from fastapi import FastAPI, HTTPException, status, Depends
from typing import Optional, List, Dict, Any
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from datetime import timedelta

import sys
import os
import cloudinary
import cloudinary.uploader

# Add the 'server' directory to sys.path so Vercel can resolve 'api.models'
# __file__ is server/api/main.py, so we need the parent of the parent
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import using absolute paths corresponding to the injected sys.path
from api.models import (
    UserCreate, UserLogin, Token, UserInDB, LocationUpdate,
    EmergencyCreate, EmergencyResponse, NotificationResponse,
    UserProfileResponse, UserSettingsUpdate, UserProfileUpdate,
    HelpRequestCreate, HelpRequestResponse, ChatbotQuery, RefreshTokenRequest,
    RewardResponse, RedemptionResponse, UserLocationResponse
)
from api.database import (
    users_collection, emergencies_collection, notifications_collection,
    support_requests_collection, faqs_collection, rewards_collection, user_redemptions_collection
)
from api.auth import get_password_hash, verify_password, create_access_token, create_refresh_token, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS, verify_token, verify_refresh_token

import traceback
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime
from bson import ObjectId
from fastapi import WebSocket, WebSocketDisconnect
from typing import List, Dict

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

app = FastAPI(title="HelpOn API")

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login", auto_error=False)

async def get_current_user(request: Request, token: Optional[str] = Depends(oauth2_scheme)):
    # Try header first, then cookie
    if not token:
        token = request.cookies.get("helpon_access_token")
        
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
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

async def get_current_user_optional(request: Request, token: Optional[str] = Depends(oauth2_scheme)):
    if not token:
        token = request.cookies.get("helpon_access_token")
        
    if not token:
        return None
    try:
        user = await get_current_user(request, token)
        return user
    except:
        return None

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "traceback": traceback.format_exc()}
    )

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://soulkingpk.github.io",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Content-Type", "Authorization"],
)

@app.get("/api/health")
async def root():
    return {"message": "HelpOn Backend is running!"}

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Can be used to handle incoming messages like "ping" to keep connection alive
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

from fastapi import Response

