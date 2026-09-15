import urllib.request
import json
import time

TOKEN = "5|i4xcNLJ8ZWYfNEqln2aSOQiHGdahsoX2gOSGBwLB976e1178"
BASE = "http://127.0.0.1:8000/api/v1"
DEP_UUID = "jsbx8zt4goxuboqz0mez889m"

def check_deployment():
    req = urllib.request.Request(
        f"{BASE}/deployments/{DEP_UUID}",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json"
        }
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        print(f"Status: {data.get('status')}")
        logs = data.get("logs", "")
        if logs:
            print("Logs tail:")
            print("\n".join(logs.splitlines()[-25:]))

if __name__ == "__main__":
    check_deployment()
