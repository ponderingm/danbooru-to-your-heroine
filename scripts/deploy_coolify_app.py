import os
import urllib.request
import urllib.error
import json
import time

TOKEN = os.environ.get("COOLIFY_TOKEN", "")
BASE = "http://127.0.0.1:8000/api/v1"
APP_UUID = "jfmbv96dl10h6obh1g25jlzz"

def coolify_request(endpoint, method="GET", payload=None):
    url = f"{BASE}/{endpoint.lstrip('/')}"
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTPError {e.code}: {e.read().decode()}")
        raise

def deploy():
    print(f"Deploying application {APP_UUID}...")
    res = coolify_request(f"deploy?uuid={APP_UUID}", method="POST")
    print("Deploy response:", res)
    return res

if __name__ == "__main__":
    deploy()
