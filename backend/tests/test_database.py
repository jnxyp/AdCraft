from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from core.database import init_schema

EXPECTED_TABLES: frozenset[str] = frozenset({
    "templates",
    "eval_tasks",
    "eval_responses",
    "resolved_eval_tasks",
    "template_bt_scores",
    "generations",
    "artifact_versions",
})


@pytest.mark.asyncio
async def test_init_schema_creates_all_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    await init_schema(db_path)
    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        rows = await cursor.fetchall()
    names: frozenset[str] = frozenset(row[0] for row in rows)
    assert EXPECTED_TABLES.issubset(names), names


@pytest.mark.asyncio
async def test_init_schema_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    await init_schema(db_path)
    await init_schema(db_path)
    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute("SELECT count(*) FROM templates")
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 0


@pytest.mark.asyncio
async def test_eval_responses_unique_session_task(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    await init_schema(db_path)
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "INSERT INTO eval_responses (id, task_id, session_id, winner_slot, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("r1", "t1", "s1", "a"),
        )
        await conn.commit()
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                "INSERT INTO eval_responses (id, task_id, session_id, winner_slot, created_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                ("r2", "t1", "s1", "b"),
            )
            await conn.commit()
