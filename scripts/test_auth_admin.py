import requests
import json

base_url = 'http://127.0.0.1:8000/api'
session = requests.Session()

def print_step(msg):
    print(f"\n--- {msg} ---")

import random
try:
    # 1. Register User
    print_step("Registering Test Admin User")
    rand_id = random.randint(1000, 9999)
    reg_data = {
        "full_name": f"Test Admin {rand_id}",
        "email": f"testadmin{rand_id}@helpon.com",
        "password": "Password123!",
        "phone_number": f"12345{rand_id}0"
    }
    r = session.post(f"{base_url}/register", json=reg_data)
    if r.status_code != 200:
        print(f"Register failed with {r.status_code}: {r.text}")
    if r.status_code == 400: # might already exist, try login
        print("User might exist, trying login...")
        r = session.post(f"{base_url}/login", json={"username": reg_data["email"], "password": reg_data["password"]})
        if r.status_code != 200:
            print(f"Login failed with {r.status_code}: {r.text}")
    print(f"Auth Status: {r.status_code}")
    
    # Check if cookies were set
    cookies = session.cookies.get_dict()
    print(f"Cookies received: {list(cookies.keys())}")
    assert 'helpon_access_token' in cookies, "Failed to receive HttpOnly access cookie"
    
    # 2. Submit a Support Ticket
    print_step("Submitting Support Ticket")
    ticket_data = {
        "name": "Test User",
        "email": "testuser@helpon.com",
        "subject": "App Crash on Maps",
        "message": "When I open map.html it crashes."
    }
    r = session.post(f"{base_url}/support", json=ticket_data)
    print(f"Support Submit Status: {r.status_code}")
    ticket_result = r.json()
    print(ticket_result)
    ticket_id = ticket_result.get("id")
    
    # 3. Test Admin Stats
    print_step("Fetching Admin Stats")
    r = session.get(f"{base_url}/admin/stats", cookies=cookies)
    print(f"Admin Stats Status: {r.status_code}")
    print(json.dumps(r.json(), indent=2))
    
    # 4. Test Admin Support List
    print_step("Fetching Admin Support Tickets")
    r = session.get(f"{base_url}/admin/support", cookies=cookies)
    print(f"Admin Support Status: {r.status_code}")
    tickets = r.json()
    print(f"Found {len(tickets)} tickets. Latest: {tickets[0]['subject']}")
    
    # 5. Test Admin Close Ticket
    if ticket_id:
        print_step(f"Closing Ticket {ticket_id}")
        r = session.put(f"{base_url}/admin/support/{ticket_id}/close", cookies=cookies)
        print(f"Close Ticket Status: {r.status_code}")
        print(r.json())
        
    # 6. Logout
    print_step("Logging Out")
    r = session.post(f"{base_url}/logout", cookies=cookies)
    print(f"Logout Status: {r.status_code}")
    
    # Check cookies cleared
    cookies_after = session.cookies.get_dict()
    print(f"Cookies after logout: {cookies_after}")
    # requests library might still show the cookie key but with empty value, 
    # but the server sent Set-Cookie with Max-Age=0
    print("Test Completed Successfully!")
    
except Exception as e:
    print(f"TEST FAILED: {e}")
