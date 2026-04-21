"""Deduplicate ads in two passes.

Pass 1 — exact: drop ads whose body text is identical to an earlier ad.
Pass 2 — near: embed remaining bodies with text-embedding-3-small and drop any
         ad whose cosine similarity to an already-kept ad exceeds NEAR_THRESHOLD.
         Set high (default 0.97) so only near-verbatim copies are removed;
         same-product ads with different copy stay.

Run from pipeline/:
    python dedup.py                              # dedup raw_ds0.json
    python dedup.py --input data/raw_ds1.json --output data/deduped_ds1.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
from openai import OpenAI

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)

EMBED_MODEL: str = "text-embedding-3-small"
EMBED_BATCH: int = 200      # inputs per embedding API call
NEAR_THRESHOLD: float = 0.97


# ── Embedding ─────────────────────────────────────────────────────────────────

_MAX_CHARS: int = 24_000  # ~6k tokens; well under the 8192-token embedding limit


def embed_texts(client: OpenAI, texts: list[str]) -> np.ndarray:
    """Return (N, D) float32 array of L2-normalised embeddings."""
    all_vecs: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = [t[:_MAX_CHARS] for t in texts[i: i + EMBED_BATCH]]
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
        resp.data.sort(key=lambda e: e.index)
        all_vecs.extend(e.embedding for e in resp.data)
        log.info("  embedded %d / %d", min(i + EMBED_BATCH, len(texts)), len(texts))
    mat = np.array(all_vecs, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    return mat / np.maximum(norms, 1e-9)


# ── Dedup passes ─────────────────────────────────────────────────────────────

def exact_dedup(ads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    kept: list[dict[str, Any]] = []
    for ad in ads:
        body = ad["body"]
        if body not in seen:
            seen.add(body)
            kept.append(ad)
    removed = len(ads) - len(kept)
    log.info("Exact dedup: removed %d / %d  →  %d remaining", removed, len(ads), len(kept))
    return kept


def near_dedup(ads: list[dict[str, Any]], client: OpenAI, threshold: float) -> list[dict[str, Any]]:
    log.info("Embedding %d ads for near-dedup (model=%s)...", len(ads), EMBED_MODEL)
    bodies = [ad["body"] for ad in ads]
    vecs = embed_texts(client, bodies)   # (N, D), L2-normalised

    kept_indices: list[int] = []
    kept_vecs: list[np.ndarray] = []

    for i, vec in enumerate(vecs):
        if kept_vecs:
            sims = np.array(kept_vecs) @ vec   # cosine similarity to all kept
            if float(sims.max()) >= threshold:
                continue                        # near-duplicate — skip
        kept_indices.append(i)
        kept_vecs.append(vec)

    kept = [ads[i] for i in kept_indices]
    removed = len(ads) - len(kept)
    log.info(
        "Near-dedup (threshold=%.2f): removed %d / %d  →  %d remaining",
        threshold, removed, len(ads), len(kept),
    )
    return kept


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(Path(__file__).parent.parent / ".env")

    parser = argparse.ArgumentParser(description="Deduplicate raw ads (exact + near-embedding)")
    parser.add_argument("--input",     default="data/raw_ds0.json",    help="Input raw ads JSON")
    parser.add_argument("--output",    default="data/deduped_ds0.json", help="Output deduped JSON")
    parser.add_argument("--threshold", type=float, default=NEAR_THRESHOLD,
                        help=f"Cosine similarity cutoff for near-dedup (default {NEAR_THRESHOLD})")
    args = parser.parse_args()

    input_path  = Path(args.input)
    output_path = Path(args.output)

    ads: list[dict[str, Any]] = json.loads(input_path.read_text(encoding="utf-8"))
    log.info("Loaded %d ads from %s", len(ads), input_path)

    ads = exact_dedup(ads)

    client = OpenAI()
    ads = near_dedup(ads, client, threshold=args.threshold)

    output_path.write_text(json.dumps(ads, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Saved %d ads → %s", len(ads), output_path)


if __name__ == "__main__":
    main()
