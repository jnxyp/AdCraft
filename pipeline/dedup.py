"""Deduplicate ads in two passes.

Pass 1 — exact: drop ads whose body text is identical to an earlier ad.
Pass 2 — near: embed remaining bodies with text-embedding-3-small and drop any
         ad whose cosine similarity to an already-kept ad exceeds NEAR_THRESHOLD.
         Set high (default 0.97) so only near-verbatim copies are removed;
         same-product ads with different copy stay.

Run from pipeline/:
    python dedup.py                              # dedup ds0_raw.json → ds0_dedup.json
    python dedup.py --input data/ds1_raw.json --output data/ds1_dedup.json
"""
from __future__ import annotations

import argparse
import json
import logging
import re
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
DEFAULT_EXCLUDE_LANGS: tuple[str, ...] = ("hi", "ar", "es", "ja")


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


# ── Language filtering ───────────────────────────────────────────────────────

_SPANISH_STOPWORDS: set[str] = {
    "de", "la", "el", "en", "y", "por", "para", "con", "una", "un", "los", "las",
    "que", "del", "al", "como", "más", "mas", "sus", "tu", "tus", "mi", "mis",
    "hoy", "ahora", "oferta", "comprar", "envio", "envío", "gratis", "descuento",
}

_SPANISH_WORD_RE = re.compile(r"[a-záéíóúñü]+", re.IGNORECASE)


def _looks_hindi(text: str) -> bool:
    return any("\u0900" <= ch <= "\u097F" for ch in text)


def _looks_arabic(text: str) -> bool:
    return any(
        ("\u0600" <= ch <= "\u06FF")
        or ("\u0750" <= ch <= "\u077F")
        or ("\u08A0" <= ch <= "\u08FF")
        for ch in text
    )


def _looks_japanese(text: str) -> bool:
    return any(
        ("\u3040" <= ch <= "\u309F")   # Hiragana
        or ("\u30A0" <= ch <= "\u30FF")  # Katakana
        for ch in text
    )


def _looks_spanish(text: str) -> bool:
    lowered = text.lower()
    # Strong indicator characters.
    if any(ch in lowered for ch in ("ñ", "á", "é", "í", "ó", "ú", "ü", "¿", "¡")):
        return True
    words = _SPANISH_WORD_RE.findall(lowered)
    if len(words) < 6:
        return False
    hits = sum(1 for w in words if w in _SPANISH_STOPWORDS)
    return hits >= 3


def detect_language_bucket(text: str) -> str | None:
    if _looks_hindi(text):
        return "hi"
    if _looks_arabic(text):
        return "ar"
    if _looks_japanese(text):
        return "ja"
    if _looks_spanish(text):
        return "es"
    return None


def filter_languages(ads: list[dict[str, Any]], exclude_langs: set[str]) -> list[dict[str, Any]]:
    if not exclude_langs:
        return ads
    kept: list[dict[str, Any]] = []
    removed_counts: dict[str, int] = {}
    for ad in ads:
        body = str(ad.get("body", ""))
        lang = detect_language_bucket(body)
        if lang is not None and lang in exclude_langs:
            removed_counts[lang] = removed_counts.get(lang, 0) + 1
            continue
        kept.append(ad)
    removed_total = len(ads) - len(kept)
    if removed_total > 0:
        details = ", ".join(f"{lang}={count}" for lang, count in sorted(removed_counts.items()))
        log.info("Language filter: removed %d / %d (%s)", removed_total, len(ads), details)
    else:
        log.info("Language filter: removed 0 / %d", len(ads))
    return kept


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(Path(__file__).parent.parent / ".env")

    parser = argparse.ArgumentParser(description="Deduplicate raw ads (exact + near-embedding)")
    parser.add_argument("--input",     default="data/ds0_raw.json",   help="Input raw ads JSON")
    parser.add_argument("--output",    default="data/ds0_dedup.json", help="Output deduped JSON")
    parser.add_argument("--threshold", type=float, default=NEAR_THRESHOLD,
                        help=f"Cosine similarity cutoff for near-dedup (default {NEAR_THRESHOLD})")
    parser.add_argument(
        "--exclude-langs",
        default=",".join(DEFAULT_EXCLUDE_LANGS),
        help="Comma-separated language buckets to drop before dedup (supported: hi,ar,es,ja). "
             "Set empty string to disable.",
    )
    args = parser.parse_args()

    input_path  = Path(args.input)
    output_path = Path(args.output)

    ads: list[dict[str, Any]] = json.loads(input_path.read_text(encoding="utf-8"))
    log.info("Loaded %d ads from %s", len(ads), input_path)
    exclude_langs = {item.strip().lower() for item in args.exclude_langs.split(",") if item.strip()}
    ads = filter_languages(ads, exclude_langs)

    ads = exact_dedup(ads)

    client = OpenAI()
    ads = near_dedup(ads, client, threshold=args.threshold)

    output_path.write_text(json.dumps(ads, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Saved %d ads → %s", len(ads), output_path)


if __name__ == "__main__":
    main()
