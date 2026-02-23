import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("d:/HelpOn/.env")
client = MongoClient(os.getenv("MONGODB_URL"))
db = client["helpon_db"]

# Give the user 'bharani2008india@gmail.com' exactly 1250 points
db.users.update_one({"email": "bharani2008india@gmail.com"}, {"$set": {"points": 1250}})

user = db.users.find_one({"email": "bharani2008india@gmail.com"})
print(f"Points updated successfully! Current points: {user.get('points')}")
