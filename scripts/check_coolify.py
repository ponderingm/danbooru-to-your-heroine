import subprocess
import json
import urllib.request
import urllib.error

def get_coolify_token():
    cmd = [
        "docker", "exec", "coolify", "php", "artisan", "tinker", "--execute",
        "$u = App\\Models\\User::first();\n"
        "$token = $u->tokens()->where('name', 'antigravity_token')->first();\n"
        "if (!$token) {\n"
        "    $t = $u->createToken('antigravity_token', ['*']);\n"
        "    $t->accessToken->team_id = 0;\n"
        "    $t->accessToken->save();\n"
        "    echo 'TOKEN:' . $t->plainTextToken . PHP_EOL;\n"
        "} else {\n"
        "    echo 'EXISTS' . PHP_EOL;\n"
        "}"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    print("Tinker output:", res.stdout)
    if "EXISTS" in res.stdout:
        # Re-create token to get plainTextToken
        cmd_new = [
            "docker", "exec", "coolify", "php", "artisan", "tinker", "--execute",
            "$u = App\\Models\\User::first();\n"
            "$u->tokens()->where('name', 'antigravity_token')->delete();\n"
            "$t = $u->createToken('antigravity_token', ['*']);\n"
            "$t->accessToken->team_id = 0;\n"
            "$t->accessToken->save();\n"
            "echo 'TOKEN:' . $t->plainTextToken . PHP_EOL;"
        ]
        res_new = subprocess.run(cmd_new, capture_output=True, text=True)
        print("Tinker new output:", res_new.stdout)
        for line in res_new.stdout.splitlines():
            if line.startswith("TOKEN:"):
                return line.replace("TOKEN:", "").strip()
    else:
        for line in res.stdout.splitlines():
            if line.startswith("TOKEN:"):
                return line.replace("TOKEN:", "").strip()
    return None

def test_api(token):
    url = "http://127.0.0.1:8000/api/v1/projects"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            print("Projects:", json.dumps(data, indent=2))
            return data
    except Exception as e:
        print("API test failed:", e)
        return None

if __name__ == "__main__":
    token = get_coolify_token()
    print("Token obtained:", token[:10] if token else "None")
    if token:
        test_api(token)
