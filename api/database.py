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

if not MONGODB_URL:
    logger.error("CRITICAL: MONGODB_URL not found in environment. Database connection impossible.")
else:
    try:
        # Lower timeout to 2 seconds for serverless environments
        client = AsyncIOMotorClient(MONGODB_URL, serverSelectionTimeoutMS=2000)
        db = client.helpon_db
        users_collection = db.get_collection("users")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        client = None
        db = None
        users_collection = None
