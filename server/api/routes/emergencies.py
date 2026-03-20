from fastapi import APIRouter, HTTPException, Depends, Request
from datetime import datetime
from bson import ObjectId

from ..models import EmergencyCreate
from ..database import users_collection, emergencies_collection, notifications_collection
from ..dependencies import get_current_user, manager, limiter, verify_csrf

router = APIRouter(tags=["Emergencies"])

@router.post("/sos", dependencies=[Depends(verify_csrf)])
@limiter.limit("3/minute")
async def create_emergency(emergency: EmergencyCreate, request: Request, current_user: dict = Depends(get_current_user)):
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
    
    # Blasting a notification to users within a 20km radius
    users_cursor = users_collection.find({
        "_id": {"$ne": current_user["_id"]},
        "last_location": {
            "$near": {
                "$geometry": {
                    "type": "Point",
                    "coordinates": [emergency.lon, emergency.lat]
                },
                "$maxDistance": 20000
            }
        }
    })
    async for user in users_cursor:
        await notifications_collection.insert_one({
            "user_id": str(user["_id"]),
            "title": "Emergency Alert",
            "message": f"{new_emergency['created_name']} triggered an SOS nearby: {emergency.description}",
            "type": "alert",
            "is_read": False,
            "created_at": datetime.utcnow()
        })
        
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

@router.get("/nearby")
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
        
    # Active helpers
    from datetime import timedelta
    active_users = await users_collection.count_documents({"last_active": {"$gte": datetime.utcnow() - timedelta(hours=1)}})
    return {"emergencies": response, "active_helpers": active_users}

@router.post("/{id}/accept", dependencies=[Depends(verify_csrf)])
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

@router.put("/{id}/complete", dependencies=[Depends(verify_csrf)])
async def complete_emergency(id: str, current_user: dict = Depends(get_current_user)):
    emergency = await emergencies_collection.find_one({"_id": ObjectId(id)})
    
    if not emergency:
        raise HTTPException(status_code=404, detail="Emergency not found")
        
    if emergency.get("created_by") != str(current_user["_id"]) and emergency.get("helper_id") != str(current_user["_id"]):
         raise HTTPException(status_code=403, detail="Only involved users can complete the SOS.")
         
    await emergencies_collection.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"status": "resolved"}}
    )
    
    helper_id = emergency.get("helper_id")
    if helper_id:
        await users_collection.update_one(
            {"_id": ObjectId(helper_id)},
            {"$inc": {"points": 50, "helps_given": 1}}
        )
        
        await notifications_collection.insert_one({
            "user_id": helper_id,
            "title": "Help Rewards",
            "message": f"{current_user.get('full_name')} marked the emergency as resolved! You have been awarded 50 HelpPoints.",
            "type": "reward",
            "is_read": False,
            "created_at": datetime.utcnow()
        })
        
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

@router.get("/inbox")
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

@router.post("/inbox/{notif_id}/read", dependencies=[Depends(verify_csrf)])
async def read_notification(notif_id: str, current_user: dict = Depends(get_current_user)):
    await notifications_collection.update_one(
        {"_id": ObjectId(notif_id), "user_id": str(current_user["_id"])},
        {"$set": {"is_read": True}}
    )
    return {"status": "Read"}
