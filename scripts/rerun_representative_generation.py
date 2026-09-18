import requests
import time
import json
import sys

PREVIEW_URL = "http://1.danbooru.hannya.org"

TARGET_POST_IDS = [
    "1886630",
    "311329",
    "2315348",
    "4746599",
    "6667193",
]

def rerun_generation():
    print("=== Submitting 5 Representative Jobs with artist_mode=override ===")
    jobs = {}
    for pid in TARGET_POST_IDS:
        payload = {
            "url": f"https://danbooru.donmai.us/posts/{pid}",
            "heroine": "yukikaze",
            "backend": "anima_turbo_slow",
            "artist_mode": "override",
            "width": 832,
            "height": 1216
        }
        r = requests.post(f"{PREVIEW_URL}/generate", json=payload, timeout=10)
        jid = r.json().get("job_id")
        jobs[pid] = jid
        print(f"Queued Post {pid} -> Job {jid}")
        time.sleep(0.5)

    print("\nAll 5 jobs submitted. Monitoring progress...")
    completed = {}
    start_time = time.time()

    while len(completed) < len(jobs):
        for pid, jid in jobs.items():
            if pid in completed:
                continue
            try:
                r = requests.get(f"{PREVIEW_URL}/jobs/{jid}", timeout=5)
                data = r.json()
                status = data.get("status")
                if status == "done":
                    res = data.get("result", {})
                    files = res.get("files", [])
                    prompt = res.get("prompt", "")
                    elapsed = time.time() - start_time
                    print(f"[{elapsed:.1f}s] Post {pid}: DONE -> {files}")
                    print(f"  Prompt: {prompt[:120]}...")
                    completed[pid] = {
                        "job_id": jid,
                        "status": "done",
                        "files": files,
                        "prompt": prompt,
                    }
                elif status == "error":
                    err = data.get("error")
                    print(f"Post {pid}: ERROR -> {err}")
                    completed[pid] = {
                        "job_id": jid,
                        "status": "error",
                        "error": err
                    }
            except Exception as e:
                print(f"Polling error for {pid}: {e}")
        time.sleep(5)

    print("\nAll 5 jobs finished successfully!")
    with open("/home/pi/danbooru_yukikaze_tool/database/v3_representative_rerun_results.json", "w", encoding="utf-8") as f:
        json.dump(completed, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    rerun_generation()
