from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from core.database import connect, init_schema
from sync.artifact_sync import (
    categories_metadata,
    rebuild_chroma_collection,
    run_sync,
)


@dataclass
class FakeChromaCollection:
    name: str
    ids: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    metadatas: list[dict[str, Any]] = field(default_factory=list)

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        self.ids = list(ids)
        self.documents = list(documents)
        self.metadatas = list(metadatas)


@dataclass
class FakeChromaClient:
    collections: dict[str, FakeChromaCollection] = field(default_factory=dict)
    delete_calls: int = 0
    create_calls: int = 0

    def delete_collection(self, name: str) -> None:
        self.delete_calls += 1
        if name not in self.collections:
            raise ValueError(f"collection missing: {name}")
        del self.collections[name]

    def create_collection(
        self,
        name: str,
        embedding_function: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FakeChromaCollection:
        self.create_calls += 1
        col = FakeChromaCollection(name=name)
        self.collections[name] = col
        return col


def _templates_payload() -> dict[str, Any]:
    return {
        "source": "data/ds0_annotated.json",
        "template_count": 2,
        "ad_count": 5,
        "templates": [
            {
                "id": "tmpl_aaa",
                "sequence": ["AH", "FB"],
                "name": "AH→FB",
                "seq_len": 2,
                "count": 3,
                "freq_score": 0.6,
                "categories": ["tech", "ecommerce"],
                "example_ad_id": "ad_1",
                "example_body": "Body A",
                "example_product_desc": "Wireless keyboard with long battery.",
            },
            {
                "id": "tmpl_bbb",
                "sequence": ["PP", "FB", "CTA"],
                "name": "PP→FB→CTA",
                "seq_len": 3,
                "count": 2,
                "freq_score": 0.4,
                "categories": ["health"],
                "example_ad_id": "ad_2",
                "example_body": "Body B",
                "example_product_desc": "Sleep aid device.",
            },
        ],
    }


def _eval_tasks_payload() -> dict[str, Any]:
    return {
        "source_ads": "data/ds0_annotated.json",
        "source_clusters": "data/ds0_clusters.json",
        "source_templates": "data/ds0_templates.json",
        "task_count": 1,
        "tasks": [
            {
                "id": "eval_t1",
                "task_type": "pair",
                "pair_scope": "same_cluster",
                "category": "tech",
                "cluster_id": "tech-0001",
                "ads": [
                    {
                        "slot": "a",
                        "ad_id": "ad_1",
                        "body": "Body A",
                        "template_id": "tmpl_aaa",
                        "sequence": ["AH", "FB"],
                    },
                    {
                        "slot": "b",
                        "ad_id": "ad_2",
                        "body": "Body B",
                        "template_id": "tmpl_bbb",
                        "sequence": ["PP", "FB", "CTA"],
                    },
                ],
            }
        ],
    }


def test_categories_metadata_sorted_pipe_join() -> None:
    assert categories_metadata(["tech", "ecommerce", "tech"]) == "ecommerce|tech"
    assert categories_metadata([]) == ""


def test_rebuild_chroma_collection_replaces_collection() -> None:
    client = FakeChromaClient()
    client.collections["ad_templates"] = FakeChromaCollection(name="ad_templates")
    templates = [
        {
            "id": "tmpl_aaa",
            "sequence": ["AH", "FB"],
            "name": "AH→FB",
            "seq_len": 2,
            "count": 3,
            "freq_score": 0.6,
            "categories": ["tech", "ecommerce"],
            "example_ad_id": "ad_1",
            "example_body": "Body A",
            "example_product_desc": "Wireless keyboard.",
        }
    ]
    rebuild_chroma_collection(client, "ad_templates", embedding_function=None, templates=templates)  # type: ignore[arg-type]
    assert client.delete_calls == 1
    assert client.create_calls == 1
    col = client.collections["ad_templates"]
    assert col.ids == ["tmpl_aaa"]
    assert col.documents == ["Wireless keyboard."]
    assert col.metadatas[0]["seq_len"] == 2
    assert col.metadatas[0]["categories"] == "ecommerce|tech"
    assert col.metadatas[0]["name"] == "AH→FB"


@pytest.mark.asyncio
async def test_run_sync_initial_writes_then_skips(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    await init_schema(db_path)

    templates_path = tmp_path / "templates.json"
    eval_tasks_path = tmp_path / "eval_tasks.json"
    templates_path.write_text(json.dumps(_templates_payload()), encoding="utf-8")
    eval_tasks_path.write_text(json.dumps(_eval_tasks_payload()), encoding="utf-8")

    client = FakeChromaClient()
    await run_sync(db_path, templates_path, eval_tasks_path, client, "ad_templates", embedding_function=None)  # type: ignore[arg-type]

    async with connect(db_path) as conn:
        rows = await (await conn.execute("SELECT id, name, freq_score, categories FROM templates ORDER BY id")).fetchall()
    assert [r[0] for r in rows] == ["tmpl_aaa", "tmpl_bbb"]
    assert json.loads(rows[0][3]) == ["tech", "ecommerce"]

    async with connect(db_path) as conn:
        task_rows = await (
            await conn.execute("SELECT id, pair_scope, category, cluster_id, ads FROM eval_tasks")
        ).fetchall()
    assert task_rows[0][0] == "eval_t1"
    assert task_rows[0][1] == "same_cluster"
    assert task_rows[0][3] == "tech-0001"
    ads_payload = json.loads(task_rows[0][4])
    assert ads_payload[0]["ad_id"] == "ad_1"
    assert ads_payload[0]["template_id"] == "tmpl_aaa"

    # Run again with no changes — chroma should not rebuild
    create_calls_before = client.create_calls
    await run_sync(db_path, templates_path, eval_tasks_path, client, "ad_templates", embedding_function=None)  # type: ignore[arg-type]
    assert client.create_calls == create_calls_before


@pytest.mark.asyncio
async def test_run_sync_preserves_runtime_feedback(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    await init_schema(db_path)

    templates_path = tmp_path / "templates.json"
    eval_tasks_path = tmp_path / "eval_tasks.json"
    templates_path.write_text(json.dumps(_templates_payload()), encoding="utf-8")
    eval_tasks_path.write_text(json.dumps(_eval_tasks_payload()), encoding="utf-8")

    client = FakeChromaClient()
    await run_sync(db_path, templates_path, eval_tasks_path, client, "ad_templates", embedding_function=None)  # type: ignore[arg-type]

    # Insert runtime feedback rows that must survive a second sync
    async with connect(db_path) as conn:
        await conn.execute(
            "INSERT INTO eval_responses (id, task_id, session_id, winner_slot, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("r1", "eval_t1", "s1", "a"),
        )
        await conn.execute(
            "INSERT INTO template_bt_scores (template_id, beta, updated_at) VALUES (?, ?, datetime('now'))",
            ("tmpl_aaa", 1.5),
        )
        await conn.commit()

    # Mutate templates JSON so hash differs
    payload = _templates_payload()
    payload["templates"][0]["freq_score"] = 0.65
    templates_path.write_text(json.dumps(payload), encoding="utf-8")

    await run_sync(db_path, templates_path, eval_tasks_path, client, "ad_templates", embedding_function=None)  # type: ignore[arg-type]

    async with connect(db_path) as conn:
        bt_row = await (await conn.execute("SELECT beta FROM template_bt_scores WHERE template_id='tmpl_aaa'")).fetchone()
        resp_row = await (await conn.execute("SELECT winner_slot FROM eval_responses WHERE id='r1'")).fetchone()
        tmpl_row = await (await conn.execute("SELECT freq_score FROM templates WHERE id='tmpl_aaa'")).fetchone()
    assert bt_row is not None and bt_row[0] == 1.5
    assert resp_row is not None and resp_row[0] == "a"
    assert tmpl_row is not None and tmpl_row[0] == pytest.approx(0.65)
