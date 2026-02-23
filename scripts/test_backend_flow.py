import urllib.request
import urllib.error
import json
import os

API_BASE = "http://localhost:8000/api"

# 1. Login
try:
    login_payload = json.dumps({"username": "bharani2008india@gmail.com", "password": "@bharani2008"}).encode('utf-8')
    req = urllib.request.Request(f"{API_BASE}/login", 
        data=login_payload, 
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        token = json.loads(resp.read())["access_token"]
except urllib.error.HTTPError as e:
    print(f"Login HTTP Error {e.code}: {e.read().decode('utf-8')}")
    exit(1)

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

try:
    # 2. Create SOS
    sos_data = json.dumps({
        "type": "health",
        "description": "Test Backend Flow",
        "lat": 28.6139,
        "lon": 77.209
    }).encode('utf-8')
    req = urllib.request.Request(f"{API_BASE}/emergency/sos", data=sos_data, headers=headers)
    with urllib.request.urlopen(req) as resp:
        sos_id = json.loads(resp.read())["id"]
        print(f"Created SOS: {sos_id}")

    # 3. Accept SOS
    req = urllib.request.Request(f"{API_BASE}/emergency/{sos_id}/accept", data=b'', headers=headers)
    with urllib.request.urlopen(req) as resp:
        print(f"Accepted SOS: {resp.status}")

    # 4. Complete SOS
    req = urllib.request.Request(f"{API_BASE}/emergency/{sos_id}/complete", data=b'', headers=headers, method="PUT")
    with urllib.request.urlopen(req) as resp:
        print(f"Completed SOS: {json.loads(resp.read())}")

    # 5. Check points using the test_points script
    os.system("python test_points.py")

except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}")
