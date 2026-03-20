import requests
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv("d:/HelpOn/.env")
client = MongoClient(os.getenv("MONGODB_URL"))
db = client["helpon_db"]

API_BASE = "http://localhost:8000/api"

def print_step(msg):
    print(f"\n--- {msg} ---")

try:
    session = requests.Session()

    print_step("1. Registering/Logging in User 1 (Requester)")
    user1_email = "requester@helpon.com"
    r = session.post(f"{API_BASE}/register", json={
        "full_name": "Requester Flow", "email": user1_email, 
        "password": "Password123!", "phone_number": "0000000001"
    })
    if r.status_code == 400:
        r = session.post(f"{API_BASE}/login", json={"username": user1_email, "password": "Password123!"})
    
    assert r.status_code == 200, f"Login failed for {user1_email}: {r.status_code} {r.text}"
    cookies1 = session.cookies.get_dict()

    print_step("2. Creating SOS (User 1)")
    r = session.post(f"{API_BASE}/emergency/sos", json={
        "type": "health", "description": "Needs immediate medical help",
        "lat": 28.6139, "lon": 77.209
    }, cookies=cookies1)
    if r.status_code != 200:
        print("SOS creation failed!", r.status_code, r.text)
        exit(1)
        
    sos_id = r.json()["id"]
    print(f"Created SOS: {sos_id}")

    print_step("3. Registering/Logging in User 2 (Helper)")
    session2 = requests.Session()
    user2_email = "helper@helpon.com"
    r = session2.post(f"{API_BASE}/register", json={
        "full_name": "Helper Flow", "email": user2_email, 
        "password": "Password123!", "phone_number": "0000000002"
    })
    if r.status_code == 400:
        r = session2.post(f"{API_BASE}/login", json={"username": user2_email, "password": "Password123!"})
    
    assert r.status_code == 200, f"Login failed for {user2_email}: {r.status_code} {r.text}"
    cookies2 = session2.cookies.get_dict()
    
    # Check baseline points for User 2
    user2_doc = db.users.find_one({"email": user2_email})
    baseline_points = user2_doc.get("points", 0)
    baseline_helps = user2_doc.get("helps_given", 0)

    print_step("4. Accepting SOS (User 2)")
    r = session2.post(f"{API_BASE}/emergency/{sos_id}/accept", cookies=cookies2)
    print("Accept Status:", r.status_code, r.text)

    print_step("5. Completing SOS (User 1)")
    r = session.put(f"{API_BASE}/emergency/{sos_id}/complete", cookies=cookies1)
    print("Complete Status:", r.status_code, r.text)

    print_step("6. Verifying points (User 2)")
    user2_doc_after = db.users.find_one({"email": user2_email})
    new_points = user2_doc_after.get("points", 0)
    new_helps = user2_doc_after.get("helps_given", 0)
    
    print(f"Baseline: Points={baseline_points}, Helps={baseline_helps}")
    print(f"Current:  Points={new_points}, Helps={new_helps}")
    
    if new_points - baseline_points == 50 and new_helps - baseline_helps == 1:
        print("✅ Gamification logic verified successfully!")
    else:
        print("❌ Gamification logic failed. Mismatch detected.")

except Exception as e:
    print(f"Error: {e}")
