import json
import os
import sys
import time
from typing import Dict, List, Any

# ホスト上のモジュールを読み込み
sys.path.insert(0, os.path.abspath("src"))
import config
from danbooru_to_heroine import fetch_post, mutate_tags_to_heroine, build_prompt
from model_adapter import adapt_prompt
from site_adapters import UnifiedPost

MANIFEST_PATH = "/home/pi/danbooru_yukikaze_tool/database/generated_manifest.json"
CACHE_PATH = "/home/pi/danbooru_yukikaze_tool/database/danbooru_posts_cache.json"

def get_cached_post(post_id: str, cache: dict) -> UnifiedPost:
    if post_id in cache:
        c = cache[post_id]
        return UnifiedPost(
            post_id=c["post_id"],
            source_site=c.get("source_site", "danbooru"),
            url=c.get("url", f"https://danbooru.donmai.us/posts/{post_id}"),
            rating=c.get("rating", "general"),
            character_tags=c.get("character_tags", []),
            general_tags=c.get("general_tags", []),
            artist_tags=c.get("artist_tags", []),
            copyright_tags=c.get("copyright_tags", []),
            meta_tags=c.get("meta_tags", []),
            all_tags=c.get("all_tags", []),
        )
    try:
        post = fetch_post(post_id)
        cache[post_id] = {
            "post_id": post.post_id,
            "source_site": post.source_site,
            "url": post.url,
            "rating": post.rating,
            "character_tags": post.character_tags,
            "general_tags": post.general_tags,
            "artist_tags": post.artist_tags,
            "copyright_tags": post.copyright_tags,
            "meta_tags": post.meta_tags,
            "all_tags": post.all_tags,
        }
        time.sleep(0.15)  # レートリミット配慮
        return post
    except Exception as e:
        print(f"Fetch error for {post_id}: {e}")
        return None

def run_comparison():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    recent_100 = manifest[-100:]
    print(f"Loaded {len(recent_100)} entries for comparison.")

    cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    results = []
    multi_subject_count = 0

    for idx, entry in enumerate(recent_100):
        post_id = str(entry.get("post_id"))
        heroine_name = entry.get("heroine", "yukikaze")
        model = entry.get("model", "anima")
        v2_prompt = entry.get("prompt", "")

        post = get_cached_post(post_id, cache)
        if not post:
            continue

        adhoc_rules = {}
        for k in ("override_breasts", "override_skin", "override_costume", "override_art_style"):
            val = entry.get(k)
            if val and val != "default":
                adhoc_rules[k.replace("override_", "")] = val

        res = mutate_tags_to_heroine(
            post,
            heroine=heroine_name,
            include_artist=entry.get("include_artist", False),
            artist_mode=entry.get("artist_mode"),
            custom_artist=entry.get("custom_artist"),
            override_rules=adhoc_rules,
        )
        identity_tags, situation_tags, _removed = res[0], res[1], res[2]
        base_prompt = build_prompt(identity_tags, situation_tags, model_type=model, heroine_name=heroine_name)
        v3_prompt = adapt_prompt(base_prompt, model_type=model)

        v2_tags = [t.strip() for t in v2_prompt.split(",") if t.strip()]
        v3_tags = [t.strip() for t in v3_prompt.split(",") if t.strip()]

        is_multi = getattr(res, "is_multi_subject", False) or ("1boy" in v3_prompt or "2girls" in v3_prompt or "multiple girls" in v3_prompt)
        if is_multi:
            multi_subject_count += 1

        results.append({
            "idx": idx + 1,
            "post_id": post_id,
            "is_multi": is_multi,
            "v2_tag_count": len(v2_tags),
            "v3_tag_count": len(v3_tags),
            "tag_diff": len(v3_tags) - len(v2_tags),
            "v2_prompt": v2_prompt,
            "v3_prompt": v3_prompt,
            "image_urls": entry.get("image_urls", []),
        })

        if (idx + 1) % 25 == 0:
            print(f"Processed {idx + 1}/100 posts... (Multi-subject: {multi_subject_count})")

    # キャッシュ保存
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)

    print(f"\nCompleted comparison of {len(results)} posts.")
    print(f"Multi-subject detected: {multi_subject_count}")

    # 結果保存
    with open("/home/pi/danbooru_yukikaze_tool/database/v2_vs_v3_comparison_100.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return results

if __name__ == "__main__":
    run_comparison()
