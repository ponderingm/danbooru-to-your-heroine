import requests
import time
import json
import sys

PREVIEW_URL = "http://1.danbooru.hannya.org"
PID = "7967741"

def main():
    print(f"=== Submitting Post {PID} (2girls yuri) to {PREVIEW_URL} ===")
    payload = {
        "url": f"https://danbooru.donmai.us/posts/{PID}",
        "heroine": "yukikaze",
        "backend": "anima_turbo_slow",
        "artist_mode": "override",
        "width": 832,
        "height": 1216
    }
    r = requests.post(f"{PREVIEW_URL}/generate", json=payload, timeout=10)
    data = r.json()
    jid = data.get("job_id")
    print(f"Queued Post {PID} -> Job {jid}")

    start_time = time.time()
    while True:
        try:
            r = requests.get(f"{PREVIEW_URL}/jobs/{jid}", timeout=5)
            job_data = r.json()
            status = job_data.get("status")
            elapsed = time.time() - start_time
            if status == "done":
                res = job_data.get("result", {})
                files = res.get("files", [])
                prompt = res.get("prompt", "")
                print(f"[{elapsed:.1f}s] Post {PID}: DONE -> {files}")
                print(f"Prompt:\n{prompt}")
                if files:
                    img_url = f"{PREVIEW_URL}/output/{files[0]}"
                    print(f"\nGenerated Image URL: {img_url}")
                break
            elif status == "error":
                print(f"[{elapsed:.1f}s] Post {PID}: ERROR -> {job_data.get('error')}")
                break
            else:
                print(f"[{elapsed:.1f}s] Status: {status}...")
        except Exception as e:
            print(f"Waiting... ({e})")
        time.sleep(3)

if __name__ == "__main__":
    main()
