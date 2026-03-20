from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from typing import List
from datetime import datetime, timedelta
import os
import cloudinary
import cloudinary.uploader
from bson import ObjectId

from ..models import LocationUpdate, UserProfileResponse, UserProfileUpdate, UserSettingsUpdate, UserLocationResponse
from ..database import users_collection, emergencies_collection
# We need to import get_current_user from main or a separate deps file.
# For now, we will assume it's moved or imported properly later, we'll use a placeholder import from main
# Alternatively, we should move deps to a dependencies.py. Let's do that in a later step when refactoring main.py.
from ..dependencies import get_current_user, verify_csrf

router = APIRouter(tags=["Users"])

@router.get("/me/profile", response_model=UserProfileResponse)
async def get_profile(current_user: dict = Depends(get_current_user)):
    points = current_user.get("points", 0)
    helps_given = current_user.get("helps_given", 0)
    
    rank = 1 if helps_given > 10 else (3 if helps_given > 5 else 8)
    
    return UserProfileResponse(
        full_name=current_user.get("full_name", ""),
        email=current_user.get("email"),
        phone_number=current_user.get("phone_number", ""),
        avatar=current_user.get("avatar"),
        points=points,
        helps_given=helps_given,
        local_rank=rank,
        verified=current_user.get("verified", False),
        kyc_status=current_user.get("kyc_status", "none"),
        is_admin=current_user.get("is_admin", False)
    )

@router.post("/me/avatar", dependencies=[Depends(verify_csrf)])
async def upload_avatar(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    if not os.getenv("CLOUDINARY_URL"):
        raise HTTPException(status_code=500, detail="Cloudinary is not configured.")
        
    try:
        result = cloudinary.uploader.upload(file.file, folder="helpon_avatars")
        url = result.get("secure_url")
        
        await users_collection.update_one(
            {"_id": current_user["_id"]},
            {"$set": {"avatar": url}}
        )
        return {"status": "Avatar updated successfully", "url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")

@router.put("/me/profile", dependencies=[Depends(verify_csrf)])
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

@router.put("/me/location", dependencies=[Depends(verify_csrf)])
async def update_location(location: LocationUpdate, current_user: dict = Depends(get_current_user)):
    try:
        # Anti-Cheat: GPS Spoofing Detection
        last_time = current_user.get("last_location_time")
        last_loc = current_user.get("last_location")
        
        if last_time and last_loc:
            # Calculate distance using a simple Haversine formula approximation or just Euclidean if close
            # But let's use a simple speed check: dist / time
            import math
            
            def get_distance(lat1, lon1, lat2, lon2):
                R = 6371 # Radius of the earth in km
                dLat = math.radians(lat2 - lat1)
                dLon = math.radians(lon2 - lon1)
                a = math.sin(dLat / 2) * math.sin(dLat / 2) + \
                    math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
                    math.sin(dLon / 2) * math.sin(dLon / 2)
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                return R * c

            prev_coords = last_loc.get("coordinates", [0, 0])
            prev_lon, prev_lat = prev_coords
            
            dist_km = get_distance(prev_lat, prev_lon, location.lat, location.lon)
            time_diff_hours = (datetime.utcnow() - last_time).total_seconds() / 3600
            
            if time_diff_hours > 0:
                speed = dist_km / time_diff_hours
                if speed > 300: # Threshold: 300 km/h (e.g., impossible for a car in city)
                    # Flag but still update for now, or ignore? Let's ignore it to prevent cheating
                    return {"status": "Location update ignored due to impossible travel speed", "speed_kmh": round(speed, 2)}

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

@router.get("/active", response_model=List[UserLocationResponse])
async def get_active_users():
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
            last_updated=last_updated_str,
            verified=user.get("verified", False),
            kyc_status=user.get("kyc_status", "none")
        ))
        
    return active_users

@router.put("/me/settings", dependencies=[Depends(verify_csrf)])
async def update_settings(settings: UserSettingsUpdate, current_user: dict = Depends(get_current_user)):
    await users_collection.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"settings": settings.dict()}}
    )
    return {"status": "Settings updated"}

@router.get("/leaderboard")
async def get_leaderboard():
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

@router.get("/me/history")
async def get_history(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    
    requested_cursor = emergencies_collection.find({"created_by": user_id}).sort("created_at", -1)
    requests = await requested_cursor.to_list(length=50)
    
    responded_cursor = emergencies_collection.find({"helper_id": user_id}).sort("created_at", -1)
    responses = await responded_cursor.to_list(length=50)
    
    history = []
    
    for req in requests:
        helper_name = None
        if req.get("helper_id"):
            helper_user = await users_collection.find_one({"_id": ObjectId(req["helper_id"])})
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
            "rating": 5.0,
            "duration": "10 minutes",
            "location": "Map Location",
            "status": req.get("status", "active"),
            "helper": helper_name
        })
        
    for res in responses:
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
            "rating": 5.0,
            "duration": "15 minutes",
            "location": "Map Location",
            "status": res.get("status", "active"),
            "helper": None
        })
        
    history.sort(key=lambda x: x["date"] if x["date"] else "", reverse=True)
    
    return history
