"""Loader for smangrul/ad-copy-generation.

Raw field: `content` — Llama instruction-tuning format:
  <s>[INST] <<SYS>>\\nCreate a text ad...\\n<</SYS>>\\n\\nProduct: X\\nDescription: Y [/INST] Ad: Z </s>

Parsed output per row:
  { "ad_id": str, "body": str, "product_desc": str, "category": "" }
"""
import re
import uuid
from typing import Any

from datasets import load_dataset  # type: ignore[import-untyped]

_PRODUCT_RE = re.compile(r"Product:\s*(.+?)(?:\n|$)")
_DESC_RE = re.compile(r"Description:\s*(.+?)\s*\[/INST\]", re.DOTALL)
_BODY_RE = re.compile(r"\[/INST\]\s*Ad:\s*(.+?)\s*</s>", re.DOTALL)


def _parse_row(content: str) -> dict[str, str] | None:
    product_m = _PRODUCT_RE.search(content)
    desc_m = _DESC_RE.search(content)
    body_m = _BODY_RE.search(content)

    if not body_m:
        return None

    product: str = product_m.group(1).strip() if product_m else ""
    desc: str = desc_m.group(1).strip() if desc_m else ""

    parts = [p for p in (product, desc) if p]
    product_desc = ". ".join(parts)
    body = body_m.group(1).strip()

    return {"product_desc": product_desc, "body": body}


def load() -> list[dict[str, str]]:
    """Return all rows from both train and test splits as unified dicts."""
    ds = load_dataset("smangrul/ad-copy-generation")
    records: list[dict[str, str]] = []

    for split in ds.values():
        for row in split:
            parsed = _parse_row(row["content"])  # type: ignore[index]
            if parsed is None:
                continue
            records.append(
                {
                    "ad_id": str(uuid.uuid4()),
                    "body": parsed["body"],
                    "product_desc": parsed["product_desc"],
                    "category": "",
                    "source": "ds1",
                }
            )

    return records


if __name__ == "__main__":
    import json
    import sys

    rows = load()
    sys.stdout.buffer.write(f"Loaded {len(rows)} rows from DS1\n".encode())
    for r in rows[:3]:
        sys.stdout.buffer.write((json.dumps(r, ensure_ascii=True) + "\n").encode())
