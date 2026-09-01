"""
danbooru_search_batch_generator.py
===================================
Danbooruの検索ワードでヒットした投稿を上から順に取得し、
danbooru_to_heroine.py と同じロジックでタグを config.py で定義したヒロインに
変換した上で、ComfyUI経由で連続的に画像生成するバッチスクリプト。

Usage:
    uv run python src/danbooru_search_batch_generator.py "micro_bikini"
    uv run python src/danbooru_search_batch_generator.py "santa_costume rating:explicit" --limit 30 --pages 2
    uv run python src/danbooru_search_batch_generator.py "school_uniform" --heroine rinko --model anima --no-nsfw
    uv run python src/danbooru_search_batch_generator.py "rating:explicit" --lucky
    uv run python src/danbooru_search_batch_generator.py "order:score rating:explicit micro_bikini beach 1girl" --limit 10
    uv run python src/danbooru_search_batch_generator.py "order:favcount swimsuit -competition_swimsuit" --all

事前準備:
    cp src/config.example.py src/config.py
    # src/config.py を自分の環境（ComfyUIのURL・保存先ディレクトリ・HEROINES等）に合わせて編集する
"""

import os
import re
import sys
import json
import time
import argparse

import requests

from danbooru_to_heroine import (
    DANBOORU_API_BASE, get_heroine_dna, mutate_tags_to_heroine, build_prompt,
)
from model_adapter import adapt_prompt, get_negative_prompt
from comfy_client import (
    compute_canvas_size, create_default_workflow, create_custom_workflow, create_anima_workflow,
    wait_for_comfyui, submit_and_wait,
)
import config

