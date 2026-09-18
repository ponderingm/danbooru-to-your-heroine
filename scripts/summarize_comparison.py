import json
import statistics

def summarize():
    with open("/home/pi/danbooru_yukikaze_tool/database/v2_vs_v3_comparison_100.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Total compared: {len(data)}")

    v2_tag_counts = [d["v2_tag_count"] for d in data]
    v3_tag_counts = [d["v3_tag_count"] for d in data]
    diffs = [d["tag_diff"] for d in data]

    print(f"v2 Tag Count: avg={statistics.mean(v2_tag_counts):.1f}, min={min(v2_tag_counts)}, max={max(v2_tag_counts)}")
    print(f"v3 Tag Count: avg={statistics.mean(v3_tag_counts):.1f}, min={min(v3_tag_counts)}, max={max(v3_tag_counts)}")
    print(f"Diff (v3 - v2): avg={statistics.mean(diffs):.1f}, min={min(diffs)}, max={max(diffs)}")

    # DNAの注入状況、置換状況のサンプル抽出
    # 特徴的な改善例（タグ順序の整理、重複排除、DNA補完）
    print("\n=== Sample 1 (Entry #1: post_id 1886630) ===")
    print("v2:", data[0]["v2_prompt"])
    print("v3:", data[0]["v3_prompt"])

    print("\n=== Sample 2 (Entry #50: post_id 4746599) ===")
    print("v2:", data[49]["v2_prompt"])
    print("v3:", data[49]["v3_prompt"])

    print("\n=== Sample 3 (Entry #100: post_id 6667193) ===")
    print("v2:", data[99]["v2_prompt"])
    print("v3:", data[99]["v3_prompt"])

if __name__ == "__main__":
    summarize()
