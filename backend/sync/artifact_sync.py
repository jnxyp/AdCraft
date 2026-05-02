"""Backend artifact sync — see plan-generation.md §1.0 for the canonical spec.

Reads pipeline JSON artifacts (`ds0_templates.json`, `ds0_eval_tasks.json`),
hashes each, and only touches runtime storage when the hash changed:

- templates JSON change   -> upsert SQLite `templates`, rebuild ChromaDB `ad_templates`
- eval_tasks JSON change  -> upsert SQLite `eval_tasks` (keep `pair_scope` + `cluster_id`)

Never deletes or overwrites runtime feedback data
(`eval_responses`, `resolved_eval_tasks`, `template_bt_scores`, `generations`).
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, TypedDict

from core.database import connect

log = logging.getLogger(__name__)


class TemplateRow(TypedDict):
    id: str
    sequence: list[str]
    name: str
    seq_len: int
    count: int
    freq_score: float
    categories: list[str]
    example_ad_id: str
    example_body: str
    example_product_desc: str


class EvalTaskAd(TypedDict):
    slot: str
    ad_id: str
    body: str
    template_id: str
    sequence: list[str]


class EvalTaskRow(TypedDict):
    id: str
    task_type: str
    pair_scope: str
    category: str
    cluster_id: str
    ads: list[EvalTaskAd]


class ChromaCollection(Protocol):
    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None: ...


class ChromaClient(Protocol):
    def delete_collection(self, name: str) -> None: ...
    def create_collection(
        self,
        name: str,
        embedding_function: Any | None = ...,
        metadata: dict[str, Any] | None = ...,
    ) -> ChromaCollection: ...


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_templates_json(path: Path) -> list[TemplateRow]:
    data = json.loads(path.read_text(encoding="utf-8"))
    templates = data.get("templates")
    if not isinstance(templates, list):
        raise ValueError(f"{path}: missing 'templates' array")
    return [_coerce_template(item) for item in templates]


def read_eval_tasks_json(path: Path) -> list[EvalTaskRow]:
    data = json.loads(path.read_text(encoding="utf-8"))
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError(f"{path}: missing 'tasks' array")
    return [_coerce_eval_task(item) for item in tasks]


def _coerce_template(item: object) -> TemplateRow:
    if not isinstance(item, dict):
        raise ValueError(f"template entry not object: {item!r}")
    return TemplateRow(
        id=str(item["id"]),
        sequence=[str(x) for x in item["sequence"]],
        name=str(item["name"]),
        seq_len=int(item["seq_len"]),
        count=int(item["count"]),
        freq_score=float(item["freq_score"]),
        categories=[str(x) for x in item["categories"]],
        example_ad_id=str(item["example_ad_id"]),
        example_body=str(item["example_body"]),
        example_product_desc=str(item["example_product_desc"]),
    )


def _coerce_eval_task(item: object) -> EvalTaskRow:
    if not isinstance(item, dict):
        raise ValueError(f"eval task entry not object: {item!r}")
    ads_raw = item["ads"]
    if not isinstance(ads_raw, list):
        raise ValueError(f"eval task ads not list: {item!r}")
    ads: list[EvalTaskAd] = []
    for ad in ads_raw:
        if not isinstance(ad, dict):
            raise ValueError(f"ad entry not object: {ad!r}")
        ads.append(
            EvalTaskAd(
                slot=str(ad["slot"]),
                ad_id=str(ad["ad_id"]),
                body=str(ad["body"]),
                template_id=str(ad["template_id"]),
                sequence=[str(x) for x in ad["sequence"]],
            )
        )
    return EvalTaskRow(
        id=str(item["id"]),
        task_type=str(item["task_type"]),
        pair_scope=str(item["pair_scope"]),
        category=str(item["category"]),
        cluster_id=str(item.get("cluster_id", "")),
        ads=ads,
    )


async def get_recorded_hash(db_path: Path, name: str) -> str | None:
    async with connect(db_path) as conn:
        cursor = await conn.execute(
            "SELECT sha256 FROM artifact_versions WHERE name = ?", (name,)
        )
        row = await cursor.fetchone()
    return None if row is None else str(row[0])


async def record_hash(db_path: Path, name: str, sha256: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with connect(db_path) as conn:
        await conn.execute(
            """
            INSERT INTO artifact_versions (name, sha256, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET sha256 = excluded.sha256, updated_at = excluded.updated_at
            """,
            (name, sha256, now),
        )
        await conn.commit()


async def upsert_templates(db_path: Path, templates: list[TemplateRow]) -> None:
    async with connect(db_path) as conn:
        await conn.execute("BEGIN")
        for t in templates:
            await conn.execute(
                """
                INSERT INTO templates (id, sequence, name, freq_score, categories, example_body)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  sequence = excluded.sequence,
                  name = excluded.name,
                  freq_score = excluded.freq_score,
                  categories = excluded.categories,
                  example_body = excluded.example_body
                """,
                (
                    t["id"],
                    json.dumps(t["sequence"], ensure_ascii=False),
                    t["name"],
                    t["freq_score"],
                    json.dumps(t["categories"], ensure_ascii=False),
                    t["example_body"],
                ),
            )
        await conn.commit()


async def upsert_eval_tasks(db_path: Path, tasks: list[EvalTaskRow]) -> None:
    async with connect(db_path) as conn:
        await conn.execute("BEGIN")
        for task in tasks:
            ads_payload = [
                {
                    "slot": ad["slot"],
                    "ad_id": ad["ad_id"],
                    "body": ad["body"],
                    "template_id": ad["template_id"],
                    "sequence": ad["sequence"],
                }
                for ad in task["ads"]
            ]
            await conn.execute(
                """
                INSERT INTO eval_tasks (id, task_type, pair_scope, category, cluster_id, ads)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  task_type = excluded.task_type,
                  pair_scope = excluded.pair_scope,
                  category = excluded.category,
                  cluster_id = excluded.cluster_id,
                  ads = excluded.ads
                """,
                (
                    task["id"],
                    task["task_type"],
                    task["pair_scope"],
                    task["category"],
                    task["cluster_id"],
                    json.dumps(ads_payload, ensure_ascii=False),
                ),
            )
        await conn.commit()


def categories_metadata(categories: list[str]) -> str:
    return "|".join(sorted(set(categories)))


def rebuild_chroma_collection(
    chroma_client: ChromaClient,
    collection_name: str,
    embedding_function: Any,
    templates: list[TemplateRow],
) -> None:
    try:
        chroma_client.delete_collection(collection_name)
    except Exception:  # noqa: BLE001 -- chromadb raises various errors when collection is absent
        pass
    collection = chroma_client.create_collection(
        name=collection_name,
        embedding_function=embedding_function,
        metadata={"hnsw:space": "cosine"},
    )
    if not templates:
        return
    ids = [t["id"] for t in templates]
    documents = [t["example_product_desc"] for t in templates]
    metadatas: list[dict[str, Any]] = [
        {
            "seq_len": t["seq_len"],
            "categories": categories_metadata(t["categories"]),
            "freq_score": t["freq_score"],
            "name": t["name"],
        }
        for t in templates
    ]
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)


async def run_sync(
    db_path: Path,
    templates_json: Path,
    eval_tasks_json: Path,
    chroma_client: ChromaClient,
    collection_name: str,
    embedding_function: Any,
) -> None:
    if templates_json.exists():
        new_hash = sha256_file(templates_json)
        recorded = await get_recorded_hash(db_path, "templates")
        if new_hash != recorded:
            templates = read_templates_json(templates_json)
            log.info("artifact_sync: templates changed, upserting %d rows", len(templates))
            await upsert_templates(db_path, templates)
            rebuild_chroma_collection(chroma_client, collection_name, embedding_function, templates)
            await record_hash(db_path, "templates", new_hash)
        else:
            log.info("artifact_sync: templates unchanged")
    else:
        log.warning("artifact_sync: templates JSON missing at %s", templates_json)

    if eval_tasks_json.exists():
        new_hash = sha256_file(eval_tasks_json)
        recorded = await get_recorded_hash(db_path, "eval_tasks")
        if new_hash != recorded:
            tasks = read_eval_tasks_json(eval_tasks_json)
            log.info("artifact_sync: eval_tasks changed, upserting %d rows", len(tasks))
            await upsert_eval_tasks(db_path, tasks)
            await record_hash(db_path, "eval_tasks", new_hash)
        else:
            log.info("artifact_sync: eval_tasks unchanged")
    else:
        log.warning("artifact_sync: eval_tasks JSON missing at %s", eval_tasks_json)
