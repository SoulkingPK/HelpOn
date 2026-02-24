from pymongo import MongoClient
import sys
import os
from dotenv import load_dotenv

load_dotenv("d:/HelpOn/.env")
client = MongoClient(os.getenv("MONGODB_URL"))
db = client["helpon_db"]

email = sys.argv[1] if len(sys.argv) > 1 else "testuser@example.com"
user = db.users.find_one({"email": email})

if user:
    print(f"Points for {email}: {user.get('points', 0)}, Helps: {user.get('helps_provided', 0)}")
else:
    print(f"User {email} not found.")
