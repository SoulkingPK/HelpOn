import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import logging

load_dotenv()

# Configure simple logging
logger = logging.getLogger("api.database")

MONGODB_URL = os.getenv("MONGODB_URL")

# Initialize global DB variables
client = None
db = None
users_collection = None
emergencies_collection = None
notifications_collection = None
support_requests_collection = None
faqs_collection = None

if not MONGODB_URL:
    logger.error("CRITICAL: MONGODB_URL not found in environment. Database connection impossible.")
else:
    try:
        # Lower timeout to 2 seconds for serverless environments
        client = AsyncIOMotorClient(MONGODB_URL, serverSelectionTimeoutMS=2000)
        db = client.helpon_db
        users_collection = db.get_collection("users")
        emergencies_collection = db.get_collection("emergencies")
        notifications_collection = db.get_collection("notifications")
        support_requests_collection = db.get_collection("support_requests")
        faqs_collection = db.get_collection("faqs")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        client = None
        db = None
        users_collection = None
        emergencies_collection = None
        notifications_collection = None
        support_requests_collection = None
        faqs_collection = None
