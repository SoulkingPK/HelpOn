import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import logging

load_dotenv()

# Configure simple logging
logger = logging.getLogger("api.database")

MONGODB_URL = os.getenv("MONGODB_URL")
if not MONGODB_URL:
    MONGODB_URL = "mongodb://localhost:27017" # Local fallback
    logger.warning("MONGODB_URL not found in environment, falling back to local auth.")

try:
    client = AsyncIOMotorClient(MONGODB_URL, serverSelectionTimeoutMS=5000)
    db = client.helpon_db
    users_collection = db.get_collection("users")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    # Initialize as None so the API can handle it gracefully instead of crashing on import
    client = None
    db = None
    users_collection = None
