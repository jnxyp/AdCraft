from __future__ import annotations

import json
from pathlib import Path

import aiosqlite
import pytest

from core.database import connect, init_schema
from ranking.bradley_terry import (
    build_comparisons_from_resolved_tasks,
    fit,
    rank_candidates,
)


def test_fit_orders_known_chain() -> None:
    comparisons = [
        ("tmpl_a", "tmpl_b", 1.0),
        ("tmpl_a", "tmpl_b", 1.0),
        ("tmpl_a", "tmpl_b", 1.0),
        ("tmpl_a", "tmpl_c", 1.0),
        ("tmpl_a", "tmpl_c", 1.0),
        ("tmpl_a", "tmpl_c", 1.0),
        ("tmpl_b", "tmpl_c", 1.0),
        ("tmpl_b", "tmpl_c", 1.0),
        ("tmpl_b", "tmpl_c", 1.0),
        ("tmpl_b", "tmpl_c", 1.0),
        ("tmpl_c", "tmpl_a", 1.0),
    ]

    scores = fit(comparisons)

    assert scores["tmpl_a"] > scores["tmpl_b"] > scores["tmpl_c"]


def test_fit_cold_start_returns_empty_and_rank_falls_back_to_freq_score() -> None:
    scores = fit([("tmpl_a", "tmpl_b", 1.0)] * 9)
    candidates: list[dict[str, object]] = [
        {"id": "tmpl_low", "freq_score": 0.1},
        {"id": "tmpl_high", "freq_score": 0.9},
        {"id": "tmpl_mid", "freq_score": 0.5},
        {"id": "tmpl_extra", "freq_score": 0.2},
    ]

    ranked = rank_candidates(candidates, scores)

    assert scores == {}
    assert [candidate["id"] for candidate in ranked] == ["tmpl_high", "tmpl_mid", "tmpl_extra"]


def test_rank_candidates_uses_bt_scores_and_places_unknown_after_known() -> None:
    candidates: list[dict[str, object]] = [
        {"id": "tmpl_unknown", "freq_score": 0.99},
        {"id": "tmpl_b", "freq_score": 0.1},
        {"id": "tmpl_a", "freq_score": 0.2},
        {"id": "tmpl_c", "freq_score": 0.3},
    ]

    ranked = rank_candidates(candidates, {"tmpl_a": 2.0, "tmpl_b": 1.0})

    assert [candidate["id"] for candidate in ranked] == ["tmpl_a", "tmpl_b", "tmpl_unknown"]


@pytest.mark.asyncio
async def test_build_comparisons_from_resolved_tasks_handles_a_b_and_tie(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    await init_schema(db_path)

    async with connect(db_path) as conn:
        await _insert_eval_task(conn, "task_a", "tmpl_a1", "tmpl_b1")
        await _insert_eval_task(conn, "task_b", "tmpl_a2", "tmpl_b2")
        await _insert_eval_task(conn, "task_tie", "tmpl_a3", "tmpl_b3")
        await conn.execute(
            """
            INSERT INTO resolved_eval_tasks
              (task_id, resolved_winner_slot, vote_count, vote_summary, resolved_at)
            VALUES
              (?, ?, ?, ?, datetime('now')),
              (?, ?, ?, ?, datetime('now')),
              (?, ?, ?, ?, datetime('now'))
            """,
            (
                "task_a",
                "a",
                3,
                json.dumps({"a": 2, "b": 1, "tie": 0}),
                "task_b",
                "b",
                3,
                json.dumps({"a": 1, "b": 2, "tie": 0}),
                "task_tie",
                "tie",
                5,
                json.dumps({"a": 2, "b": 2, "tie": 1}),
            ),
        )
        await conn.commit()

    comparisons = await build_comparisons_from_resolved_tasks(db_path)

    assert comparisons == [
        ("tmpl_a1", "tmpl_b1", 1.0),
        ("tmpl_b2", "tmpl_a2", 1.0),
        ("tmpl_a3", "tmpl_b3", 0.5),
        ("tmpl_b3", "tmpl_a3", 0.5),
    ]


async def _insert_eval_task(
    conn: aiosqlite.Connection,
    task_id: str,
    template_a: str,
    template_b: str,
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
    await conn.execute(
        """
        INSERT INTO eval_tasks (id, task_type, pair_scope, category, cluster_id, ads)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (task_id, "pair", "same_cluster", "tech", "", json.dumps(ads)),
    )
