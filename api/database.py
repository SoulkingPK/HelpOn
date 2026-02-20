import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL")
if not MONGODB_URL:
    # Fallback to local for development if not provided, though Vercel/Atlas will need real config
    MONGODB_URL = "mongodb://localhost:27017"
    
client = AsyncIOMotorClient(MONGODB_URL)
db = client.helpon_db
users_collection = db.get_collection("users")
