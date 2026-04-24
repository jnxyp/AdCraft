"""SQLite schema and connection helpers.

`backend/core/database.py` owns all DDL for the runtime SQLite database. Both the
artifact sync and the eval API rely on these tables existing, so `init_schema` runs
first in the FastAPI lifespan (see plan-generation.md §1.0).
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS templates (
      id TEXT PRIMARY KEY,
      sequence TEXT NOT NULL,
      name TEXT NOT NULL,
      freq_score REAL NOT NULL,
      categories TEXT NOT NULL,
      example_body TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS eval_tasks (
      id TEXT PRIMARY KEY,
      task_type TEXT NOT NULL,
      pair_scope TEXT NOT NULL,
      category TEXT NOT NULL,
      ads TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS eval_responses (
      id TEXT PRIMARY KEY,
      task_id TEXT NOT NULL,
      session_id TEXT NOT NULL,
      winner_slot TEXT NOT NULL,
      created_at DATETIME NOT NULL,
      UNIQUE(session_id, task_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_eval_responses_task ON eval_responses(task_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_eval_responses_session ON eval_responses(session_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS resolved_eval_tasks (
      task_id TEXT PRIMARY KEY,
      resolved_winner_slot TEXT NOT NULL,
      vote_count INTEGER NOT NULL,
      vote_summary TEXT NOT NULL,
      resolved_at DATETIME NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS template_bt_scores (
      template_id TEXT PRIMARY KEY,
      beta REAL NOT NULL,
      updated_at DATETIME NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS generations (
      id TEXT PRIMARY KEY,
      created_at DATETIME NOT NULL,
      category TEXT NOT NULL,
      product_desc TEXT NOT NULL,
      generation_prompt TEXT,
      variants TEXT NOT NULL,
      direct_output TEXT NOT NULL,
      image_path TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS artifact_versions (
      name TEXT PRIMARY KEY,
      sha256 TEXT NOT NULL,
      updated_at DATETIME NOT NULL
    )
    """,
)


async def init_schema(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        for stmt in SCHEMA_STATEMENTS:
            await conn.execute(stmt)
        await conn.commit()


@asynccontextmanager
async def connect(db_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        yield conn
