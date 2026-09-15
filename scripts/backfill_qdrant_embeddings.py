"""
Backfill semantic embedding vectors for images registered in Qdrant.
Uses Ollama (embeddinggemma:300m) to generate 768-dim full embeddings
and 256-dim MRL small embeddings.
"""

import json
import logging
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ── Configuration Constants ───────────────────────────────────────────────────
QDRANT_URL: str = "http://localhost:6333"
OLLAMA_URL: str = "http://100.126.79.83:11434/api/embed"
EMBED_MODEL: str = "embeddinggemma:300m"
COLLECTION_NAME: str = "images"
BATCH_SIZE: int = 16
SMALL_DIM: int = 256
LOG_FILE: Path = Path("/home/pi/danbooru_yukikaze_tool/database/backfill_embedding.log")
COOLDOWN_SECONDS: float = 0.3

# ── Logging Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("backfill")


def count_total_points() -> int:
    req = urllib.request.Request(
        f"{QDRANT_URL}/collections/{COLLECTION_NAME}",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode())
        return res.get("result", {}).get("points_count", 0)


def embed_batch(texts: list[str]) -> list[list[float]]:
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps({"model": EMBED_MODEL, "input": texts}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        res = json.loads(resp.read().decode())
        return res.get("embeddings", [])


def update_qdrant_vectors(points_with_vectors: list[tuple[dict, list[float]]]) -> int:
    points_payload = []
    for p, vec in points_with_vectors:
        points_payload.append({
            "id": p["id"],
            "vector": {
                "embedding": vec,
                "embedding_small": vec[:SMALL_DIM],
            },
        })

    req = urllib.request.Request(
        f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points/vectors",
        data=json.dumps({"points": points_payload}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.status


def process_all_points():
    logger.info("=== Starting Whole-Collection Embedding Backfill ===")
    logger.info("Target Model: %s, Batch Size: %d, Qdrant Collection: %s", EMBED_MODEL, BATCH_SIZE, COLLECTION_NAME)

    total_points = count_total_points()
    logger.info("Total points registered in Qdrant: %d", total_points)

    processed_count = 0
    scanned_count = 0
    start_time = time.time()
    offset = None

    while True:
        scroll_body = {
            "limit": 100,
            "with_vector": True,
            "with_payload": True,
        }
        if offset is not None:
            scroll_body["offset"] = offset

        req = urllib.request.Request(
            f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points/scroll",
            data=json.dumps(scroll_body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                res = json.loads(resp.read().decode()).get("result", {})
                points = res.get("points", [])
                offset = res.get("next_page_offset")
        except Exception as e:
            logger.error("Scroll error: %s. Retrying in 5s...", e)
            time.sleep(5)
            continue

        if not points:
            break

        scanned_count += len(points)

        # Filter out points that already have valid embeddings
        unvectorized = []
        for p in points:
            vec = p.get("vector")
            if not vec:
                unvectorized.append(p)
            elif isinstance(vec, dict) and not vec.get("embedding"):
                unvectorized.append(p)

        # Process in batches of BATCH_SIZE
        for i in range(0, len(unvectorized), BATCH_SIZE):
            batch = unvectorized[i:i + BATCH_SIZE]
            texts = []
            for p in batch:
                payload = p.get("payload", {})
                tags = payload.get("wd14_tags", [])
                name = payload.get("name", "")
                heroine = payload.get("heroine", "")
                text = f"{heroine}, {name}, " + ", ".join(tags)
                texts.append(text)

            t_batch = time.time()
            try:
                embeddings = embed_batch(texts)
            except Exception as e:
                logger.error("Embedding generation error: %s. Retrying batch in 5s...", e)
                time.sleep(5)
                continue

            if len(embeddings) != len(batch):
                logger.error("Embedding mismatch: %d vs %d", len(batch), len(embeddings))
                continue

            paired = list(zip(batch, embeddings))
            try:
                update_qdrant_vectors(paired)
            except Exception as e:
                logger.error("Qdrant update error: %s", e)
                continue

            batch_elapsed = time.time() - t_batch
            processed_count += len(batch)
            total_elapsed = time.time() - start_time
            rate = processed_count / total_elapsed if total_elapsed > 0 else 0

            logger.info(
                "Progress: %d/%d scanned, %d newly embedded (last batch: %.2fs, rate: %.2f img/s)",
                scanned_count, total_points, processed_count, batch_elapsed, rate
            )
            time.sleep(COOLDOWN_SECONDS)

        if offset is None:
            break

    total_time = time.time() - start_time
    logger.info(
        "=== Finished! Scanned: %d, Newly Embedded: %d in %.1fs (avg %.2f img/s) ===",
        scanned_count, processed_count, total_time, processed_count / total_time if total_time > 0 else 0
    )


def main():
    process_all_points()


if __name__ == "__main__":
    main()
