import requests
import json

PREVIEW_URL = "http://1.danbooru.hannya.org"

def verify_v3_manifest():
    print(f"=== Testing /convert on {PREVIEW_URL} for v3 structured fields ===")
    payload = {
        "url": "https://danbooru.donmai.us/posts/7967741",
        "heroine": "yukikaze",
        "backend": "anima_turbo_slow",
        "multi_mode": "shared_costume",
    }
    r = requests.post(f"{PREVIEW_URL}/convert", json=payload, timeout=10)
    data = r.json()

    print(f"Status: {r.status_code}")
    print(f"Post ID: {data.get('post_id')}")
    print(f"Heroine: {data.get('heroine')}")
    print(f"Multi Mode: {data.get('multi_mode')}")
    print(f"Identity tags ({len(data.get('identity_tags', []))}): {data.get('identity_tags')}")
    print(f"Situation tags ({len(data.get('situation_tags', []))}): {data.get('situation_tags')[:5]}...")
    print(f"Removed tags ({len(data.get('removed_tags', []))}): {data.get('removed_tags')}")
    print(f"Slots mapped count: {len(data.get('slots', {}))}")
    sample_slots = {k: v for i, (k, v) in enumerate(data.get('slots', {}).items()) if i < 6}
    print(f"Sample slots: {json.dumps(sample_slots, ensure_ascii=False, indent=2)}")

    assert "identity_tags" in data, "Missing identity_tags"
    assert "situation_tags" in data, "Missing situation_tags"
    assert "removed_tags" in data, "Missing removed_tags"
    assert "slots" in data, "Missing slots"
    print("\n✅ Verification Successful: All V3 structured fields are present and active!")

if __name__ == "__main__":
    verify_v3_manifest()
