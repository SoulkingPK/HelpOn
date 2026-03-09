import urllib.request
import urllib.parse
import json

url = "http://localhost:8000/api/login"
data = {"username": "test@example.com", "password": "password123"}
req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type':'application/json'}, method='POST')

try:
    response = urllib.request.urlopen(req)
    print("Status:", response.status)
    print("Headers:", response.headers)
    print("Body:", response.read().decode())
except urllib.error.URLError as e:
    print("Error:", e)
    if hasattr(e, 'code'):
        print("Status:", e.code)
    if hasattr(e, 'headers'):
        print("Headers:", e.headers)
    if hasattr(e, 'read'):
        print("Body:", e.read().decode())
