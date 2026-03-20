from fastapi import APIRouter, Depends, Request
from typing import Optional
from datetime import datetime

from ..models import HelpRequestCreate, ChatbotQuery
from ..database import support_requests_collection, faqs_collection
from ..dependencies import get_current_user_optional, limiter, verify_csrf

router = APIRouter(tags=["Support"])

@router.post("/request", response_description="Submit a help request", dependencies=[Depends(verify_csrf)])
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
    
    print(f"Mock Email Sent: 'We received your request ({body.subject}) and will respond shortly!' to {body.email}")
    
    return {"status": "success", "message": "Your request has been submitted successfully. We will email you shortly.", "id": str(result.inserted_id)}

@router.get("/faqs", response_description="Get Frequently Asked Questions")
async def get_faqs():
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

@router.post("/chatbot", response_description="AI Chatbot Assistant")
async def ai_chatbot(query: ChatbotQuery):
    user_msg = query.prompt.lower()
    bot_response = "I am the HelpOn AI assistant. How can I help you today?"
    
    if "point" in user_msg or "reward" in user_msg:
        bot_response = "You can earn HelpPoints by completing SOS assists. Navigate to the Rewards tab to see what you can redeem them for!"
    elif "verify" in user_msg or "id" in user_msg:
        bot_response = "To get verified, go to your Profile and click 'Complete Verification' under the Verification Status section."
    elif "location" in user_msg or "tracking" in user_msg:
        bot_response = "HelpOn only tracks your location when the app is active to preserve your privacy."
        
    return {"response": bot_response}
