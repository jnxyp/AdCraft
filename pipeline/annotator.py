"""Annotate ads with product_desc (2A), categories (2B), and pattern labels (Step 4).

Run from pipeline/:
    python annotator.py                          # process raw_ds0.json
    python annotator.py --input data/raw_ds1.json --output data/annotated_ds1.json

Steps run sequentially; each step saves a checkpoint so the run is resumable
if interrupted (checkpoint is deleted on clean completion).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)

MODEL: str = "gpt-5-mini"
TEMPERATURE: float = 0.0
MAX_CONCURRENT: int = 20
BATCH_SIZE: int = 10
MAX_RETRIES: int = 3

CATEGORIES: list[str] = [
    "ecommerce", "tech", "health", "beauty", "education",
    "finance", "food", "travel", "automotive", "home", "entertainment", "other",
]

PATTERN_CODES: list[str] = [
    "AH", "PP", "AG", "FB", "SP", "BA", "AU", "UR", "OF", "CTA",
]


# ── Prompts ──────────────────────────────────────────────────────────────────

_SYSTEM_2A = (
    "You are an expert at analyzing advertising copy.\n"
    "Given an ad, infer a concise one-sentence product description in English.\n"
    "Describe what the product/service IS, not how it is advertised."
)

_FEW_SHOT_2A: list[dict[str, str]] = [
    {
        "role": "user",
        "content": (
            'Ad copy: "Tired of tossing and turning? Sleep8 uses medical-grade sound therapy '
            'to help you fall asleep 2x faster — clinically proven, drug-free."'
        ),
    },
    {
        "role": "assistant",
        "content": '{"product_desc": "A drug-free sleep aid device that uses sound therapy to improve sleep quality."}',
    },
]

_SYSTEM_2B = (
    "Classify this product into 1–2 categories. Use 2 only when the product genuinely "
    "spans two domains. Prefer 1 when in doubt. Use \"other\" only as a last resort.\n\n"
    "Categories:\n"
    "ecommerce     — physical retail goods (clothing, accessories, gifts, household items)\n"
    "tech          — software, apps, electronics, SaaS, internet services\n"
    "health        — healthcare, nutrition, fitness, sports\n"
    "beauty        — cosmetics, skincare, personal care, haircare\n"
    "education     — courses, training, learning platforms\n"
    "finance       — banking, insurance, investment\n"
    "food          — restaurants, delivery, food & beverages\n"
    "travel        — hotels, flights, vacation packages\n"
    "automotive    — cars, auto parts, auto services\n"
    "home          — furniture, appliances, home improvement, gardening\n"
    "entertainment — media, gaming, streaming, content subscriptions\n"
    "other         — none of the above"
)

_FEW_SHOT_2B: list[dict[str, str]] = [
    {
        "role": "user",
        "content": (
            'Product description: "A mobile app that tracks daily calorie intake '
            'and suggests personalized workout plans."'
        ),
    },
    {"role": "assistant", "content": '{"categories": ["health", "tech"]}'},
    {
        "role": "user",
        "content": 'Product description: "A 30-day online course teaching Python for data science."',
    },
    {"role": "assistant", "content": '{"categories": ["education"]}'},
]

_SYSTEM_STEP4 = (
    "You are an expert ad copy analyst.\n"
    "For each ad: split the body into individual sentences, assign exactly one pattern "
    "label per sentence (choose the most dominant intent), and list the labels in order "
    "as \"sequence\". Return one object per ad in the \"annotations\" field, preserving input order.\n\n"
    "Pattern labels:\n"
    "AH — Attention Hook   PP — Pain Point     AG — Agitation\n"
    "FB — Feature&Benefit  SP — Social Proof   BA — Before&After\n"
    "AU — Authority        UR — Urgency        OF — Offer\n"
    "CTA — Call to Action"
)

_FEW_SHOT_STEP4: list[dict[str, str]] = [
    {
        "role": "user",
        "content": json.dumps([{
            "ad_index": 0,
            "body": (
                "Still wasting hours on manual reports? "
                "DataPulse auto-generates your analytics in seconds. "
                "Trusted by 10,000+ teams. Start free today."
            ),
        }]),
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "annotations": [{
                "ad_index": 0,
                "sentences": [
                    {"text": "Still wasting hours on manual reports?", "pattern": "PP"},
                    {"text": "DataPulse auto-generates your analytics in seconds.", "pattern": "FB"},
                    {"text": "Trusted by 10,000+ teams.", "pattern": "SP"},
                    {"text": "Start free today.", "pattern": "CTA"},
                ],
                "sequence": ["PP", "FB", "SP", "CTA"],
            }],
        }),
    },
]


# ── JSON schemas ──────────────────────────────────────────────────────────────

def _wrap_schema(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}}


_SCHEMA_2A = _wrap_schema("product_desc_response", {
    "type": "object",
    "properties": {"product_desc": {"type": "string"}},
    "required": ["product_desc"],
    "additionalProperties": False,
})

_SCHEMA_2B = _wrap_schema("categories_response", {
    "type": "object",
    "properties": {
        "categories": {
            "type": "array",
            "items": {"type": "string", "enum": CATEGORIES},
        },
    },
    "required": ["categories"],
    "additionalProperties": False,
})

_SCHEMA_STEP4 = _wrap_schema("annotations_response", {
    "type": "object",
    "properties": {
        "annotations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ad_index": {"type": "integer"},
                    "sentences": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "pattern": {"type": "string", "enum": PATTERN_CODES},
                            },
                            "required": ["text", "pattern"],
                            "additionalProperties": False,
                        },
                    },
                    "sequence": {
                        "type": "array",
                        "items": {"type": "string", "enum": PATTERN_CODES},
                    },
                },
                "required": ["ad_index", "sentences", "sequence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["annotations"],
    "additionalProperties": False,
})


# ── API helpers ───────────────────────────────────────────────────────────────

async def _call(
    client: AsyncOpenAI,
    sem: asyncio.Semaphore,
    messages: list[dict[str, str]],
    response_format: dict[str, Any],
) -> str:
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            async with sem:
                resp = await client.chat.completions.create(
                    model=MODEL,
                    response_format=response_format,  # type: ignore[arg-type]
                    messages=messages,  # type: ignore[arg-type]
                )
            content = resp.choices[0].message.content
            if content is None:
                raise ValueError("Empty response content")
            return content
        except Exception as exc:
            last_exc = exc
            wait = 2 ** attempt
            log.warning("API call failed (attempt %d/%d): %s — retrying in %ds",
                        attempt + 1, MAX_RETRIES, exc, wait)
            await asyncio.sleep(wait)
    raise RuntimeError(f"API call failed after {MAX_RETRIES} attempts") from last_exc


# ── Step 2A: infer product_desc ───────────────────────────────────────────────

async def _infer_product_desc(
    client: AsyncOpenAI, sem: asyncio.Semaphore, body: str
) -> str:
    content = await _call(
        client, sem,
        [
            {"role": "system", "content": _SYSTEM_2A},
            *_FEW_SHOT_2A,
            {"role": "user", "content": f"Ad copy: {body}"},
        ],
        _SCHEMA_2A,
    )
    return str(json.loads(content)["product_desc"])


async def run_2a(client: AsyncOpenAI, ads: list[dict[str, Any]]) -> None:
    missing: list[int] = [i for i, ad in enumerate(ads) if not ad.get("product_desc")]
    if not missing:
        log.info("2A: all ads already have product_desc — skipping")
        return
    log.info("2A: inferring product_desc for %d / %d ads", len(missing), len(ads))
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    done_count: int = 0

    async def _do(idx: int) -> None:
        nonlocal done_count
        try:
            ads[idx]["product_desc"] = await _infer_product_desc(client, sem, ads[idx]["body"])
        except Exception as exc:
            log.error("2A: ad %d failed: %s", idx, exc)
        done_count += 1
        if done_count % 100 == 0:
            log.info("2A: %d / %d done", done_count, len(missing))

    await asyncio.gather(*[_do(i) for i in missing])
    log.info("2A: complete")


# ── Step 2B: classify categories ─────────────────────────────────────────────

async def _infer_categories(
    client: AsyncOpenAI, sem: asyncio.Semaphore, product_desc: str
) -> list[str]:
    content = await _call(
        client, sem,
        [
            {"role": "system", "content": _SYSTEM_2B},
            *_FEW_SHOT_2B,
            {"role": "user", "content": f"Product description: {product_desc}"},
        ],
        _SCHEMA_2B,
    )
    return list(json.loads(content)["categories"])


async def run_2b(client: AsyncOpenAI, ads: list[dict[str, Any]]) -> None:
    missing: list[int] = [i for i, ad in enumerate(ads) if not ad.get("categories")]
    if not missing:
        log.info("2B: all ads already have categories — skipping")
        return
    log.info("2B: classifying categories for %d / %d ads", len(missing), len(ads))
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    done_count: int = 0

    async def _do(idx: int) -> None:
        nonlocal done_count
        try:
            ads[idx]["categories"] = await _infer_categories(
                client, sem, ads[idx]["product_desc"]
            )
        except Exception as exc:
            log.error("2B: ad %d failed: %s", idx, exc)
        done_count += 1
        if done_count % 100 == 0:
            log.info("2B: %d / %d done", done_count, len(missing))

    await asyncio.gather(*[_do(i) for i in missing])
    log.info("2B: complete")


# ── Step 4: pattern annotation ────────────────────────────────────────────────

async def _annotate_batch(
    client: AsyncOpenAI,
    sem: asyncio.Semaphore,
    batch: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return annotation objects for a batch; falls back to one-by-one on length mismatch."""
    items = [{"ad_index": i, "body": ad["body"]} for i, ad in enumerate(batch)]

    try:
        content = await _call(
            client, sem,
            [
                {"role": "system", "content": _SYSTEM_STEP4},
                *_FEW_SHOT_STEP4,
                {"role": "user", "content": json.dumps(items)},
            ],
            _SCHEMA_STEP4,
        )
        result: list[dict[str, Any]] = json.loads(content)["annotations"]
        if len(result) == len(batch):
            return result
        log.warning(
            "Step 4: batch size mismatch — expected %d, got %d; falling back to individual calls",
            len(batch), len(result),
        )
    except Exception as exc:
        log.warning("Step 4: batch failed (%s); falling back to individual calls", exc)

    # One-by-one fallback
    fallback: list[dict[str, Any]] = []
    for i, ad in enumerate(batch):
        try:
            content = await _call(
                client, sem,
                [
                    {"role": "system", "content": _SYSTEM_STEP4},
                    *_FEW_SHOT_STEP4,
                    {"role": "user", "content": json.dumps([{"ad_index": 0, "body": ad["body"]}])},
                ],
                _SCHEMA_STEP4,
            )
            ann = json.loads(content)["annotations"][0]
            ann["ad_index"] = i
            fallback.append(ann)
        except Exception as exc:
            log.error("Step 4: individual annotation failed for ad in batch (pos %d): %s", i, exc)
            fallback.append({
                "ad_index": i,
                "sentences": [{"text": ad["body"], "pattern": "AH"}],
                "sequence": ["AH"],
            })
    return fallback


