from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from datetime import timedelta

# Relative imports assuming the current directory is 'api'
# Since Vercel executes from the project root sometimes, we import via absolute paths or local
try:
    from api.models import (
        UserCreate, UserLogin, Token, UserInDB, LocationUpdate,
        EmergencyCreate, EmergencyResponse, NotificationResponse,
        UserProfileResponse, UserSettingsUpdate
    )
    from api.database import users_collection, emergencies_collection, notifications_collection
    from api.auth import get_password_hash, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, verify_token
except ImportError:
    from models import (
        UserCreate, UserLogin, Token, UserInDB, LocationUpdate,
        EmergencyCreate, EmergencyResponse, NotificationResponse,
        UserProfileResponse, UserSettingsUpdate
    )
    from database import users_collection, emergencies_collection, notifications_collection
    from auth import get_password_hash, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, verify_token

import traceback
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime
from bson import ObjectId

app = FastAPI(title="HelpOn API")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    user = await users_collection.find_one({
        "$or": [{"email": username}, {"phone_number": username}]
    })
    
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "traceback": traceback.format_exc()}
    )

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to your netlify domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def root():
    return {"message": "HelpOn Backend is running!"}

@app.post("/api/register", response_model=Token)
async def register_user(user: UserCreate):
    if users_collection is None:
        raise HTTPException(
            status_code=500,
            detail="Database connection failed. Please check MONGODB_URL environment variable."
        )

    # Check if user exists by phone or email
    query = {"$or": [{"phone_number": user.phone_number}]}
    if user.email:
        query["$or"].append({"email": user.email})
        
    db_user = await users_collection.find_one(query)
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="User with this phone number or email already exists"
        )
    
    hashed_password = get_password_hash(user.password)
    user_dict = user.dict()
    del user_dict["password"]
    user_dict["hashed_password"] = hashed_password
    user_dict["points"] = 0
    user_dict["helps_given"] = 0
    
    new_user = await users_collection.insert_one(user_dict)
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.phone_number}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer", "full_name": user.full_name}

@app.post("/api/login", response_model=Token)
async def login_user(login_data: UserLogin):
    if users_collection is None:
        raise HTTPException(
            status_code=500,
            detail="Database connection failed. Please check MONGODB_URL environment variable."
        )

    # Search by email or phone
    user = await users_collection.find_one({
        "$or": [
            {"email": login_data.username},
            {"phone_number": login_data.username}
        ]
    })
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not verify_password(login_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.get("phone_number", user.get("email")))}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "full_name": str(user.get("full_name", ""))}

# --- Real-World Tracking APIs --- #

@app.post("/api/users/me/location")
async def update_location(location: LocationUpdate, current_user: dict = Depends(get_current_user)):
    await users_collection.update_one(
        {"_id": current_user["_id"]},
        {"$set": {
            "last_location": {
                "type": "Point",
                "coordinates": [location.lon, location.lat]
            },
            "last_active": datetime.utcnow()
        }}
    )
    return {"status": "Location updated"}

@app.get("/api/users/me/profile", response_model=UserProfileResponse)
async def get_profile(current_user: dict = Depends(get_current_user)):
    points = current_user.get("points", 0)
    helps_given = current_user.get("helps_given", 0)
    
    # Simple rank calculation
    rank = 1 if helps_given > 10 else (3 if helps_given > 5 else 8)
    
    return UserProfileResponse(
        full_name=current_user.get("full_name", ""),
        points=points,
        helps_given=helps_given,
        local_rank=rank,
        verified=current_user.get("verified", False)
    )

@app.put("/api/users/me/settings")
async def update_settings(settings: UserSettingsUpdate, current_user: dict = Depends(get_current_user)):
    await users_collection.update_one(
        {"_id": current_user["_id"]},
        {"$set": {
            "settings": settings.dict()
        }}
    )
    return {"status": "Settings updated"}

