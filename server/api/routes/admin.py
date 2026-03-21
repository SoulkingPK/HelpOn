from fastapi import APIRouter, HTTPException, Depends, Body
from datetime import datetime, timedelta
from bson import ObjectId

from ..database import users_collection, emergencies_collection, support_requests_collection
from ..dependencies import require_admin, verify_csrf

router = APIRouter(tags=["Admin"])

@router.get("/stats", response_description="Get admin dashboard statistics")
async def get_admin_stats(current_user: dict = Depends(require_admin)):
    
    total_users = await users_collection.count_documents({})
    total_sos = await emergencies_collection.count_documents({})
    active_sos = await emergencies_collection.count_documents({"status": "active"})
    resolved_sos = await emergencies_collection.count_documents({"status": "resolved"})
    open_tickets = await support_requests_collection.count_documents({"status": "open"})
    total_tickets = await support_requests_collection.count_documents({})
    
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

@router.get("/users", response_description="Get all users (admin)")
async def get_all_users(current_user: dict = Depends(require_admin)):
    
    cursor = users_collection.find({}, {
        "_id": 1, "full_name": 1, "email": 1, "phone_number": 1, 
        "points": 1, "helps_given": 1, "verified": 1, "last_active": 1, "is_admin": 1
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
            "is_admin": u.get("is_admin", False),
            "last_active": u["last_active"].isoformat() if u.get("last_active") else None
        })
    return response

@router.get("/sos", response_description="Get all SOS requests (admin)")
async def get_all_sos(current_user: dict = Depends(require_admin)):
    
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

@router.get("/support", response_description="Get all support requests (admin)")
async def get_all_support_requests(current_user: dict = Depends(require_admin)):
    
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

@router.put("/support/{ticket_id}/close", response_description="Close a support ticket", dependencies=[Depends(verify_csrf)])
async def close_support_ticket(ticket_id: str, current_user: dict = Depends(require_admin)):
    
    result = await support_requests_collection.update_one(
        {"_id": ObjectId(ticket_id)},
        {"$set": {"status": "closed", "closed_at": datetime.utcnow(), "closed_by": str(current_user["_id"])}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"status": "Ticket closed"}

@router.get("/kyc/pending", response_description="Get pending KYC requests (admin)")
async def get_pending_kyc(current_user: dict = Depends(require_admin)):
    """List all pending KYC verification requests."""
    from ..database import kyc_collection
    
    cursor = kyc_collection.find({"status": "pending"}).sort("created_at", 1)
    submissions = await cursor.to_list(length=100)
    
    response = []
    for s in submissions:
        response.append({
            "id": str(s["_id"]),
            "user_id": s["user_id"],
            "document_type": s["document_type"],
            "document_number": s["document_number"],
            "document_image_url": s["document_image_url"],
            "status": s["status"],
            "created_at": s["created_at"].isoformat() if s.get("created_at") else None
        })
    return response

@router.put("/kyc/{kyc_id}/verify", response_description="Approve or reject KYC (admin)", dependencies=[Depends(verify_csrf)])
async def verify_kyc(kyc_id: str, payload: dict = Body(...), current_user: dict = Depends(require_admin)):
    """Approve or reject a KYC submission."""
    from ..database import kyc_collection, users_collection
    
    status = payload.get("status") # "approved" or "rejected"
    feedback = payload.get("feedback")
    
    if status not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status. Use 'approved' or 'rejected'.")
    
    kyc = await kyc_collection.find_one({"_id": ObjectId(kyc_id)})
    if not kyc:
        raise HTTPException(status_code=404, detail="KYC submission not found")
    
    # Update KYC submission
    update_data = {
        "status": status,
        "admin_feedback": feedback,
        "verified_at": datetime.utcnow()
    }
    
    await kyc_collection.update_one({"_id": ObjectId(kyc_id)}, {"$set": update_data})
    
    # Update User Profile
    user_id = kyc["user_id"]
    await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {
            "kyc_status": status,
            "verified": (status == "approved") # Set verified flag if approved
        }}
    )
    
    return {"message": f"KYC {status} successfully"}
