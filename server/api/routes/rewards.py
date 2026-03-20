from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime

from ..database import users_collection, rewards_collection, user_redemptions_collection
from ..dependencies import get_current_user, verify_csrf

router = APIRouter(tags=["Rewards"])

@router.get("/user/points", response_description="Get user points balance")
async def get_user_points(current_user: dict = Depends(get_current_user)):
    user_id = current_user["_id"]
    user = await users_collection.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "points": user.get("points", 0),
        "helps_given": user.get("helps_given", 0)
    }

@router.get("/", response_description="Get all available rewards")
async def get_rewards():
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

@router.post("/{reward_id}/redeem", response_description="Redeem a reward", dependencies=[Depends(verify_csrf)])
async def redeem_reward(reward_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["_id"]
    user = await users_collection.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Anti-Cheat: Daily Redemption Limit
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    daily_count = await user_redemptions_collection.count_documents({
        "user_id": str(user_id),
        "created_at": {"$gte": today_start}
    })
    
    if daily_count >= 3: # Limit: 3 redemptions per day
        raise HTTPException(status_code=400, detail="Daily redemption limit reached (max 3 per day)")
        
    reward = await rewards_collection.find_one({"id": reward_id})
    if not reward:
        raise HTTPException(status_code=404, detail="Reward not found")
        
    points_cost = int(reward.get("points_cost", 0))
    current_points = int(user.get("points", 0))
    
    if current_points < points_cost:
        raise HTTPException(status_code=400, detail="Insufficient points")
        
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

@router.get("/user/redemptions", response_description="Get user redemption history")
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
