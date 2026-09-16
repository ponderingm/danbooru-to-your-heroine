import os
import urllib.request
import urllib.error
import json

TOKEN = os.environ.get("COOLIFY_TOKEN", "")
BASE = "http://127.0.0.1:8000/api/v1"

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
        err_body = e.read().decode()
        print(f"HTTPError {e.code}: {err_body}")
        raise

def register_app():
    payload = {
        "project_uuid": "wk0ckc0wok44oososo80kwg4",
        "server_uuid": "c88o8wg44ks484cwgsooc8wc",
        "environment_name": "production",
        "github_app_uuid": "hkwk0cc8gcw80swscw0sow40",
        "git_repository": "ponderingm/ranbell_image",
        "git_branch": "main",
        "build_pack": "dockercompose",
        "name": "ranbell-gallery",
        "description": "Rich AI Image Gallery for Yukikaze Archive",
        "is_auto_deploy_enabled": True,
        "docker_compose_domains": [
            {
                "name": "frontend",
                "domain": "http://gallery.hannya.org"
            }
        ]
    }
    print("Registering private repo app in Coolify...")
    res = coolify_request("applications/private-github-app", method="POST", payload=payload)
    print("Registration response:", json.dumps(res, indent=2))
    return res

if __name__ == "__main__":
    register_app()