@app.post("/api/emergencies")
async def create_emergency(emergency: EmergencyCreate, current_user: dict = Depends(get_current_user)):
    new_emergency = {
        "type": emergency.type,
        "description": emergency.description,
        "location": {
            "type": "Point",
            "coordinates": [emergency.lon, emergency.lat]
        },
        "created_by": str(current_user["_id"]),
        "created_name": current_user.get("full_name"),
        "status": "active",
        "created_at": datetime.utcnow()
    }
    
    result = await emergencies_collection.insert_one(new_emergency)
    
    # Blasting a notification to all other users
    users_cursor = users_collection.find({"_id": {"$ne": current_user["_id"]}})
    async for user in users_cursor:
        await notifications_collection.insert_one({
            "user_id": str(user["_id"]),
            "title": "Emergency Alert",
            "message": f"{new_emergency['created_name']} triggered an SOS nearby: {emergency.description}",
            "type": "alert",
            "is_read": False,
            "created_at": datetime.utcnow()
        })
        
    return {"status": "Emergency broadcasted", "id": str(result.inserted_id)}

@app.get("/api/emergencies/nearby")
async def get_nearby_emergencies(current_user: dict = Depends(get_current_user)):
    # Simulating getting all active emergencies
    cursor = emergencies_collection.find({"status": "active"})
    emergencies = await cursor.to_list(length=100)
    
    response = []
    for e in emergencies:
        response.append({
            "id": str(e["_id"]),
            "type": e["type"],
            "description": e["description"],
            "lat": e["location"]["coordinates"][1],
            "lon": e["location"]["coordinates"][0],
            "created_by": e.get("created_name", "Someone"),
            "status": e["status"],
            "created_at": e["created_at"].isoformat()
        })
    return {"emergencies": response, "active_helpers": 3}

@app.post("/api/emergencies/{emergency_id}/accept")
async def accept_emergency(emergency_id: str, current_user: dict = Depends(get_current_user)):
    result = await emergencies_collection.update_one(
        {"_id": ObjectId(emergency_id), "status": "active"},
        {"$set": {
            "status": "accepted",
            "helper_id": str(current_user["_id"]),
            "helper_name": current_user.get("full_name")
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Emergency not found or already accepted.")
        
    return {"status": "Emergency accepted"}

@app.post("/api/emergencies/{emergency_id}/complete")
async def complete_emergency(emergency_id: str, current_user: dict = Depends(get_current_user)):
    emergency = await emergencies_collection.find_one({"_id": ObjectId(emergency_id)})
    
    if not emergency:
        raise HTTPException(status_code=404, detail="Emergency not found")
        
    if emergency.get("helper_id") != str(current_user["_id"]):
         raise HTTPException(status_code=403, detail="You are not authorized to complete this emergency.")
         
    # Mark resolved
    await emergencies_collection.update_one(
        {"_id": ObjectId(emergency_id)},
        {"$set": {"status": "resolved"}}
    )
    
    # Award 20 points and +1 help to the helper
    await users_collection.update_one(
        {"_id": current_user["_id"]},
        {"$inc": {"points": 20, "helps_given": 1}}
    )
    
    # Notify the victim
    await notifications_collection.insert_one({
        "user_id": emergency["created_by"],
        "title": "Help Completed",
        "message": f"{current_user.get('full_name')} has resolved your emergency.",
        "type": "help",
        "is_read": False,
        "created_at": datetime.utcnow()
    })
    
    return {"status": "Emergency resolved and 20 Points awarded."}

@app.get("/api/inbox")
async def get_inbox(current_user: dict = Depends(get_current_user)):
    cursor = notifications_collection.find({"user_id": str(current_user["_id"])}).sort("created_at", -1)
    notifications = await cursor.to_list(length=50)
    
    response = []
    for n in notifications:
        response.append({
            "id": str(n["_id"]),
            "title": n["title"],
            "message": n["message"],
            "type": n["type"],
            "is_read": n.get("is_read", False),
            "created_at": n["created_at"].isoformat()
        })
    return response

@app.post("/api/inbox/{notif_id}/read")
async def read_notification(notif_id: str, current_user: dict = Depends(get_current_user)):
    await notifications_collection.update_one(
        {"_id": ObjectId(notif_id), "user_id": str(current_user["_id"])},
        {"$set": {"is_read": True}}
    )
    return {"status": "Read"}
