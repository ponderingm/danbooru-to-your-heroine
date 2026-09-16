"""
tag_classifier.py
=================
タグのセマンティックスロット（7大スロット ＆ サブプロパティ体系）を判定するコアモジュール。
Base層 (src/rules/tags_classification_base.json) と
User層 (database/tags_classification_cache.json) をメモリ上で高速マージし、
未知タグ遭遇時にはオンデマンドでLLM推論を行って自動キャッシュ蓄積する。
"""

import json
import os
import re
import sys
import threading
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_DB_PATH = PROJECT_ROOT / "src" / "rules" / "tags_classification_base.json"
USER_DB_PATH = PROJECT_ROOT / "database" / "tags_classification_user.json"
CACHE_DB_PATH = PROJECT_ROOT / "database" / "tags_classification_cache.json"
PROMPT_FILE = PROJECT_ROOT / "src" / "prompts" / "tag_classification_system_instruction.md"

VALID_PARENT_SLOTS = {
    "meta_quality",
    "subject",
    "character_dna",
    "costume",
    "accessories",
    "action_pose",
    "environment",
}


class TagClassifier:
    """
    自己増殖型ハイブリッドタグ分類エンジン
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(TagClassifier, cls).__new__(cls)
                cls._instance._init_engine()
            return cls._instance

    def _init_engine(self):
        self._db: Dict[str, str] = {}
        self._system_instruction: str = ""
        self._file_lock = threading.Lock()
        self.reload()

    def reload(self):
        """Base層、User層、Cache層の辞書を再読込してメモリ展開する"""
        with self._file_lock:
            new_db = {}
            # 1. Base層（Git管理・普遍マスター辞書）
            if BASE_DB_PATH.exists():
                try:
                    base_data = json.loads(BASE_DB_PATH.read_text(encoding="utf-8"))
                    new_db.update(base_data)
                except Exception as e:
                    print(f"Warning: Failed to load Base tag classification DB: {e}")

            # 2. User層（ローカル固有設定・マニフェスト由来・.gitignore）
            if USER_DB_PATH.exists():
                try:
                    user_data = json.loads(USER_DB_PATH.read_text(encoding="utf-8"))
                    new_db.update(user_data)
                except Exception as e:
                    print(f"Warning: Failed to load User tag classification DB: {e}")

            # 3. Cache層（オンデマンド自動学習キャッシュ・.gitignore）
            if CACHE_DB_PATH.exists():
                try:
                    cache_data = json.loads(CACHE_DB_PATH.read_text(encoding="utf-8"))
                    new_db.update(cache_data)
                except Exception as e:
                    print(f"Warning: Failed to load Cache tag classification DB: {e}")

            self._db = new_db

            # プロンプト指示書の読込
            if PROMPT_FILE.exists():
                self._system_instruction = PROMPT_FILE.read_text(encoding="utf-8")

    def get_slot(self, tag: str, fallback_llm: bool = False) -> Optional[str]:
        """
        単一タグのスロット（例: 'character_dna.hair.color'）を取得する。
        未登録かつ fallback_llm=True の場合はLLMで推論してキャッシュに保存する。
        """
        cleaned = tag.strip().lower()
        if not cleaned:
            return None

        # 決定論的ルール（自明なプレフィックスの即時判定）
        rule_slot = self._check_deterministic_rules(cleaned)
        if rule_slot:
            return rule_slot

        # メモリ内ルックアップ (O(1))
        if cleaned in self._db:
            return self._db[cleaned]

        if not fallback_llm:
            return None

        # オンデマンドLLM推論
        classified = self.classify_tags([cleaned], fallback_llm=True)
        return classified.get(cleaned)

    def classify_tags(self, tags: List[str], fallback_llm: bool = False) -> Dict[str, str]:
        """
        複数タグのスロットを一括判定する。
        未知タグが存在し fallback_llm=True の場合はまとめてLLM推論を行う。
        """
        results: Dict[str, str] = {}
        missing: List[str] = []

        for raw_t in tags:
            t = raw_t.strip().lower()
            if not t:
                continue

            rule_slot = self._check_deterministic_rules(t)
            if rule_slot:
                results[t] = rule_slot
                continue

            if t in self._db:
                results[t] = self._db[t]
            else:
                missing.append(t)

        if not missing or not fallback_llm:
            return results

        # 未知タグをLLMで推論
        inferred = self._infer_tags_llm(missing)
        if inferred:
            with self._file_lock:
                self._save_to_cache(inferred)
            results.update(inferred)

        return results

    def get_parent_slot(self, tag: str, fallback_llm: bool = False) -> str:
        """
        タグの親スロット名（例: 'character_dna', 'costume'）を返す。
        未知の場合は 'unknown' を返す。
        """
        slot = self.get_slot(tag, fallback_llm=fallback_llm)
        if slot:
            return slot.split(".")[0]
        return "unknown"

    def _check_deterministic_rules(self, tag: str) -> Optional[str]:
        """自明なパターンに対するルールベース即時判定"""
        if tag.startswith("@") or tag.startswith("drawn by"):
            return "meta_quality.artist"
        if tag.startswith("score_"):
            return "meta_quality.quality"
        if tag in ("1girl", "solo", "2girls", "multiple girls", "1boy"):
            return "subject.count"
        if tag in ("masterpiece", "best quality", "highly detailed"):
            return "meta_quality.quality"
        return None

    def _infer_tags_llm(self, tags: List[str]) -> Dict[str, str]:
        """LLM (Gemini または Ollama) を用いて未知タグを一括推論する"""
        has_gemini = bool(os.environ.get("GEMINI_API_KEY") or getattr(config, "GEMINI_API_KEY", None))
        try:
            if has_gemini:
                return self._infer_gemini(tags)
            else:
                return self._infer_ollama(tags)
        except Exception as e:
            print(f"Warning: LLM tag classification failed for {tags}: {e}")
            return {}

    def _infer_gemini(self, tags: List[str]) -> Dict[str, str]:
        key = os.environ.get("GEMINI_API_KEY") or getattr(config, "GEMINI_API_KEY", None)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"

        payload = {
            "contents": [{"parts": [{"text": f"以下のタグリストを分類してください:\n{json.dumps({'tags_to_classify': tags}, ensure_ascii=False)}"}]}],
            "systemInstruction": {"parts": [{"text": self._system_instruction}]},
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})

        with urllib.request.urlopen(req, timeout=30) as resp:
            res = json.loads(resp.read().decode("utf-8"))

        raw_text = res["candidates"][0]["content"]["parts"][0]["text"].strip()
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```[a-zA-Z]*\n", "", raw_text)
            raw_text = re.sub(r"\n```$", "", raw_text).strip()
        data = json.loads(raw_text)
        return self._validate_inferred(data)

    def _infer_ollama(self, tags: List[str]) -> Dict[str, str]:
        url = "http://127.0.0.1:11434/api/generate"
        payload = {
            "model": "qwen2.5:latest",
            "system": self._system_instruction,
            "prompt": f"以下のタグリストを分類してください:\n{json.dumps({'tags_to_classify': tags}, ensure_ascii=False)}",
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.1},
        }
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})

        with urllib.request.urlopen(req, timeout=45) as resp:
            res = json.loads(resp.read().decode("utf-8"))

        raw_text = res.get("response", "").strip()
        data = json.loads(raw_text)
        return self._validate_inferred(data)

    def _validate_inferred(self, raw_dict: Dict[str, Any]) -> Dict[str, str]:
        valid = {}
        for t, slot in raw_dict.items():
            if isinstance(t, str) and isinstance(slot, str):
                cl_tag = t.strip().lower()
                cl_slot = slot.strip().lower()
                parent = cl_slot.split(".")[0]
                if parent in VALID_PARENT_SLOTS:
                    valid[cl_tag] = cl_slot
        return valid

    def _save_to_cache(self, new_entries: Dict[str, str]):
        """User層キャッシュファイルへ差分追記してメモリ更新"""
        self._db.update(new_entries)
        CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        current_cache = {}
        if CACHE_DB_PATH.exists():
            try:
                current_cache = json.loads(CACHE_DB_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        current_cache.update(new_entries)
        CACHE_DB_PATH.write_text(json.dumps(current_cache, ensure_ascii=False, indent=2), encoding="utf-8")


# シングルトンインスタンス
classifier = TagClassifier()
