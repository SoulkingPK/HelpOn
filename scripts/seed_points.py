import sys
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("d:/HelpOn/.env")
client = MongoClient(os.getenv("MONGODB_URL"))
db = client["helpon_db"]

email = sys.argv[1] if len(sys.argv) > 1 else "testuser@example.com"

# Give the user exactly 1250 points
db.users.update_one({"email": email}, {"$set": {"points": 1250}})

user = db.users.find_one({"email": email})
if user:
    print(f"Points updated successfully for {email}! Current points: {user.get('points')}")
else:
    print(f"User {email} not found. Please register first.")
