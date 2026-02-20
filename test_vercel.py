import urllib.request
import urllib.error
import json

req = urllib.request.Request(
    'https://help-on.vercel.app/api/login',
    data=json.dumps({'username': 'test', 'password': 'test'}).encode(),
    headers={'Content-Type': 'application/json'}
)

try:
    urllib.request.urlopen(req)
except urllib.error.HTTPError as e:
    print(e.read().decode())