# src/ の1つ上（リポジトリルート）を基準にする。database/ はsrcの外に置く
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMFYUI_URL = config.COMFYUI_API_URL
# カスタムワークフロー用ComfyUIエンドポイント。設定は config.py を参照
CUSTOM_COMFY_URL = config.CUSTOM_COMFY_URL
# Anima v1.0 DiT用ComfyUIエンドポイント。設定は config.py を参照
ANIMA_COMFY_URL = config.ANIMA_COMFY_URL
OUTPUT_DIR = config.OUTPUT_DIR
WEB_OUTPUT_DIR = config.WEB_OUTPUT_DIR
PROGRESS_PATH = os.path.join(PROJECT_ROOT, "database", "danbooru_search_batch_progress.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(WEB_OUTPUT_DIR, exist_ok=True)


def resolve_comfy_url(model: str, use_custom: bool) -> str:
    """model/use_customから使用するComfyUIエンドポイントを決定する（animaはSDXL checkpointを使わないため専用エンドポイント）"""
    if "anima" in model.lower():
        return ANIMA_COMFY_URL
    return CUSTOM_COMFY_URL if use_custom else COMFYUI_URL


# ─────────────────────────────────────────────
# Danbooru 検索 API
# ─────────────────────────────────────────────

# ヒロインが複数人化する構図のみ除外。相手役（1boy等）は許可する
NON_SOLO_GIRL_TAGS = {
    "2girls", "3girls", "4girls", "5girls", "6+girls", "multiple girls",
}


def is_solo_girl(post: dict) -> bool:
    """投稿の一般タグに1girlが含まれ、女性が複数人写る構図でないかを判定する（相手役の男性・人外はOK）"""
    general_tags = set(t.replace("_", " ") for t in post.get("tag_string_general", "").split())
    if "1girl" not in general_tags:
        return False
    if general_tags & NON_SOLO_GIRL_TAGS:
        return False
    return True


# 実写・3DCG調は変換結果が低品質画像になりやすいため既定で除外する
REALISTIC_STYLE_TAGS = {
    "3d", "photorealistic", "realistic", "real_life", "photo_(medium)",
}


def is_realistic_style(post: dict) -> bool:
    """投稿が実写・3DCG調（photorealistic/3d等）かどうかを判定する"""
    general_tags = set(t.replace("_", " ") for t in post.get("tag_string_general", "").split())
    meta_tags = set(t.replace("_", " ") for t in post.get("tag_string_meta", "").split())
    style_tags = {t.replace("_", " ") for t in REALISTIC_STYLE_TAGS}
    return bool((general_tags | meta_tags) & style_tags)


def is_blacklisted(post: dict) -> bool:
    """config.GENERATION_BLACKLIST_TAGSに合致するタグ（例: グロ系）を含むかを判定する
    （自動バッチ生成専用のスキップ判定。手動変換(danbooru_to_heroine.py/⁄convert/⁄generate)には適用しない）"""
    blacklist = {t.replace("_", " ").lower() for t in getattr(config, "GENERATION_BLACKLIST_TAGS", set())}
    if not blacklist:
        return False
    post_tags = {t.replace("_", " ").lower() for t in post.get("tag_string", "").split()}
    return bool(post_tags & blacklist)


def search_posts(tags: str, limit: int, page: int, login: str = None, api_key: str = None) -> list:
    """タグ検索で投稿一覧を取得（サイト表示と同じ新着順=上から順）"""
    endpoint = f"{DANBOORU_API_BASE}/posts.json"
    params = {"tags": tags, "limit": limit, "page": page}
    if login and api_key:
        params["login"] = login
        params["api_key"] = api_key
    headers = {"User-Agent": "danbooru-to-your-heroine/1.0"}
    resp = requests.get(endpoint, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _tokenize_search_query(search_str: str):
    """検索文字列を order:タグ / キーワードタグ / rating:フィルタ / 除外タグ(-tag) に分解する"""
    order_tag = None
    keyword_tags = []
    ratings = set()
    excluded_tags = set()
    for tok in search_str.split():
        if tok.startswith("order:"):
            if order_tag is None:
                order_tag = tok
        elif tok.startswith("rating:"):
            code = tok.split(":", 1)[1][:1].lower()
            if code in "gsqe":
                ratings.add(code)
        elif tok.startswith("-") and len(tok) > 1:
            excluded_tags.add(tok[1:])
        else:
            keyword_tags.append(tok)
    return order_tag, keyword_tags, ratings, excluded_tags


def parse_search_query(search_str: str) -> tuple:
    """
    Danbooru匿名利用時の「1リクエスト最大2タグ」制限に合わせ、検索文字列をAPI送信用
    クエリ（order:+キーワード1個、またはキーワード最大2個）と、取得後に手元で判定する
    フィルタ（3個目以降のキーワード・rating:・除外タグ）に分割する。

    戻り値:
        api_query (str): Danbooru APIに渡すクエリ（空白区切り、最大2要素）
        local_filters (dict): required_tags / excluded_tags / ratings のセットを持つ
    """
    order_tag, keyword_tags, ratings, excluded_tags = _tokenize_search_query(search_str)

    api_tags = []
    if order_tag:
        api_tags.append(order_tag)
        if keyword_tags:
            api_tags.append(keyword_tags[0])
        required_tags = set(keyword_tags[1:])
    else:
        api_tags.extend(keyword_tags[:2])
        required_tags = set(keyword_tags[2:])

    api_query = " ".join(api_tags)
    local_filters = {
        "required_tags": required_tags,
        "excluded_tags": excluded_tags,
        "ratings": ratings,
    }
    return api_query, local_filters


def matches_local_filters(post: dict, local_filters: dict) -> bool:
    """APIから返却された投稿が、APIに送りきれなかった手元判定条件を満たすか判定する"""
    allowed_ratings = local_filters.get("ratings")
    if allowed_ratings and post.get("rating") not in allowed_ratings:
        return False

    tag_string = post.get("tag_string", "")
    # アンダースコア表記・スペース表記どちらでも判定できるよう両方をタグ集合に含める
    all_post_tags = set(tag_string.split()) | set(tag_string.replace("_", " ").split())

    for req in local_filters.get("required_tags", set()):
        req_norm = req.replace("_", " ")
        if req not in all_post_tags and req_norm not in all_post_tags:
            return False

    for exc in local_filters.get("excluded_tags", set()):
        exc_norm = exc.replace("_", " ")
        if exc in all_post_tags or exc_norm in all_post_tags:
            return False

    return True


# ─────────────────────────────────────────────
# 進捗管理（中断・再開に対応）
# ─────────────────────────────────────────────

def load_progress() -> dict:
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"done_post_ids": []}


def save_progress(progress: dict) -> None:
    os.makedirs(os.path.dirname(PROGRESS_PATH), exist_ok=True)
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# メインループ
# ─────────────────────────────────────────────

def process_post(post: dict, idx: int, total: int, search_slug: str, negative_text: str,
                  heroine: str, nsfw: bool, include_artist: bool, model: str, checkpoint: str,
                  width: int, height: int, timeout: int, solo_girl_only: bool, auto_canvas: bool,
                  done_ids: set, progress: dict, use_custom: bool = False,
                  skip_realistic: bool = True, local_filters: dict = None, artist_mode: str = None,
                  skip_blacklisted: bool = True) -> int:
    """1件の投稿を判定・変換・生成する。生成した画像枚数を返す（スキップ時は0）"""
    post_id = post.get("id")
    if post_id in done_ids:
        print(f"  [{idx}/{total}] post {post_id}: スキップ（生成済み）")
        return 0

    if local_filters and not matches_local_filters(post, local_filters):
        print(f"  [{idx}/{total}] post {post_id}: スキップ（手元フィルタ条件[必須タグ/除外タグ/rating]に非合致）")
        done_ids.add(post_id)
        progress["done_post_ids"] = sorted(done_ids)
        save_progress(progress)
        return 0

    if solo_girl_only and not is_solo_girl(post):
        print(f"  [{idx}/{total}] post {post_id}: スキップ（ヒロインが複数人の構図）")
        done_ids.add(post_id)
        progress["done_post_ids"] = sorted(done_ids)
        save_progress(progress)
        return 0

    if skip_realistic and is_realistic_style(post):
        print(f"  [{idx}/{total}] post {post_id}: スキップ（実写・3DCG調のため低品質になりやすい）")
        done_ids.add(post_id)
        progress["done_post_ids"] = sorted(done_ids)
        save_progress(progress)
        return 0

    if skip_blacklisted and is_blacklisted(post):
        print(f"  [{idx}/{total}] post {post_id}: スキップ（GENERATION_BLACKLIST_TAGSに合致）")
        done_ids.add(post_id)
        progress["done_post_ids"] = sorted(done_ids)
        save_progress(progress)
        return 0

    identity_tags, situation_tags, _removed = mutate_tags_to_heroine(
        post, heroine=heroine, nsfw=nsfw, include_artist=include_artist, artist_mode=artist_mode
    )
    base_prompt = build_prompt(identity_tags, situation_tags)
    prompt_text = adapt_prompt(base_prompt, model_type=model, is_h_scene=nsfw)

    canvas_size = compute_canvas_size(post.get("image_width"), post.get("image_height")) if auto_canvas else None
    gen_width, gen_height = canvas_size if canvas_size else (width, height)

    prefix = f"DanbooruSearch_{search_slug}_{post_id}"
    mode_label = "anima" if "anima" in model.lower() else ("custom" if use_custom else "default")
    print(f"  [{idx}/{total}] post {post_id} → 生成中 ({prefix}, {gen_width}x{gen_height}, {mode_label})...")

    if "anima" in model.lower():
        # Anima v1.0 DiTはSDXL checkpointを使わないため、use_custom/checkpointの指定は無視する
        wf = create_anima_workflow(
            prompt_text=prompt_text, negative_text=negative_text,
            filename_prefix=prefix, width=gen_width, height=gen_height,
        )
        saved_files, duration = submit_and_wait(wf, timeout=timeout, base_url=ANIMA_COMFY_URL)
    elif use_custom:
        wf = create_custom_workflow(
            prompt_text=prompt_text, negative_text=negative_text,
            filename_prefix=prefix, checkpoint=checkpoint, width=gen_width, height=gen_height,
        )
        saved_files, duration = submit_and_wait(wf, timeout=timeout, base_url=CUSTOM_COMFY_URL)
    else:
        wf = create_default_workflow(
            prompt_text=prompt_text, negative_text=negative_text,
            filename_prefix=prefix, checkpoint=checkpoint, width=gen_width, height=gen_height,
        )
        saved_files, duration = submit_and_wait(wf, timeout=timeout)
    if saved_files:
        print(f"    ✨ 保存: {', '.join(saved_files)} ({duration:.1f}s)")
    else:
        print(f"    ⚠️ タイムアウトまたは失敗: post {post_id}")

    done_ids.add(post_id)
    progress["done_post_ids"] = sorted(done_ids)
    save_progress(progress)
    return len(saved_files)


def run(search: str, limit: int, pages: int, heroine: str, nsfw: bool, include_artist: bool,
        model: str, checkpoint: str, width: int, height: int,
        login: str, api_key: str, resume: bool, timeout: int, solo_girl_only: bool = True,
        auto_canvas: bool = True, use_custom: bool = False, skip_realistic: bool = True,
        until_exhausted: bool = False, artist_mode: str = None, skip_blacklisted: bool = True) -> None:
    progress = load_progress() if resume else {"done_post_ids": []}
    done_ids = set(progress.get("done_post_ids", []))

    heroine_name = get_heroine_dna(heroine)["name"]
    negative_text = get_negative_prompt(model_type=model)
    search_slug = re.sub(r"[^a-zA-Z0-9]+", "_", search).strip("_")[:30] or "search"

    # 匿名利用は1リクエスト最大2タグまでのため、order:+主タグのみAPIに送り、
    # 残りのキーワード・rating:・除外タグは取得後に手元(matches_local_filters)で判定する
    api_query, local_filters = parse_search_query(search)

    print("==================================================================")
    print(f" ⚡ Danbooru検索バッチ生成: '{search}' → {heroine_name} ({model}) ⚡")
    if api_query != search:
        print(f"   API送信クエリ: '{api_query}'")
        print(f"   手元フィルタ: 必須タグ={sorted(local_filters['required_tags'])} "
              f"除外タグ={sorted(local_filters['excluded_tags'])} rating={sorted(local_filters['ratings'])}")
    if until_exhausted:
        print("   🔁 --all指定: 検索条件に合致する投稿が尽きるまでページを進め続けます（目標枚数・ページ上限なし）")
    print("==================================================================")

    wait_for_comfyui(resolve_comfy_url(model, use_custom))

    # 手元フィルタで弾かれる投稿が出る分、目標生成枚数(limit*pages)に届くまでページを進め続ける。
    # ただし検索条件が厳しすぎて無限にページを取得し続けないよう安全上限を設ける。
    # --all指定時は両方とも無効化し、Danbooruが空のページを返す（対象が尽きる）まで回す。
    target_generated = None if until_exhausted else limit * pages
    max_page = None if until_exhausted else max(pages * 20, pages)
    total_generated = 0
    page = 0
    while (target_generated is None or total_generated < target_generated) \
            and (max_page is None or page < max_page):
        page += 1
        posts = search_posts(api_query, limit=limit, page=page, login=login, api_key=api_key)
        if not posts:
            print(f"  ページ {page}: 結果なし。終了します。")
            break
        print(f"\n📄 ページ {page}: {len(posts)}件取得")

        for idx, post in enumerate(posts, 1):
            total_generated += process_post(
                post, idx, len(posts), search_slug, negative_text,
                heroine=heroine, nsfw=nsfw, include_artist=include_artist,
                model=model, checkpoint=checkpoint, width=width, height=height,
                timeout=timeout, solo_girl_only=solo_girl_only, auto_canvas=auto_canvas,
                done_ids=done_ids, progress=progress, use_custom=use_custom,
                skip_realistic=skip_realistic, local_filters=local_filters, artist_mode=artist_mode,
                skip_blacklisted=skip_blacklisted,
            )
            if target_generated is not None and total_generated >= target_generated:
                break

        if target_generated is None or total_generated < target_generated:
            time.sleep(1)

    print(f"\n🎉 完了: {total_generated}枚生成しました。")


def run_lucky(search: str, limit: int, heroine: str, nsfw: bool, include_artist: bool,
              model: str, checkpoint: str, width: int, height: int,
              login: str, api_key: str, resume: bool, timeout: int, solo_girl_only: bool = True,
              auto_canvas: bool = True, interval: float = 2.0, use_custom: bool = False,
              skip_realistic: bool = True, artist_mode: str = None, skip_blacklisted: bool = True) -> None:
    """I'm Feeling Lucky: random:Nで無限に投稿を引き当てて生成し続ける（Ctrl+Cで停止）"""
    progress = load_progress() if resume else {"done_post_ids": []}
    done_ids = set(progress.get("done_post_ids", []))

    heroine_name = get_heroine_dna(heroine)["name"]
    negative_text = get_negative_prompt(model_type=model)
    search_slug = re.sub(r"[^a-zA-Z0-9]+", "_", search).strip("_")[:30] or "search"

    # order:randomは大きい母集団全体をソートするためタイムアウトしやすいので使わず、
    # random:Nで効率的にN件だけ無作為抽出する。1リクエスト最大2タグ制限のため主キーワード
    # 1個+random:Nのみ送信し、order:や残りのキーワード・rating:・除外タグは手元で判定する。
    _order_tag, keyword_tags, ratings, excluded_tags = _tokenize_search_query(search)
    local_filters = {
        "required_tags": set(keyword_tags[1:]),
        "excluded_tags": excluded_tags,
        "ratings": ratings,
    }
    lucky_tags = f"{keyword_tags[0] if keyword_tags else ''} random:{limit}".strip()

    print("==================================================================")
    print(f" 🍀 I'M FEELING LUCKY: '{search}' → {heroine_name} ({model}) を無限ループ生成 🍀")
    print("   (Ctrl+C で停止できます。進捗は自動保存されます)")
    print("==================================================================")

    wait_for_comfyui(resolve_comfy_url(model, use_custom))

    total_generated = 0
    round_num = 0
    while True:
        round_num += 1
        try:
            posts = search_posts(lucky_tags, limit=limit, page=1, login=login, api_key=api_key)
        except requests.HTTPError as e:
            print(f"  ラウンド {round_num}: Danbooru APIエラー ({e})。{interval}秒後に再試行します。")
            time.sleep(interval)
            continue
        if not posts:
            print(f"  ラウンド {round_num}: 結果なし。{interval}秒後に再試行します。")
            time.sleep(interval)
            continue

        print(f"\n🎲 ラウンド {round_num}: {len(posts)}件取得")
        new_in_round = 0
        for idx, post in enumerate(posts, 1):
            if post.get("id") not in done_ids:
                new_in_round += 1
            total_generated += process_post(
                post, idx, len(posts), search_slug, negative_text,
                heroine=heroine, nsfw=nsfw, include_artist=include_artist,
                model=model, checkpoint=checkpoint, width=width, height=height,
                timeout=timeout, solo_girl_only=solo_girl_only, auto_canvas=auto_canvas,
                done_ids=done_ids, progress=progress, use_custom=use_custom,
                skip_realistic=skip_realistic, local_filters=local_filters, artist_mode=artist_mode,
                skip_blacklisted=skip_blacklisted,
            )

        if new_in_round == 0:
            time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(
        description="⚡ Danbooru検索結果を上から順にヒロイン化して連続画像生成するツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("search", help="Danbooruの検索タグ（スペース区切りで複数指定可、order:/rating:/-除外タグも可、例: 'order:score rating:explicit micro_bikini beach 1girl'）")
    parser.add_argument("--limit", type=int, default=20, help="1ページあたりの取得件数（デフォルト20、最大200）")
    parser.add_argument("--pages", type=int, default=1, help="取得するページ数（デフォルト1）")
    parser.add_argument("--sort", "-s", default=None,
                         help="searchにorder:が無い場合に自動付与する並び順（例: score, favcount, rank）")
    parser.add_argument("--heroine", "-H", choices=list(config.HEROINES.keys()), default=config.DEFAULT_HEROINE,
                         help=f"変換先ヒロイン（デフォルト: {config.DEFAULT_HEROINE}）")
    parser.add_argument("--no-nsfw", action="store_true", help="NSFWタグを除去する")
    parser.add_argument("--include-artist", action="store_true", help="artist:タグをプロンプトに含める")
    parser.add_argument("--artist-mode", choices=["keep", "override", "none"], default=None,
                         help="画風(artistタグ)の扱い: keep=元投稿優先(無ければヒロインのartist_tags) / "
                              "override=常にヒロインのartist_tagsを使う / none=完全除去（省略時は--include-artistから決定）")
    parser.add_argument("--model", choices=["illustrious", "anima", "animagine"], default="illustrious",
                         help="生成モデル構文（デフォルト: illustrious）")
    parser.add_argument("--checkpoint", default=config.DEFAULT_CHECKPOINT,
                         help="ComfyUIのcheckpointファイル名")
    parser.add_argument("--width", type=int, default=832, help="キャンバス幅（--no-auto-canvas指定時、またはDanbooruに元サイズ情報がない場合のフォールバック）")
    parser.add_argument("--height", type=int, default=1216, help="キャンバス高さ（同上）")
    parser.add_argument("--login", default=config.DANBOORU_LOGIN, help="Danbooru ログイン名（任意、config.pyでも設定可）")
    parser.add_argument("--api-key", default=config.DANBOORU_API_KEY, help="Danbooru API キー（任意、config.pyでも設定可）")
    parser.add_argument("--no-resume", action="store_true", help="生成済み投稿の記録を無視して最初からやり直す")
    parser.add_argument("--timeout", type=int, default=180, help="1枚あたりの生成待機タイムアウト秒")
    parser.add_argument("--allow-multi-girl", action="store_true",
                         help="ヒロインが複数人登場する投稿（2girls等）も生成対象に含める（デフォルトはヒロイン1人のみ。相手役の1boy等は常に許容）")
    parser.add_argument("--no-auto-canvas", action="store_true",
                         help="Danbooru元画像のアスペクト比に合わせて約1024x1024に自動調整する機能を無効化し、常に--width/--heightを使う")
    parser.add_argument("--allow-realistic", action="store_true",
                         help="実写・3DCG調(photorealistic/3d/realistic等)の投稿も生成対象に含める（デフォルトは低品質になりやすいため除外）")
    parser.add_argument("--allow-blacklisted", action="store_true",
                         help="config.GENERATION_BLACKLIST_TAGSに合致する投稿も生成対象に含める（デフォルトはスキップ）")
    parser.add_argument("--all", action="store_true", dest="until_exhausted",
                         help="--limit/--pagesの目標枚数・ページ上限を無視し、検索条件に合致する投稿が尽きる（Danbooruが空のページを返す）まで全て処理する")
    parser.add_argument("--lucky", action="store_true",
                         help="I'm Feeling Luckyモード： order:randomで投稿を引き当てながらCtrl+Cで停止するまで無限に生成し続ける（--pagesは無視される）")
    parser.add_argument("--lucky-interval", type=float, default=2.0,
                         help="--lucky使用時、新規投稿が0件だったラウンドの後に待機する秒数（デフォルト、2.0秒）")
    parser.add_argument("--custom", action="store_true", dest="use_custom",
                         help=f"デフォルトのComfyUIの代わりにconfig.pyのCUSTOM_COMFY_URL({CUSTOM_COMFY_URL})とCUSTOM_LORA_NAME等のカスタムワークフローで生成する（高速化LoRA運用等を想定）")

    args = parser.parse_args()

    search = args.search
    if args.sort and "order:" not in search:
        search = f"order:{args.sort} {search}".strip()

    try:
        if args.lucky:
            run_lucky(
                search=search, limit=args.limit,
                heroine=args.heroine, nsfw=not args.no_nsfw, include_artist=args.include_artist,
                model=args.model, checkpoint=args.checkpoint, width=args.width, height=args.height,
                login=args.login, api_key=args.api_key, resume=not args.no_resume, timeout=args.timeout,
                solo_girl_only=not args.allow_multi_girl, auto_canvas=not args.no_auto_canvas,
                interval=args.lucky_interval, use_custom=args.use_custom,
                skip_realistic=not args.allow_realistic, artist_mode=args.artist_mode,
                skip_blacklisted=not args.allow_blacklisted,
            )
        else:
            run(
                search=search, limit=args.limit, pages=args.pages,
                heroine=args.heroine, nsfw=not args.no_nsfw, include_artist=args.include_artist,
                model=args.model, checkpoint=args.checkpoint, width=args.width, height=args.height,
                login=args.login, api_key=args.api_key, resume=not args.no_resume, timeout=args.timeout,
                solo_girl_only=not args.allow_multi_girl, auto_canvas=not args.no_auto_canvas,
                use_custom=args.use_custom, skip_realistic=not args.allow_realistic,
                until_exhausted=args.until_exhausted, artist_mode=args.artist_mode,
                skip_blacklisted=not args.allow_blacklisted,
            )
    except requests.HTTPError as e:
        print(f"\n[ERROR] Danbooru API エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[中断] ユーザーによって中断されました。進捗は保存済みなので --no-resume なしで再実行すれば続きから再開します。", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
