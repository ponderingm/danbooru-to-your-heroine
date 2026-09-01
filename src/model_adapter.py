import re

# Illustrious記法のrating:xxxタグ(danbooruのg/s/q/e相当) → Anima記法(safe/sensitive/nsfw/explicit)
ANIMA_RATING_MAP = {
    "general": "safe",
    "sensitive": "sensitive",
    "questionable": "nsfw",
    "explicit": "explicit",
}

def adapt_prompt(raw_prompt, model_type="illustrious", is_h_scene=True):
    """
    モデルアーキテクチャに合わせてプロンプト構文を最適化
    - illustrious / netayume: SDXL Danbooru tags + Artist:Name
    - anima: Qwen3 DiT tags + @Artist + space separation + score_9/explicit + underscore removal
    - animagine: Animagine tags + masterpiece + rating:explicit
    """
    m = model_type.lower()
    p = raw_prompt

    if "anima" in m:
        # --- 🌟 Anima v1.0 DiT ---
        p = re.sub(r"Artist:\s*([^,]+)", r"@\1", p, flags=re.IGNORECASE)
        p = re.sub(r"\b1girl\b", "1 girl", p, flags=re.IGNORECASE)
        p = re.sub(r"\b1boy\b", "1 boy", p, flags=re.IGNORECASE)
        p = re.sub(r"\b2girls\b", "2 girls", p, flags=re.IGNORECASE)

        # score_9 などのスコアタグを保護してアンダースコアを半角スペースに展開
        p = re.sub(r"score_(\d+)", r"___SCORE_\1___", p, flags=re.IGNORECASE)
        p = p.replace("_", " ")
        p = re.sub(r"___SCORE_(\d+)___", r"score_\1", p, flags=re.IGNORECASE)
        p = re.sub(r",\s*", ", ", p)

        # 本文に埋め込まれたIllustrious記法のrating:xxxタグ(g/s/q/e由来)をAnima記法へ変換し、
        # 元タグ(Animaでは無効な構文)は本文から除去する。無ければ従来通りis_h_sceneの二値で判定
        rating_match = re.search(r"rating:\s*(general|sensitive|questionable|explicit)", p, flags=re.IGNORECASE)
        if rating_match:
            rating = ANIMA_RATING_MAP[rating_match.group(1).lower()]
            p = re.sub(r"rating:\s*(general|sensitive|questionable|explicit)\s*,?\s*", "", p, flags=re.IGNORECASE)
            p = re.sub(r",\s*,", ",", p).strip(" ,")
        else:
            rating = "explicit" if is_h_scene else "safe"

        return f"score_9, score_8, score_7, masterpiece, best quality, {rating}, {p}"

    elif "animagine" in m:
        # --- 🪄 Animagine XL ---
        rating = "rating:explicit" if is_h_scene else "rating:general"
        return f"masterpiece, best quality, very aesthetic, absurdres, {rating}, {p}"

    else:
        # --- 🎨 Illustrious-XL / NetaYume ---
        if not p.startswith("masterpiece"):
            p = f"masterpiece, best quality, amazing quality, very aesthetic, absurdres, {p}"
        return p

def get_negative_prompt(model_type="illustrious"):
    m = model_type.lower()
    if "anima" in m:
        return "worst quality, low quality, score_1, score_2, score_3, 6 fingers, 6 toes, ai-generated, bad eyes, bad pupils, bad iris, bad hands, bad fingers, watermark, patreon logo, text, speech bubble, sound effects, logo, signature, scenery, distant character, small person, tiny figure, landscape focus, empty scene, wide panoramic view, background emphasis"
    elif "animagine" in m:
        return "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, logo, speech bubble, sound effects, blurry, scenery, distant character, small person"
    else:
        # 🎨 Illustrious-XL: Complete text, watermark, comic, speech bubble banishment
        return "worst quality, low quality, bad anatomy, bad hands, bad eyes, text, letters, font, logo, watermark, signature, username, artist name, copyright name, web address, patreon logo, twitter username, speech bubble, dialogue, commentary, sound effects, subtitles, comic, manga, page, panel, border, frame, ui, split screen, censored, blurry"
