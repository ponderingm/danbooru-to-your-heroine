"""
prompt_sorter.py
================
7大スロット＆サブプロパティ体系に基づき、画像生成モデル（Illustrious / Anima / SDXL）
のText Encoderが最も能力を発揮する「黄金の整列順」へプロンプトを全自動ソート・最適化するエンジン。
"""

from typing import Dict, List, Optional, Tuple
from tag_classifier import classifier

# 黄金のデフォルト整列順（スロットパス ➜ ソート優先度ランク）
# 数値が小さいほどプロンプトの先頭（強いアテンション領域）に配置される
SLOT_ORDER_RANKS = {
    # 1. 品質・メタ・絵師
    "meta_quality.quality": 10,
    "meta_quality.artist": 20,
    "meta_quality.format": 30,

    # 2. 主体・人数
    "subject.count": 100,
    "subject.gender": 110,

    # 3. ヒロインDNA（肉体・髪・顔）
    "character_dna.hair.color": 200,
    "character_dna.hair.style": 210,
    "character_dna.hair.feature": 220,
    "character_dna.face.eyes": 230,
    "character_dna.face.marks": 240,
    "character_dna.body.skin": 250,
    "character_dna.body.breasts": 260,
    "character_dna.body.build": 270,
    "character_dna.body.marks": 280,

    # 4. 衣装レイヤー（全身 ➜ 上 ➜ 下 ➜ 外 ➜ 内 ➜ 脚 ➜ 足）
    "costume.full_body": 300,
    "costume.top": 310,
    "costume.bottom": 320,
    "costume.outer": 330,
    "costume.inner": 340,
    "costume.legwear": 350,
    "costume.footwear": 360,

    # 5. 装飾品・小物（頭 ➜ 目 ➜ 首 ➜ 腕 ➜ 体 ➜ 宝飾 ➜ 道具）
    "accessories.head": 400,
    "accessories.eyes": 410,
    "accessories.neck": 420,
    "accessories.arms": 430,
    "accessories.body": 440,
    "accessories.jewelry": 450,
    "accessories.item": 460,

    # 6. 表情・ポーズ・構図・行為
    "action_pose.expression": 500,
    "action_pose.gaze": 510,
    "action_pose.pose": 520,
    "action_pose.framing": 530,
    "action_pose.interaction": 540,

    # 7. 背景・環境・ライティング
    "environment.location": 600,
    "environment.time_weather": 610,
    "environment.lighting": 620,
    "environment.effects": 630,
    "environment.background": 640,
}

# 未知スロットのデフォルトランク（末尾の手前に配置）
DEFAULT_UNKNOWN_RANK = 900


class PromptSorter:
    """プロンプト最適整列ソーター"""

    def __init__(self):
        self.classifier = classifier

    def get_slot_rank(self, slot_path: Optional[str]) -> int:
        """スロットパスからソート順序ランクを取得する"""
        if not slot_path:
            return DEFAULT_UNKNOWN_RANK
        if slot_path in SLOT_ORDER_RANKS:
            return SLOT_ORDER_RANKS[slot_path]
        
        # 親スロット単位での大まかなフォールバック
        parent = slot_path.split(".")[0]
        parent_map = {
            "meta_quality": 50,
            "subject": 120,
            "character_dna": 290,
            "costume": 370,
            "accessories": 470,
            "action_pose": 550,
            "environment": 650,
        }
        return parent_map.get(parent, DEFAULT_UNKNOWN_RANK)

    def sort_tags(
        self,
        tags: List[str],
        model: str = "illustrious",
        fallback_llm: bool = False,
    ) -> List[str]:
        """
        タグリストをセマンティックスロット順にソートして返却する。
        重複タグは最初の優先位置を保ったまま排除する。
        """
        if not tags:
            return []

        # 1. タグのクリーニングと重複除去
        seen = set()
        clean_tags = []
        for t in tags:
            norm = t.strip()
            if not norm:
                continue
            key = norm.lower()
            if key not in seen:
                seen.add(key)
                clean_tags.append(norm)

        # 2. 一括スロット判定
        slot_map = self.classifier.classify_tags(clean_tags, fallback_llm=fallback_llm)

        # 3. 各タグにソートキーを付与
        # (スロットランク, 元の出現インデックス) のタプルで安定ソート
        indexed_tags = []
        for idx, tag in enumerate(clean_tags):
            slot = slot_map.get(tag.lower())
            rank = self.get_slot_rank(slot)
            indexed_tags.append((rank, idx, tag))

        indexed_tags.sort(key=lambda x: (x[0], x[1]))
        return [tag for _, _, tag in indexed_tags]

    def sort_prompt(
        self,
        prompt: str,
        model: str = "illustrious",
        fallback_llm: bool = False,
        delimiter: str = ", ",
    ) -> str:
        """
        カンマ区切りのプロンプト文字列を受け取り、黄金順に整列した文字列を返却する。
        """
        if not prompt or not prompt.strip():
            return ""

        tags = [t.strip() for t in prompt.split(",") if t.strip()]
        sorted_tags = self.sort_tags(tags, model=model, fallback_llm=fallback_llm)
        return delimiter.join(sorted_tags)

    def explain_slots(self, prompt: str, fallback_llm: bool = False) -> Dict[str, List[str]]:
        """
        プロンプト内のタグがどのスロットに分類されているかをスロット別グループで返却（デバッグ・UI用）
        """
        tags = [t.strip() for t in prompt.split(",") if t.strip()]
        slot_map = self.classifier.classify_tags(tags, fallback_llm=fallback_llm)
        grouped: Dict[str, List[str]] = {}

        for t in tags:
            slot = slot_map.get(t.lower(), "unknown")
            grouped.setdefault(slot, []).append(t)

        return grouped


# シングルトン
sorter = PromptSorter()
