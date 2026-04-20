"""Loader for PeterBrendan/Ads_Creative_Ad_Copy_Programmatic.

Raw fields:
  `text`       — OCR-extracted display banner text (short, fragmented)
  `dimensions` — banner pixel size, e.g. "(300, 250)" — not used

Quality filter: rows with fewer than MIN_WORDS words are dropped.

Parsed output per row:
  { "ad_id": str, "body": str, "product_desc": "", "category": "" }
  (product_desc inferred by LLM in Step 2A; category in Step 2B)
"""
import uuid

from datasets import load_dataset  # type: ignore[import-untyped]

MIN_WORDS: int = 15


def load() -> list[dict[str, str]]:
    """Return quality-filtered rows from DS2 as unified dicts."""
    ds = load_dataset("PeterBrendan/Ads_Creative_Ad_Copy_Programmatic")
    records: list[dict[str, str]] = []

    for split in ds.values():
        for row in split:
            text: str = row["text"].strip()  # type: ignore[index]
            if len(text.split()) < MIN_WORDS:
                continue
            records.append(
                {
                    "ad_id": str(uuid.uuid4()),
                    "body": text,
                    "product_desc": "",
                    "category": "",
                    "source": "ds2",
                }
            )

    return records


if __name__ == "__main__":
    import json
    import sys

    rows = load()
    sys.stdout.buffer.write(
        f"Loaded {len(rows)} rows from DS2 (after >= {MIN_WORDS} word filter)\n".encode()
    )
    for r in rows[:3]:
        sys.stdout.buffer.write((json.dumps(r, ensure_ascii=True) + "\n").encode())