@app.post("/api/register")
async def register_user(user: UserCreate, response: Response):
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
    refresh_token = create_refresh_token(data={"sub": user.phone_number}, expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    
    # Set cookies
    response.set_cookie(
        key="helpon_access_token",
        value=access_token,
        httponly=True,
        secure=True, # Will only be sent over HTTPS
        samesite="none", # Required for cross-site requests
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    response.set_cookie(
        key="helpon_refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )
    
    return {"token_type": "bearer", "full_name": user.full_name}

@app.post("/api/login")
async def login_user(login_data: UserLogin, response: Response):
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
    refresh_token = create_refresh_token(
        data={"sub": str(user.get("phone_number", user.get("email")))},
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )
    
    # Set cookies
    response.set_cookie(
        key="helpon_access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    response.set_cookie(
        key="helpon_refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )
    
    return {"token_type": "bearer", "full_name": str(user.get("full_name", ""))}

@app.post("/api/refresh")
async def refresh_access_token(request: Request, response: Response):
    # Determine where the refresh token is
    ref_token = request.cookies.get("helpon_refresh_token")
    if not ref_token:
        # Fallback to reading from body if frontend still sends it
        try:
            body = await request.json()
            ref_token = body.get("refresh_token")
        except:
            pass
            
    if not ref_token:
        raise HTTPException(status_code=400, detail="No refresh token provided")

    payload = verify_refresh_token(ref_token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = await users_collection.find_one({
        "$or": [{"email": username}, {"phone_number": username}]
    })
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.get("phone_number", user.get("email")))}, expires_delta=access_token_expires
    )
    new_refresh_token = create_refresh_token(
        data={"sub": str(user.get("phone_number", user.get("email")))},
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )

    # Set cookies
    response.set_cookie(
        key="helpon_access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    response.set_cookie(
        key="helpon_refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )

    return {
        "token_type": "bearer",
        "full_name": str(user.get("full_name", ""))
    }
    
@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie(key="helpon_access_token", secure=True, httponly=True, samesite="none")
    response.delete_cookie(key="helpon_refresh_token", secure=True, httponly=True, samesite="none")
    return {"status": "Logged out successfully"}

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
        email=current_user.get("email"),
        phone_number=current_user.get("phone_number", ""),
        avatar=current_user.get("avatar"),
        points=points,
        helps_given=helps_given,
        local_rank=rank,
        verified=current_user.get("verified", False)
    )

from fastapi import UploadFile, File

@app.post("/api/users/me/avatar")
async def upload_avatar(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    if not os.getenv("CLOUDINARY_URL"):
        raise HTTPException(status_code=500, detail="Cloudinary is not configured. Please add CLOUDINARY_URL to .env")
        
    try:
        # Upload to cloudinary
        result = cloudinary.uploader.upload(file.file, folder="helpon_avatars")
        url = result.get("secure_url")
        
        # Save URL to MongoDB
        await users_collection.update_one(
            {"_id": current_user["_id"]},
            {"$set": {"avatar": url}}
        )
        return {"status": "Avatar updated successfully", "url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")

@app.put("/api/users/me/profile")
async def update_profile(profile_data: UserProfileUpdate, current_user: dict = Depends(get_current_user)):
    update_fields = {
        "full_name": profile_data.full_name,
        "phone_number": profile_data.phone_number
    }
    
    if profile_data.email is not None:
        update_fields["email"] = profile_data.email
        
    if profile_data.avatar is not None:
        update_fields["avatar"] = profile_data.avatar
        
    await users_collection.update_one(
        {"_id": current_user["_id"]},
        {"$set": update_fields}
    )
    
    return {"status": "Profile updated successfully"}

@app.put("/api/users/me/location")
async def update_location(location: LocationUpdate, current_user: dict = Depends(get_current_user)):
    try:
        await users_collection.update_one(
            {"_id": current_user["_id"]},
            {
                "$set": {
                    "last_location": {
                        "type": "Point",
                        "coordinates": [location.lon, location.lat]
                    },
                    "last_location_time": datetime.utcnow()
                }
            }
        )
        return {"status": "Location updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/users/active", response_model=List[UserLocationResponse])
async def get_active_users():
    # Fetch users updated in the last 15 minutes
    fifteen_mins_ago = datetime.utcnow() - timedelta(minutes=15)
    
    cursor = users_collection.find({
        "last_location_time": {"$gte": fifteen_mins_ago},
        "last_location": {"$exists": True}
    })
    
    users = await cursor.to_list(length=100)
    
    active_users = []
    for user in users:
        coords = user.get("last_location", {}).get("coordinates", [0, 0])
        lon, lat = coords if len(coords) == 2 else (0, 0)
        
        last_updated = user.get("last_location_time")
        if last_updated:
            last_updated_str = last_updated.isoformat() + "Z"
        else:
            last_updated_str = datetime.utcnow().isoformat() + "Z"
            
        active_users.append(UserLocationResponse(
            id=str(user["_id"]),
            full_name=user.get("full_name", "Anonymous Helper") or "Anonymous Helper",
            lat=lat,
            lon=lon,
            last_updated=last_updated_str
        ))
        
    return active_users

@app.put("/api/users/me/settings")
async def update_settings(settings: UserSettingsUpdate, current_user: dict = Depends(get_current_user)):
    await users_collection.update_one(
        {"_id": current_user["_id"]},
        {"$set": {
            "settings": settings.dict()
        }}
    )
    return {"status": "Settings updated"}

@app.get("/api/leaderboard")
async def get_leaderboard():
    # Fetch top 50 users sorted by points descending
    cursor = users_collection.find(
        {}, 
        {"full_name": 1, "points": 1, "helps_given": 1, "verified": 1}
    ).sort("points", -1).limit(50)
    
    users = await cursor.to_list(length=50)
    
    leaderboard = []
    for rank, user in enumerate(users, start=1):
        leaderboard.append({
            "id": str(user["_id"]),
            "rank": rank,
            "name": user.get("full_name", "Anonymous Helper") or "Anonymous Helper",
            "points": user.get("points", 0),
            "helps": user.get("helps_given", 0),
            "verified": user.get("verified", False)
        })
        
    return leaderboard

@app.get("/api/users/me/history")
async def get_history(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    
    # 1. Get emergencies requested by this user (where they were the victim needing help)
    requested_cursor = emergencies_collection.find({"created_by": user_id}).sort("created_at", -1)
    requests = await requested_cursor.to_list(length=50)
    
    # 2. Get emergencies responded to by this user (where they were the helper)
    responded_cursor = emergencies_collection.find({"accepted_by": user_id}).sort("created_at", -1)
    responses = await responded_cursor.to_list(length=50)
    
    history = []
    
    for req in requests:
        helper_name = None
        if req.get("accepted_by"):
            helper_user = await users_collection.find_one({"_id": ObjectId(req["accepted_by"])})
            if helper_user:
                helper_name = helper_user.get("full_name")
                
        history.append({
            "id": str(req["_id"]),
            "type": "requested",
            "emergencyType": req.get("type", "other").lower(),
            "title": f"Requested SOS",
            "description": req.get("description", "SOS Help Request"),
            "person": "You",
            "date": req.get("created_at", datetime.utcnow()).isoformat() if req.get("created_at") else None,
            "points": 0,
            "rating": 5.0, # Defaulting for now
            "duration": "10 minutes",
            "location": "Map Location",
            "status": req.get("status", "active"),
            "helper": helper_name
        })
        
    for res in responses:
        # User is the helper here, so they earned points
        points_earned = 20 if res.get("status") == "completed" else 0
        history.append({
            "id": str(res["_id"]),
            "type": "responded",
            "emergencyType": res.get("type", "other").lower(),
            "title": f"Responded to SOS",
            "description": res.get("description", "Responded to emergency"),
            "person": res.get("created_name", "Unknown User"),
            "date": res.get("created_at", datetime.utcnow()).isoformat() if res.get("created_at") else None,
            "points": points_earned,
            "rating": 5.0, # Defaulting for now
            "duration": "15 minutes",
            "location": "Map Location",
            "status": res.get("status", "active"),
            "helper": None # User IS the helper here
        })
        
    # Sort history by Date descending
    history.sort(key=lambda x: x["date"] if x["date"] else "", reverse=True)
    
    return history

@app.post("/api/emergency/sos")
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
        
    # Broadcast to websockets
    try:
        await manager.broadcast({
            "type": "new_sos",
            "data": {
                "id": str(result.inserted_id),
                "type": new_emergency["type"],
                "description": new_emergency["description"],
                "lat": emergency.lat,
                "lon": emergency.lon,
                "created_by": new_emergency["created_name"],
                "status": new_emergency["status"],
                "created_at": new_emergency["created_at"].isoformat()
            }
        })
    except Exception as e:
        print(f"WebSocket broadcast error: {e}")
        
    return {"status": "Emergency broadcasted", "id": str(result.inserted_id)}

@app.get("/api/emergency/nearby")
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
    # Calculate real active helpers in the last hour
    active_users = await users_collection.count_documents({"last_active": {"$gte": datetime.utcnow() - timedelta(hours=1)}})
    return {"emergencies": response, "active_helpers": active_users}

@app.post("/api/emergency/{id}/accept")
async def accept_emergency(id: str, current_user: dict = Depends(get_current_user)):
    result = await emergencies_collection.update_one(
        {"_id": ObjectId(id), "status": "active"},
        {"$set": {
            "status": "accepted",
            "helper_id": str(current_user["_id"]),
            "helper_name": current_user.get("full_name")
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Emergency not found or already accepted.")
        
    # Broadcast update
    try:
        await manager.broadcast({
            "type": "update_sos",
            "data": {
                "id": id,
                "status": "accepted",
                "helper_id": str(current_user["_id"]),
                "helper_name": current_user.get("full_name")
            }
        })
    except Exception as e:
        print(f"WebSocket broadcast error: {e}")
        
    return {"status": "Emergency accepted"}

@app.put("/api/emergency/{id}/complete")
async def complete_emergency(id: str, current_user: dict = Depends(get_current_user)):
    emergency = await emergencies_collection.find_one({"_id": ObjectId(id)})
    
    if not emergency:
        raise HTTPException(status_code=404, detail="Emergency not found")
        
    if emergency.get("created_by") != str(current_user["_id"]) and emergency.get("helper_id") != str(current_user["_id"]):
         raise HTTPException(status_code=403, detail="Only involved users can complete the SOS.")
         
    # Mark resolved
    await emergencies_collection.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"status": "resolved"}}
    )
    
    # Award 50 points and +1 help to the helper
    helper_id = emergency.get("helper_id")
    if helper_id:
        await users_collection.update_one(
            {"_id": ObjectId(helper_id)},
            {"$inc": {"points": 50, "helps_given": 1}}
        )
        
        # Notify the helper
        await notifications_collection.insert_one({
            "user_id": helper_id,
            "title": "Help Rewards",
            "message": f"{current_user.get('full_name')} marked the emergency as resolved! You have been awarded 50 HelpPoints.",
            "type": "reward",
            "is_read": False,
            "created_at": datetime.utcnow()
        })
        
    # Broadcast update
    try:
        await manager.broadcast({
            "type": "update_sos",
            "data": {
                "id": id,
                "status": "resolved"
            }
        })
    except Exception as e:
        print(f"WebSocket broadcast error: {e}")
        
    return {"status": "Emergency resolved and 50 Points awarded."}

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


# --- Support & Help Endpoints --- #
@app.post("/api/support", response_description="Submit a help request")
@limiter.limit("5/minute")
async def submit_support_request(request: Request, body: HelpRequestCreate, current_user: Optional[dict] = Depends(get_current_user_optional)):
    user_id = str(current_user["_id"]) if current_user else None
    
    new_request = {
        "name": body.name,
        "email": body.email,
        "subject": body.subject,
        "message": body.message,
        "user_id": user_id,
        "status": "open",
        "created_at": datetime.utcnow()
    }
    
    result = await support_requests_collection.insert_one(new_request)
    
    # In a real app, send an email to the user here using SMTP or SendGrid
    print(f"Mock Email Sent: 'We received your request ({body.subject}) and will respond shortly!' to {body.email}")
    
    return {"status": "success", "message": "Your request has been submitted successfully. We will email you shortly.", "id": str(result.inserted_id)}

@app.get("/api/faqs", response_description="Get Frequently Asked Questions")
async def get_faqs():
    # If DB is empty, provide default FAQs
    count = await faqs_collection.count_documents({})
    if count == 0:
        default_faqs = [
            {"question": "How do I become a verified helper?", "answer": "You can request verification from your profile page. You will need to upload a valid government ID.", "category": "account"},
            {"question": "How do HelpPoints work?", "answer": "You earn HelpPoints by assisting others during emergencies. These points can be redeemed in the Rewards section.", "category": "rewards"},
            {"question": "Is my location always tracked?", "answer": "No. Your location is only shared when you actively have the app open or when you broadcast an SOS.", "category": "privacy"}
        ]
        await faqs_collection.insert_many(default_faqs)
        
    cursor = faqs_collection.find({})
    faqs = await cursor.to_list(length=100)
    
    response = []
    for faq in faqs:
        response.append({
            "id": str(faq["_id"]),
            "question": faq["question"],
            "answer": faq["answer"],
            "category": faq.get("category", "general")
        })
    return response

@app.post("/api/chatbot", response_description="AI Chatbot Assistant")
async def ai_chatbot(query: ChatbotQuery):
    # This is a mock AI response. In production, connect this to OpenAI/Gemini/Claude
    user_msg = query.prompt.lower()
    bot_response = "I am the HelpOn AI assistant. How can I help you today?"
    
    if "point" in user_msg or "reward" in user_msg:
        bot_response = "You can earn HelpPoints by completing SOS assists. Navigate to the Rewards tab to see what you can redeem them for!"
    elif "verify" in user_msg or "id" in user_msg:
        bot_response = "To get verified, go to your Profile and click 'Complete Verification' under the Verification Status section."
    elif "location" in user_msg or "tracking" in user_msg:
        bot_response = "HelpOn only tracks your location when the app is active to preserve your privacy."
        
    return {"response": bot_response}

# --- Rewards & Redemptions Endpoints --- #

@app.get("/api/user/points", response_description="Get user points balance")
async def get_user_points(current_user: dict = Depends(get_current_user)):
    user_id = current_user["_id"]
    user = await users_collection.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "points": user.get("points", 0),
        "helps_given": user.get("helps_given", 0)
    }

@app.get("/api/rewards", response_description="Get all available rewards")
async def get_rewards():
    # If empty, seed database first
    count = await rewards_collection.count_documents({})
    if count == 0:
        default_rewards = [
            {
                "id": "amazon_500",
                "name": "₹500 Amazon Voucher",
                "description": "Use for any purchase on Amazon",
                "points_cost": 1000,
                "image_text": "AMZN",
                "image_color": "linear-gradient(135deg, #FF9900 0%, #FFD700 100%)"
            },
            {
                "id": "zomato_300",
                "name": "₹300 Zomato Credit",
                "description": "Food delivery or dining",
                "points_cost": 600,
                "image_text": "ZOM",
                "image_color": "linear-gradient(135deg, #E23744 0%, #FF6B6B 100%)"
            },
            {
                "id": "flipkart_200",
                "name": "₹200 Flipkart Voucher",
                "description": "Apply at checkout",
                "points_cost": 400,
                "image_text": "FLP",
                "image_color": "linear-gradient(135deg, #047BD5 0%, #00A8F0 100%)"
            },
            {
                "id": "paytm_100",
                "name": "₹100 Paytm Cash",
                "description": "Direct wallet transfer",
                "points_cost": 200,
                "image_text": "PTM",
                "image_color": "linear-gradient(135deg, #002E6E 0%, #0047AB 100%)"
            }
        ]
        await rewards_collection.insert_many(default_rewards)

    cursor = rewards_collection.find({})
    rewards = await cursor.to_list(length=100)
    
    response = []
    for r in rewards:
        response.append({
            "id": r["id"],
            "name": r["name"],
            "description": r["description"],
            "points_cost": r["points_cost"],
            "image_text": r["image_text"],
            "image_color": r["image_color"]
        })
    return response

@app.post("/api/rewards/{reward_id}/redeem", response_description="Redeem a reward")
async def redeem_reward(reward_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["_id"]
    user = await users_collection.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    reward = await rewards_collection.find_one({"id": reward_id})
    if not reward:
        raise HTTPException(status_code=404, detail="Reward not found")
        
    points_cost = int(reward.get("points_cost", 0))
    current_points = int(user.get("points", 0))
    
    if current_points < points_cost:
        raise HTTPException(status_code=400, detail="Insufficient points")
        
    # Deduct points locally then update DB
    new_points = current_points - points_cost
    await users_collection.update_one(
        {"_id": user_id},
        {"$set": {"points": new_points}}
    )
    
    import random
    import string
    voucher_code = f"{reward.get('image_text', 'VOUCHER')}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
    
    redemption_record = {
        "user_id": str(user_id),
        "reward_id": reward_id,
        "reward_name": reward["name"],
        "points_cost": points_cost,
        "voucher_code": voucher_code,
        "status": "completed",
        "created_at": datetime.utcnow()
    }
    
    result = await user_redemptions_collection.insert_one(redemption_record)
    
    return {
        "id": str(result.inserted_id),
        "reward_id": reward_id,
        "reward_name": reward["name"],
        "voucher_code": voucher_code,
        "status": "completed",
        "created_at": redemption_record["created_at"]
    }

@app.get("/api/user/redemptions", response_description="Get user redemption history")
async def get_user_redemptions(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    cursor = user_redemptions_collection.find({"user_id": user_id}).sort("created_at", -1)
    redemptions = await cursor.to_list(length=100)
    
    response = []
    for r in redemptions:
        response.append({
            "id": str(r["_id"]),
            "reward_id": r["reward_id"],
            "reward_name": r["reward_name"],
            "voucher_code": r["voucher_code"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat()
        })
    return response

# --- Admin Endpoints --- #

def check_admin(user: dict):
    """Simple admin check. In production, check user role from DB."""
    # For now, allow any authenticated user to access admin (protected by auth cookie).
    # TODO: Add role-based access: if not user.get("is_admin"): raise HTTPException(403, ...)
    return True

@app.get("/api/admin/stats", response_description="Get admin dashboard statistics")
async def get_admin_stats(current_user: dict = Depends(get_current_user)):
    check_admin(current_user)
    
    total_users = await users_collection.count_documents({})
    total_sos = await emergencies_collection.count_documents({})
    active_sos = await emergencies_collection.count_documents({"status": "active"})
    resolved_sos = await emergencies_collection.count_documents({"status": "resolved"})
    open_tickets = await support_requests_collection.count_documents({"status": "open"})
    total_tickets = await support_requests_collection.count_documents({})
    
    # Active users in last 24 hours
    active_users_24h = await users_collection.count_documents({
        "last_active": {"$gte": datetime.utcnow() - timedelta(hours=24)}
    })
    
    return {
        "total_users": total_users,
        "active_users_24h": active_users_24h,
        "total_sos": total_sos,
        "active_sos": active_sos,
        "resolved_sos": resolved_sos,
        "open_tickets": open_tickets,
        "total_tickets": total_tickets,
    }

@app.get("/api/admin/users", response_description="Get all users (admin)")
async def get_all_users(current_user: dict = Depends(get_current_user)):
    check_admin(current_user)
    
    cursor = users_collection.find({}, {
        "_id": 1, "full_name": 1, "email": 1, "phone_number": 1, 
        "points": 1, "helps_given": 1, "verified": 1, "last_active": 1
    }).sort("points", -1).limit(100)
    users = await cursor.to_list(length=100)
    
    response = []
    for u in users:
        response.append({
            "id": str(u["_id"]),
            "full_name": u.get("full_name", "Unknown"),
            "email": u.get("email", ""),
            "phone_number": u.get("phone_number", ""),
            "points": u.get("points", 0),
            "helps_given": u.get("helps_given", 0),
            "verified": u.get("verified", False),
            "last_active": u["last_active"].isoformat() if u.get("last_active") else None
        })
    return response

@app.get("/api/admin/sos", response_description="Get all SOS requests (admin)")
async def get_all_sos(current_user: dict = Depends(get_current_user)):
    check_admin(current_user)
    
    cursor = emergencies_collection.find({}).sort("created_at", -1).limit(100)
    emergencies = await cursor.to_list(length=100)
    
    response = []
    for e in emergencies:
        response.append({
            "id": str(e["_id"]),
            "type": e.get("type", "other"),
            "description": e.get("description", ""),
            "status": e.get("status", "active"),
            "created_by": e.get("created_name", "Unknown"),
            "lat": e["location"]["coordinates"][1] if e.get("location") else None,
            "lon": e["location"]["coordinates"][0] if e.get("location") else None,
            "created_at": e["created_at"].isoformat() if e.get("created_at") else None
        })
    return response

@app.get("/api/admin/support", response_description="Get all support requests (admin)")
async def get_all_support_requests(current_user: dict = Depends(get_current_user)):
    check_admin(current_user)
    
    cursor = support_requests_collection.find({}).sort("created_at", -1)
    requests = await cursor.to_list(length=100)
    
    response = []
    for req in requests:
        response.append({
            "id": str(req["_id"]),
            "name": req["name"],
            "email": req["email"],
            "subject": req["subject"],
            "message": req["message"],
            "status": req.get("status", "open"),
            "created_at": req["created_at"].isoformat() if "created_at" in req else None
        })
    return response

@app.put("/api/admin/support/{ticket_id}/close", response_description="Close a support ticket")
async def close_support_ticket(ticket_id: str, current_user: dict = Depends(get_current_user)):
    check_admin(current_user)
    
    result = await support_requests_collection.update_one(
        {"_id": ObjectId(ticket_id)},
        {"$set": {"status": "closed", "closed_at": datetime.utcnow(), "closed_by": str(current_user["_id"])}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"status": "Ticket closed"}
