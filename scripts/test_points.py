from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv("d:/HelpOn/.env")
client = MongoClient(os.getenv("MONGODB_URL"))
db = client["helpon_db"]
user = db.users.find_one({"email": "bharani2008india@gmail.com"})
if user:
    print(f"Points: {user.get('points', 0)}, Helps: {user.get('helps_provided', 0)}")
else:
    print("User not found.")
