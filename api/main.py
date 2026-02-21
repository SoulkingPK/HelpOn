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
        UserProfileResponse, UserSettingsUpdate,
        HelpRequestCreate, HelpRequestResponse, ChatbotQuery
    )
    from api.database import (
        users_collection, emergencies_collection, notifications_collection,
        support_requests_collection, faqs_collection
    )
    from api.auth import get_password_hash, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, verify_token
except ImportError:
    from models import (
        UserCreate, UserLogin, Token, UserInDB, LocationUpdate,
        EmergencyCreate, EmergencyResponse, NotificationResponse,
        UserProfileResponse, UserSettingsUpdate,
        HelpRequestCreate, HelpRequestResponse, ChatbotQuery
    )
    from database import (
        users_collection, emergencies_collection, notifications_collection,
        support_requests_collection, faqs_collection
    )
    from auth import get_password_hash, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, verify_token

import traceback
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime
from bson import ObjectId

app = FastAPI(title="HelpOn API")

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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

from typing import Optional

async def get_current_user_optional(token: Optional[str] = Depends(OAuth2PasswordBearer(tokenUrl="api/login", auto_error=False))):
    if not token:
        return None
    try:
        user = await get_current_user(token)
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
    # Calculate real active helpers in the last hour
    active_users = await users_collection.count_documents({"last_active": {"$gte": datetime.utcnow() - timedelta(hours=1)}})
    return {"emergencies": response, "active_helpers": active_users}

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
        
    if emergency.get("created_by") != str(current_user["_id"]):
         raise HTTPException(status_code=403, detail="Only the user who requested help can complete the SOS.")
         
    # Mark resolved
    await emergencies_collection.update_one(
        {"_id": ObjectId(emergency_id)},
        {"$set": {"status": "resolved"}}
    )
    
    # Award 20 points and +1 help to the helper
    helper_id = emergency.get("helper_id")
    if helper_id:
        await users_collection.update_one(
            {"_id": ObjectId(helper_id)},
            {"$inc": {"points": 20, "helps_given": 1}}
        )
        
        # Notify the helper
        await notifications_collection.insert_one({
            "user_id": helper_id,
            "title": "Help Rewards",
            "message": f"{current_user.get('full_name')} marked the emergency as resolved! You have been awarded 20 HelpPoints.",
            "type": "reward",
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

# --- Support & Help Endpoints --- #

@app.post("/api/support", response_description="Submit a help request")
async def submit_support_request(request: HelpRequestCreate, current_user: Optional[dict] = Depends(get_current_user_optional)):
    user_id = str(current_user["_id"]) if current_user else None
    
    new_request = {
        "name": request.name,
        "email": request.email,
        "subject": request.subject,
        "message": request.message,
        "user_id": user_id,
        "status": "open",
        "created_at": datetime.utcnow()
    }
    
    result = await support_requests_collection.insert_one(new_request)
    
    # In a real app, send an email to the user here using SMTP or SendGrid
    print(f"Mock Email Sent: 'We received your request ({request.subject}) and will respond shortly!' to {request.email}")
    
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

# --- Admin Endpoints --- #

@app.get("/api/admin/support", response_description="Get all support requests")
async def get_all_support_requests(current_user: dict = Depends(get_current_user)):
    # In a real app, verify the user is an admin here
    
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
