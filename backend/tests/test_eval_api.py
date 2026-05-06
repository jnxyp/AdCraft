from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.eval import create_eval_router
from core.database import connect, init_schema


@pytest.mark.asyncio
async def test_next_returns_unresolved_task_and_progress(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    await init_schema(db_path)
    await _insert_eval_task(db_path, "task_1")
    await _insert_eval_task(db_path, "task_2")
    async with connect(db_path) as conn:
        await conn.execute(
            "INSERT INTO eval_responses (id, task_id, session_id, winner_slot, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("resp_1", "task_1", "session_a", "a"),
        )
        await conn.commit()

    client = _client(db_path)
    response = client.get("/api/eval/next", params={"session_id": "session_a"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "task_2"
    assert payload["pair_scope"] == "same_cluster"
    assert payload["cluster_id"] == "cluster_task_2"
    assert payload["progress"] == {"session_done": 1, "responses": 1, "resolved": 0, "total": 2}
    assert payload["ads"] == [
        {"slot": "a", "ad_id": "task_2_ad_a", "body": "Body A", "sequence": ["AH"], "seq_len": 1, "length_bucket": "xs", "cluster_id": "cluster_task_2"},
        {"slot": "b", "ad_id": "task_2_ad_b", "body": "Body B", "sequence": ["CTA"], "seq_len": 1, "length_bucket": "xs", "cluster_id": "cluster_task_2"},
    ]


@pytest.mark.asyncio
async def test_submit_resolves_on_strict_majority_and_rejects_duplicate(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    await init_schema(db_path)
    await _insert_eval_task(db_path, "task_1")
    client = _client(db_path)

    assert _submit(client, "task_1", "s1", "a")["task_status"] == "pending"
    duplicate = client.post(
        "/api/eval/submit",
        json={"task_id": "task_1", "task_type": "pair", "winner": "b", "session_id": "s1"},
    )
    assert duplicate.status_code == 409
    assert _submit(client, "task_1", "s2", "b")["task_status"] == "pending"
    resolved = _submit(client, "task_1", "s3", "a")

    assert resolved["task_status"] == "resolved"
    assert resolved["resolved_winner"] == "a"
    async with connect(db_path) as conn:
        row = await (
            await conn.execute(
                "SELECT resolved_winner_slot, vote_count, vote_summary FROM resolved_eval_tasks WHERE task_id = ?",
                ("task_1",),
            )
        ).fetchone()
    assert row is not None
    assert row["resolved_winner_slot"] == "a"
    assert row["vote_count"] == 3
    assert json.loads(row["vote_summary"]) == {"a": 2, "b": 1, "tie": 0}


@pytest.mark.asyncio
async def test_submit_resolves_tie_after_five_votes_without_strict_majority(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    await init_schema(db_path)
    await _insert_eval_task(db_path, "task_1")
    client = _client(db_path, max_votes=5)

    assert _submit(client, "task_1", "s1", "a")["task_status"] == "pending"
    assert _submit(client, "task_1", "s2", "b")["task_status"] == "pending"
    assert _submit(client, "task_1", "s3", "tie")["task_status"] == "pending"
    assert _submit(client, "task_1", "s4", "a")["task_status"] == "pending"
    resolved = _submit(client, "task_1", "s5", "b")

    assert resolved["task_status"] == "resolved"
    assert resolved["resolved_winner"] == "tie"
    assert resolved["vote_summary"] == {"a": 2, "b": 2, "tie": 1}


@pytest.mark.asyncio
async def test_next_supports_exclude_task_id_and_randomize(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    await init_schema(db_path)
    await _insert_eval_task(db_path, "task_1")
    await _insert_eval_task(db_path, "task_2")
    client = _client(db_path)

    response = client.get(
        "/api/eval/next",
        params={"session_id": "session_x", "exclude_task_id": "task_1", "randomize": "true"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "task_2"


@pytest.mark.asyncio
async def test_next_can_use_priority_order_when_randomize_false(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    await init_schema(db_path)
    await _insert_eval_task(db_path, "task_1")
    await _insert_eval_task(db_path, "task_2")
    async with connect(db_path) as conn:
        await conn.execute(
            "INSERT INTO eval_responses (id, task_id, session_id, winner_slot, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("resp_1", "task_2", "other_session", "a"),
        )
        await conn.commit()
    client = _client(db_path)

    response = client.get(
        "/api/eval/next",
        params={"session_id": "session_x", "randomize": "false"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "task_2"


def _client(db_path: Path, max_votes: int = 5) -> TestClient:
    app = FastAPI()
    app.include_router(create_eval_router(db_path, max_votes=max_votes))
    return TestClient(app)


def _submit(client: TestClient, task_id: str, session_id: str, winner: str) -> dict[str, object]:
    response = client.post(
        "/api/eval/submit",
        json={"task_id": task_id, "task_type": "pair", "winner": winner, "session_id": session_id},
    )
    assert response.status_code == 200
    return response.json()


async def _insert_eval_task(db_path: Path, task_id: str) -> None:
    ads = [
        {
            "slot": "a",
            "ad_id": f"{task_id}_ad_a",
            "body": "Body A",
            "template_id": f"{task_id}_tmpl_a",
            "sequence": ["AH"],
            "cluster_id": f"cluster_{task_id}",
        },
        {
            "slot": "b",
            "ad_id": f"{task_id}_ad_b",
            "body": "Body B",
            "template_id": f"{task_id}_tmpl_b",
            "sequence": ["CTA"],
            "cluster_id": f"cluster_{task_id}",
        },
    ]
    async with connect(db_path) as conn:
        await conn.execute(
            """
            INSERT INTO eval_tasks (id, task_type, pair_scope, category, cluster_id, ads)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, "pair", "same_cluster", "tech", f"cluster_{task_id}", json.dumps(ads)),
        )
        await conn.commit()