async def run_step4(client: AsyncOpenAI, ads: list[dict[str, Any]]) -> None:
    missing: list[int] = [i for i, ad in enumerate(ads) if not ad.get("sentences")]
    if not missing:
        log.info("Step 4: all ads already annotated — skipping")
        return
    log.info("Step 4: annotating %d / %d ads (batch_size=%d)", len(missing), len(ads), BATCH_SIZE)
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    batches: list[list[int]] = [
        missing[i: i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)
    ]
    done_count: int = 0

    async def _do_batch(indices: list[int]) -> None:
        nonlocal done_count
        batch_ads = [ads[i] for i in indices]
        try:
            results = await _annotate_batch(client, sem, batch_ads)
            for ann in results:
                ads[indices[ann["ad_index"]]]["sentences"] = ann["sentences"]
                ads[indices[ann["ad_index"]]]["sequence"] = ann["sequence"]
        except Exception as exc:
            log.error("Step 4: batch %s failed entirely: %s", indices[:3], exc)
        done_count += 1
        if done_count % 20 == 0:
            log.info("Step 4: %d / %d batches done", done_count, len(batches))

    await asyncio.gather(*[_do_batch(b) for b in batches])
    log.info("Step 4: complete")


# ── Normalisation ─────────────────────────────────────────────────────────────

