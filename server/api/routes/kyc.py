from fastapi import APIRouter, HTTPException, Depends, Body
from datetime import datetime
from bson import ObjectId
from typing import List

from ..database import kyc_collection, users_collection
from ..dependencies import get_current_user, verify_csrf
from ..models import KYCSubmission, KYCResponse

router = APIRouter(tags=["KYC"])

@router.post("/submit", response_model=KYCResponse, dependencies=[Depends(verify_csrf)])
async def submit_kyc(submission: KYCSubmission, current_user: dict = Depends(get_current_user)):
    """Submit identity documents for KYC verification."""
    
    # Check if a pending or approved KYC already exists
    existing = await kyc_collection.find_one({
        "user_id": str(current_user["_id"]),
        "status": {"$in": ["pending", "approved"]}
    })
    
    if existing:
        if existing["status"] == "approved":
            raise HTTPException(status_code=400, detail="User is already verified")
        else:
            raise HTTPException(status_code=400, detail="KYC verification is already pending")
    
    kyc_data = {
        "user_id": str(current_user["_id"]),
        "document_type": submission.document_type,
        "document_number": submission.document_number,
        "document_image_url": submission.document_image_url,
        "status": "pending",
        "admin_feedback": None,
        "created_at": datetime.utcnow()
    }
    
    result = await kyc_collection.insert_one(kyc_data)
    
    # Update user's kyc_status
    await users_collection.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"kyc_status": "pending"}}
    )
    
    kyc_data["id"] = str(result.inserted_id)
    kyc_data["created_at"] = kyc_data["created_at"].isoformat()
    
    return kyc_data

@router.get("/status", response_model=KYCResponse)
async def get_kyc_status(current_user: dict = Depends(get_current_user)):
    """Get the current user's KYC verification status."""
    
    kyc = await kyc_collection.find_one(
        {"user_id": str(current_user["_id"])},
        sort=[("created_at", -1)]
    )
    
    if not kyc:
        raise HTTPException(status_code=404, detail="No KYC submission found")
    
    kyc["id"] = str(kyc["_id"])
    kyc["created_at"] = kyc["created_at"].isoformat()
    if kyc.get("verified_at"):
        kyc["verified_at"] = kyc["verified_at"].isoformat()
        
    return kyc
