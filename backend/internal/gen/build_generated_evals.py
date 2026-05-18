"""Generate pairwise eval tasks comparing template-guided vs direct ad copy.

For each selected product description the script:
  - finds the top-ranked template from the live retriever (with BT scores),
  - generates a structured variant using that template,
  - generates a direct (unstructured) copy for the same product,
  - inserts the pair into eval_tasks with pair_scope="template_vs_direct".

Slot assignment is randomised so neither template nor direct is always "A".

Prerequisites:
  - Backend DB and ChromaDB must already be initialised (run the backend at least once).
  - OPENAI_API_KEY in .env.

Run from backend/:
    uv run python internal/gen/build_generated_evals.py
    uv run python internal/gen/build_generated_evals.py --target 200 --parallel 5
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import chromadb
from chromadb.utils import embedding_functions
from openai import AsyncOpenAI

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.config import load_settings
from core.database import connect
from generation.direct import generate_direct_output
from generation.structured import generate_structured_variants
from retrieval.retriever import ChromaClient as RetrieverChromaClient
from retrieval.retriever import Retriever, Template

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)

PAIR_SCOPE = "template_vs_direct"
DEFAULT_TARGET = 200
DEFAULT_PARALLEL = 5
DEFAULT_SEMANTIC_THRESHOLD = 0.50
RANDOM_SEED = 20260517

LengthBucket = Literal["xs", "s", "m", "l", "xl"]
VALID_BUCKETS: frozenset[str] = frozenset({"xs", "s", "m", "l", "xl"})


class _TextGenerator:
    def __init__(self, *, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        response = await self._client.responses.create(
            model=self._model,
            reasoning={"effort": "high"},
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
            ],
        )
        return response.output_text


@dataclass
class _Candidate:
    product_desc: str
    category: str
    length: LengthBucket
    template: Template


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _length_bucket(seq_len: int) -> LengthBucket | None:
    if 1 <= seq_len <= 2:
        return "xs"
    if seq_len == 3:
        return "s"
    if 4 <= seq_len <= 5:
        return "m"
    if 6 <= seq_len <= 8:
        return "l"
    if 9 <= seq_len <= 15:
        return "xl"
    return None


def _task_id(template_id: str, product_desc: str) -> str:
    key = f"geneval:{template_id}:{product_desc}"
    return "gen_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _load_unique_product_descs(
    path: Path,
) -> list[tuple[str, str, LengthBucket]]:
    """Return (product_desc, category, length_bucket) de-duplicated by product_desc."""
    ads: list[dict] = json.loads(path.read_text(encoding="utf-8"))

    cats_by_desc: defaultdict[str, list[str]] = defaultdict(list)
    lengths_by_desc: defaultdict[str, Counter[str]] = defaultdict(Counter)

    for ad in ads:
        product_desc = ad.get("product_desc")
        categories = ad.get("categories", [])
        sequence = ad.get("sequence", [])
        if not isinstance(product_desc, str) or not product_desc.strip():
            continue
        if not isinstance(categories, list) or not categories:
            continue
        if not isinstance(sequence, list) or not sequence:
            continue
        bucket = _length_bucket(len(sequence))
        if bucket is None:
            continue
        cats_by_desc[product_desc].append(str(categories[0]))
        lengths_by_desc[product_desc][bucket] += 1

    result: list[tuple[str, str, LengthBucket]] = []
    for product_desc, cat_list in cats_by_desc.items():
        category = Counter(cat_list).most_common(1)[0][0]
        length = cast(LengthBucket, lengths_by_desc[product_desc].most_common(1)[0][0])
        result.append((product_desc, category, length))
    return result


async def _load_bt_scores(db_path: Path) -> dict[str, float]:
    async with connect(db_path) as conn:
        rows = await (
            await conn.execute("SELECT template_id, beta FROM template_bt_scores")
        ).fetchall()
    return {str(row["template_id"]): float(row["beta"]) for row in rows}


async def _existing_task_ids(db_path: Path) -> set[str]:
    async with connect(db_path) as conn:
        rows = await (
            await conn.execute(
                "SELECT id FROM eval_tasks WHERE pair_scope = ?", (PAIR_SCOPE,)
            )
        ).fetchall()
    return {str(row["id"]) for row in rows}


# ---------------------------------------------------------------------------
# Candidate selection
# ---------------------------------------------------------------------------

async def _select_candidates(
    *,
    retriever: Retriever,
    product_descs: list[tuple[str, str, LengthBucket]],
    semantic_threshold: float,
    target: int,
    existing_ids: set[str],
) -> list[_Candidate]:
    """
    Query the retriever for each product_desc and keep those with a strong
    semantic match to a high-quality template.

    Sorting priority:
      1. Has BT score (template has been evaluated by users)  — descending
      2. Semantic distance to template                        — ascending
    """
    candidates: list[_Candidate] = []
    skipped_dist = 0
    skipped_exists = 0

    for product_desc, category, length in product_descs:
        try:
            results = await retriever.query_ranked(
                category=category,
                product_desc=product_desc,
                length=length,
                limit=1,
            )
        except Exception as exc:
            log.debug("retriever query failed for %.40r: %s", product_desc, exc)
            continue

        if not results:
            continue

        top = results[0]
        dist = top.get("semantic_distance")
        if not isinstance(dist, (int, float)) or dist > semantic_threshold:
            skipped_dist += 1
            continue

        tid = _task_id(top["id"], product_desc)
        if tid in existing_ids:
            skipped_exists += 1
            continue

        candidates.append(_Candidate(
            product_desc=product_desc,
            category=category,
            length=length,
            template=top,
        ))

    log.info(
        "Candidate pool: %d kept, %d skipped (distance > %.2f), %d already exist",
        len(candidates), skipped_dist, semantic_threshold, skipped_exists,
    )

    # Sort: prefer templates that have a BT score, then by best semantic match
    candidates.sort(key=lambda c: (
        0 if c.template.get("bt_score") is not None else 1,
        c.template.get("semantic_distance") or 1.0,
    ))

    bt_count = sum(1 for c in candidates if c.template.get("bt_score") is not None)
    log.info(
        "Top %d selected: %d with BT score, %d freq-score only",
        min(target, len(candidates)), min(bt_count, target), max(0, min(target, len(candidates)) - min(bt_count, target)),
    )
    return candidates[:target]


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

async def _generate_pair(
    *,
    candidate: _Candidate,
    text_generator: _TextGenerator,
    rng: random.Random,
) -> dict | None:
    template = candidate.template
    sequence = template["name"].split("→")
    bucket = _length_bucket(template["seq_len"])
    if bucket is None:
        log.warning("template seq_len=%d out of range, skipping", template["seq_len"])
        return None

    try:
        variants = await generate_structured_variants(
            text_generator=text_generator,
            category=candidate.category,
            product_desc=candidate.product_desc,
            generation_prompt=None,
            templates=[template],
        )
        if not variants:
            log.warning("structured generation returned empty for template %s", template["id"])
            return None
        structured_body = variants[0]["output"]
    except Exception as exc:
        log.warning("structured generation failed (template %s): %s", template["id"], exc)
        return None

    try:
        direct_body = await generate_direct_output(
            text_generator=text_generator,
            category=candidate.category,
            product_desc=candidate.product_desc,
            length=candidate.length,
            generation_prompt=None,
        )
    except Exception as exc:
        log.warning("direct generation failed (%.40s): %s", candidate.product_desc, exc)
        return None

    # Randomise which slot gets the template to avoid positional bias
    tmpl_slot, direct_slot = ("a", "b") if rng.random() < 0.5 else ("b", "a")
    task_id_val = _task_id(template["id"], candidate.product_desc)

    # seq_len and length_bucket stored explicitly so eval.py can serve them
    # without crashing on the direct ad's empty sequence.
    ads = sorted(
        [
            {
                "slot": tmpl_slot,
                "ad_id": f"gen_tmpl_{task_id_val}",
                "body": structured_body,
                "template_id": template["id"],
                "sequence": sequence,
                "cluster_id": "",
                "seq_len": template["seq_len"],
                "length_bucket": bucket,
            },
            {
                "slot": direct_slot,
                "ad_id": f"gen_direct_{task_id_val}",
                "body": direct_body,
                "template_id": "",
                "sequence": [],
                "cluster_id": "",
                "seq_len": template["seq_len"],
                "length_bucket": bucket,
            },
        ],
        key=lambda ad: ad["slot"],
    )

    return {
        "id": task_id_val,
        "task_type": "pair",
        "pair_scope": PAIR_SCOPE,
        "category": candidate.category,
        "cluster_id": "",
        "ads": ads,
    }


# ---------------------------------------------------------------------------
# DB insertion
# ---------------------------------------------------------------------------

async def _insert_tasks(db_path: Path, tasks: list[dict]) -> int:
    inserted = 0
    async with connect(db_path) as conn:
        await conn.execute("BEGIN")
        for task in tasks:
            cursor = await conn.execute(
                """
                INSERT OR IGNORE INTO eval_tasks
                    (id, task_type, pair_scope, category, cluster_id, ads)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    task["id"],
                    task["task_type"],
                    task["pair_scope"],
                    task["category"],
                    task["cluster_id"],
                    json.dumps(task["ads"], ensure_ascii=False),
                ),
            )
            inserted += cursor.rowcount
        await conn.commit()
    return inserted


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate template-vs-direct eval task pairs and insert into the DB."
    )
    parser.add_argument(
        "--target", type=int, default=DEFAULT_TARGET,
        help=f"Number of tasks to generate (default: {DEFAULT_TARGET})",
    )
    parser.add_argument(
        "--parallel", type=int, default=DEFAULT_PARALLEL,
        help=f"Concurrent LLM calls during generation (default: {DEFAULT_PARALLEL})",
    )
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_SEMANTIC_THRESHOLD,
        help=f"Max cosine distance for template match (default: {DEFAULT_SEMANTIC_THRESHOLD})",
    )
    parser.add_argument("--model", default=None, help="Override OpenAI chat model")
    args = parser.parse_args()

    settings = load_settings()
    model = args.model or settings.openai_chat_model

    chromadb_path = str(settings.chromadb_dir)
    if not settings.chromadb_dir.exists():
        log.error(
            "ChromaDB directory not found at %s. "
            "Start the backend at least once to initialise it.",
            chromadb_path,
        )
        sys.exit(1)

    annotated_path = settings.pipeline_data_dir / "ds0_annotated.json"
    if not annotated_path.exists():
        log.error("Annotated ads not found at %s", annotated_path)
        sys.exit(1)

    log.info("Initialising ChromaDB from %s", chromadb_path)
    chroma_client = chromadb.PersistentClient(path=chromadb_path)
    embedding_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_key=settings.openai_api_key,
        model_name=settings.openai_embedding_model,
    )
    retriever = Retriever(
        cast(RetrieverChromaClient, chroma_client),
        collection_name=settings.chroma_collection_name,
    )
    bt_scores = await _load_bt_scores(settings.db_path)
    retriever.refresh_bt_scores(bt_scores)
    log.info("Loaded %d BT scores into retriever", len(bt_scores))

    log.info("Loading unique product descriptions from %s", annotated_path)
    product_descs = _load_unique_product_descs(annotated_path)
    log.info("Found %d unique product descriptions", len(product_descs))

    existing_ids = await _existing_task_ids(settings.db_path)
    log.info("Existing %s tasks in DB: %d", PAIR_SCOPE, len(existing_ids))

    candidates = await _select_candidates(
        retriever=retriever,
        product_descs=product_descs,
        semantic_threshold=args.threshold,
        target=args.target,
        existing_ids=existing_ids,
    )
    if not candidates:
        log.error(
            "No suitable candidates found. "
            "Try increasing --threshold (current: %.2f) or check that BT scores exist.",
            args.threshold,
        )
        sys.exit(1)

    oai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    text_generator = _TextGenerator(client=oai_client, model=model)
    rng = random.Random(RANDOM_SEED)
    semaphore = asyncio.Semaphore(max(1, args.parallel))

    async def _run_one(candidate: _Candidate) -> dict | None:
        async with semaphore:
            return await _generate_pair(
                candidate=candidate,
                text_generator=text_generator,
                rng=rng,
            )

    log.info(
        "Generating %d pairs with model=%s parallel=%d ...",
        len(candidates), model, args.parallel,
    )
    results = await asyncio.gather(*[_run_one(c) for c in candidates])
    tasks = [t for t in results if t is not None]
    failed = len(candidates) - len(tasks)
    if failed:
        log.warning("%d generation failures", failed)
    log.info("Successfully generated %d eval tasks", len(tasks))

    inserted = await _insert_tasks(settings.db_path, tasks)
    log.info(
        "Inserted %d new eval tasks with pair_scope=%s (%d duplicates skipped)",
        inserted, PAIR_SCOPE, len(tasks) - inserted,
    )


if __name__ == "__main__":
    asyncio.run(main())
