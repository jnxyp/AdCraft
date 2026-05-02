from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from core.database import connect, init_schema
from main import count_resolved_tasks, load_bt_scores, refit_bt_scores_once, replace_bt_scores


@dataclass
class FakeRetriever:
    scores: dict[str, float] = field(default_factory=dict)

    def refresh_bt_scores(self, scores: dict[str, float]) -> None:
        self.scores = dict(scores)


@pytest.mark.asyncio
async def test_replace_and_load_bt_scores(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    await init_schema(db_path)

    await replace_bt_scores(db_path, {"tmpl_a": 1.5, "tmpl_b": 0.5})
    scores = await load_bt_scores(db_path)

    assert scores == {"tmpl_a": 1.5, "tmpl_b": 0.5}


@pytest.mark.asyncio
async def test_refit_bt_scores_once_updates_db_and_retriever(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    await init_schema(db_path)
    for idx in range(5):
        await _insert_resolved_pair(db_path, f"task_ab_{idx}", "tmpl_a", "tmpl_b", "a")
    for idx in range(3):
        await _insert_resolved_pair(db_path, f"task_bc_{idx}", "tmpl_b", "tmpl_c", "a")
    for idx in range(2):
        await _insert_resolved_pair(db_path, f"task_ac_{idx}", "tmpl_a", "tmpl_c", "a")

    retriever = FakeRetriever()
    scores = await refit_bt_scores_once(db_path, retriever)

    assert await count_resolved_tasks(db_path) == 10
    assert scores["tmpl_a"] > scores["tmpl_b"] > scores["tmpl_c"]
    assert retriever.scores == scores
    assert await load_bt_scores(db_path) == scores


async def _insert_resolved_pair(
    db_path: Path,
    task_id: str,
    template_a: str,
    template_b: str,
    winner: str,
) -> None:
    ads = [
        {
            "slot": "a",
            "ad_id": f"{task_id}_ad_a",
            "body": "Body A",
            "template_id": template_a,
            "sequence": ["AH"],
        },
        {
            "slot": "b",
            "ad_id": f"{task_id}_ad_b",
            "body": "Body B",
            "template_id": template_b,
            "sequence": ["CTA"],
        },
    ]
    async with connect(db_path) as conn:
        await conn.execute(
            """
            INSERT INTO eval_tasks (id, task_type, pair_scope, category, cluster_id, ads)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, "pair", "same_cluster", "tech", "", json.dumps(ads)),
        )
        await conn.execute(
            """
            INSERT INTO resolved_eval_tasks
              (task_id, resolved_winner_slot, vote_count, vote_summary, resolved_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (task_id, winner, 3, json.dumps({"a": 2, "b": 1, "tie": 0})),
        )
        await conn.commit()
