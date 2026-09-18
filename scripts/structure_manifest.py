"""
structure_manifest.py
=====================
既存の画像マニフェスト (database/generated_manifest.json) を読み込み、
構築したタグ分類・ソートエンジンを用いて、全エントリーのプロンプトを
セマンティックスロット構造化＆黄金順ソートした拡張マニフェスト
(database/generated_manifest_structured.json) を生成するテストスクリプト。
"""

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# プロジェクトルート
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tag_classifier import classifier
from prompt_sorter import sorter

INPUT_MANIFEST = PROJECT_ROOT / "database" / "generated_manifest.json"
OUTPUT_MANIFEST = PROJECT_ROOT / "database" / "generated_manifest_structured.json"

PARENT_SLOTS = [
    "meta_quality",
    "subject",
    "character_dna",
    "costume",
    "accessories",
    "action_pose",
    "environment",
    "unknown",
]


def structure_single_prompt(prompt: str) -> Dict[str, Any]:
    """1件のプロンプトをスロット構造化＆黄金順ソートする"""
    raw_tags = [t.strip() for t in prompt.split(",") if t.strip()]
    if not raw_tags:
        return {
            "sorted_prompt": "",
            "structured_slots": {p: [] for p in PARENT_SLOTS},
            "detailed_slots": {},
            "coverage": 100.0,
        }

    # 黄金順ソート
    sorted_tags = sorter.sort_tags(raw_tags, fallback_llm=False)
    sorted_prompt = ", ".join(sorted_tags)

    # スロット分類マップ
    slot_map = classifier.classify_tags(sorted_tags, fallback_llm=False)

    structured_slots: Dict[str, List[str]] = {p: [] for p in PARENT_SLOTS}
    detailed_slots: Dict[str, List[str]] = {}
    known_count = 0

    for t in sorted_tags:
        slot = slot_map.get(t.lower())
        if slot:
            known_count += 1
            parent = slot.split(".")[0]
            structured_slots.setdefault(parent, []).append(t)
            detailed_slots.setdefault(slot, []).append(t)
        else:
            structured_slots["unknown"].append(t)
            detailed_slots.setdefault("unknown", []).append(t)

    coverage = round((known_count / len(sorted_tags)) * 100, 1)

    return {
        "sorted_prompt": sorted_prompt,
        "structured_slots": structured_slots,
        "detailed_slots": detailed_slots,
        "coverage": coverage,
    }


def main():
    if not INPUT_MANIFEST.exists():
        print(f"エラー: マニフェストファイルが存在しません: {INPUT_MANIFEST}")
        sys.exit(1)

    print(f"📂 マニフェスト読み込み中: {INPUT_MANIFEST}")
    data = json.loads(INPUT_MANIFEST.read_text(encoding="utf-8"))
    total_entries = len(data)
    print(f"読み込み完了: {total_entries:,} 件のエントリーを構造化します...")

    t0 = time.time()
    structured_manifest = []
    total_coverage = 0.0

    for idx, entry in enumerate(data):
        prompt = entry.get("prompt", "")
        res = structure_single_prompt(prompt)

        new_entry = dict(entry)
        new_entry["sorted_prompt"] = res["sorted_prompt"]
        new_entry["structured_slots"] = res["structured_slots"]
        new_entry["detailed_slots"] = res["detailed_slots"]
        new_entry["slot_coverage"] = res["coverage"]
        total_coverage += res["coverage"]

        structured_manifest.append(new_entry)

        if (idx + 1) % 1000 == 0 or (idx + 1) == total_entries:
            print(f"  [{idx + 1:,}/{total_entries:,}] 構造化完了...")

    dt = time.time() - t0
    avg_coverage = total_coverage / total_entries

    OUTPUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MANIFEST.write_text(json.dumps(structured_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    file_size_mb = OUTPUT_MANIFEST.stat().st_size / (1024 * 1024)

    print(f"\n🎉 構造化マニフェスト生成完了！ ({dt:.2f}秒)")
    print(f"出力ファイル: {OUTPUT_MANIFEST} ({file_size_mb:.2f} MB)")
    print(f"平均スロット分類カバー率: {avg_coverage:.2f}%")

    # サンプル1件のビフォーアフター表示
    sample = structured_manifest[0]
    print("\n--- [サンプルエントリー (ID: {}) の構造化結果] ---".format(sample.get("id", "sample")))
    print("【元プロンプト (Raw)】:")
    print(" ", sample.get("prompt")[:120], "...")
    print("\n【黄金順ソート後 (Sorted)】:")
    print(" ", sample.get("sorted_prompt")[:120], "...")
    print("\n【スロット構造 (Structured Slots)】:")
    for parent, tags in sample.get("structured_slots", {}).items():
        if tags:
            print(f"  - {parent:<15}: {tags}")


if __name__ == "__main__":
    main()
