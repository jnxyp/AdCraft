from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.database import connect, init_schema
from internal.eval._backfill import AI_SESSION_IDS, PairJudge, run_ai_eval


class AlwaysAJudge(PairJudge):
    async def choose_winner(self, task, session_id: str):  # type: ignore[override]
        return "a"


@pytest.mark.asyncio
async def test_run_ai_eval_resolves_target_tasks_with_fixed_sessions(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    await init_schema(db_path)
    await _insert_eval_task(db_path, "task_1")
    await _insert_eval_task(db_path, "task_2")

    summary = await run_ai_eval(
        db_path=db_path,
        target_resolved_count=2,
        max_votes=5,
        judge=AlwaysAJudge(),
        max_parallel_tasks=10,
    )

    assert summary.requested_resolved == 2
    assert summary.resolved == 2
    assert summary.votes_written == 6
    assert set(summary.resolved_task_ids) == {"task_1", "task_2"}

    async with connect(db_path) as conn:
        response_rows = await (
            await conn.execute(
                "SELECT task_id, session_id, winner_slot FROM eval_responses ORDER BY task_id, created_at, id"
            )
        ).fetchall()
        resolved_rows = await (
            await conn.execute(
                "SELECT task_id, resolved_winner_slot, vote_count, vote_summary FROM resolved_eval_tasks ORDER BY task_id"
            )
        ).fetchall()

    task_1_sessions = [str(row["session_id"]) for row in response_rows if str(row["task_id"]) == "task_1"]
    task_2_sessions = [str(row["session_id"]) for row in response_rows if str(row["task_id"]) == "task_2"]
    assert set(task_1_sessions) == set(AI_SESSION_IDS[:3])
    assert set(task_2_sessions) == set(AI_SESSION_IDS[:3])
    assert all(str(row["winner_slot"]) == "a" for row in response_rows)
    assert len(resolved_rows) == 2
    for row in resolved_rows:
        assert str(row["resolved_winner_slot"]) == "a"
        assert int(row["vote_count"]) == 3
        assert json.loads(str(row["vote_summary"])) == {"a": 3, "b": 0, "tie": 0}


async def _insert_eval_task(db_path: Path, task_id: str) -> None:
    ads = [
        {
            "slot": "a",
            "ad_id": f"{task_id}_ad_a",
            "body": "A body",
            "template_id": f"{task_id}_tmpl_a",
            "sequence": ["AH", "CTA"],
            "cluster_id": f"cluster_{task_id}",
        },
        {
            "slot": "b",
            "ad_id": f"{task_id}_ad_b",
            "body": "B body",
            "template_id": f"{task_id}_tmpl_b",
            "sequence": ["PP", "CTA"],
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