def _normalize(ads: list[dict[str, Any]]) -> None:
    """Ensure all ads use 'categories: list[str]' instead of legacy 'category: str'."""
    for ad in ads:
        if "categories" not in ad:
            old: str = ad.pop("category", "") or ""
            ad["categories"] = [old] if old else []
        elif isinstance(ad["categories"], str):
            val: str = ad["categories"]
            ad["categories"] = [val] if val else []
        if "category" in ad:
            del ad["category"]


# ── Main ──────────────────────────────────────────────────────────────────────

async def annotate(
    input_path: Path,
    output_path: Path,
    checkpoint_path: Path,
) -> None:
    if checkpoint_path.exists():
        ads: list[dict[str, Any]] = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        log.info("Resuming from checkpoint: %d ads loaded", len(ads))
    else:
        ads = json.loads(input_path.read_text(encoding="utf-8"))
        _normalize(ads)
        log.info("Loaded %d ads from %s", len(ads), input_path)

    client = AsyncOpenAI()

    await run_2a(client, ads)
    checkpoint_path.write_text(json.dumps(ads, ensure_ascii=False, indent=2), encoding="utf-8")

    await run_2b(client, ads)
    checkpoint_path.write_text(json.dumps(ads, ensure_ascii=False, indent=2), encoding="utf-8")

    await run_step4(client, ads)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(ads, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Saved %d annotated ads -> %s", len(ads), output_path)

    checkpoint_path.unlink(missing_ok=True)


def main() -> None:
    from pathlib import Path as _Path
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(_Path(__file__).parent.parent / ".env")

    parser = argparse.ArgumentParser(description="Annotate ads: 2A product_desc, 2B categories, Step 4 patterns")
    parser.add_argument("--input",  default="data/raw_ds0.json",       help="Input raw ads JSON")
    parser.add_argument("--output", default="data/annotated_ds0.json", help="Output annotated JSON")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    checkpoint_path = output_path.with_suffix("").with_suffix(".checkpoint.json")

    if not input_path.exists():
        log.error("Input file not found: %s", input_path)
        sys.exit(1)

    asyncio.run(annotate(input_path, output_path, checkpoint_path))


if __name__ == "__main__":
    main()
