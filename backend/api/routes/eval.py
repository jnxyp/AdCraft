from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import cast

import aiosqlite
from fastapi import APIRouter, HTTPException, Query, status

from api.schemas import (
    EvalAd,
    EvalNextResponse,
    EvalProgress,
    EvalStatsResponse,
    EvalSubmitRequest,
    EvalSubmitResponse,
    WinnerSlot,
)
from core.database import connect

MIN_VOTES_FOR_MAJORITY = 3


def create_eval_router(db_path: Path, max_votes: int = 5) -> APIRouter:
    router = APIRouter(prefix="/api/eval", tags=["eval"])

    @router.get("/next", response_model=EvalNextResponse)
    async def next_eval_task(session_id: str = Query(min_length=1)) -> EvalNextResponse:
        async with connect(db_path) as conn:
            progress = await _load_progress(conn, session_id)
            row = await (
                await conn.execute(
                    """
                    SELECT
                      e.id,
                      e.task_type,
                      e.category,
                      e.ads,
                      (SELECT COUNT(*) FROM eval_responses r WHERE r.task_id = e.id) AS vote_count
                    FROM eval_tasks e
                    WHERE NOT EXISTS (
                      SELECT 1 FROM resolved_eval_tasks rt WHERE rt.task_id = e.id
                    )
                    AND NOT EXISTS (
                      SELECT 1 FROM eval_responses mine
                      WHERE mine.task_id = e.id AND mine.session_id = ?
                    )
                    ORDER BY vote_count DESC, e.id
                    LIMIT 1
                    """,
                    (session_id,),
                )
            ).fetchone()

        if row is None:
            return EvalNextResponse(
                task_id=None,
                task_type=None,
                category=None,
                progress=progress,
                ads=[],
            )

        return EvalNextResponse(
            task_id=str(row["id"]),
            task_type=str(row["task_type"]),
            category=str(row["category"]),
            progress=progress,
            ads=_public_ads(str(row["ads"])),
        )

    @router.post("/submit", response_model=EvalSubmitResponse)
    async def submit_eval_response(payload: EvalSubmitRequest) -> EvalSubmitResponse:
        async with connect(db_path) as conn:
            task = await (
                await conn.execute(
                    "SELECT task_type FROM eval_tasks WHERE id = ?",
                    (payload.task_id,),
                )
            ).fetchone()
            if task is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
            if str(task["task_type"]) != payload.task_type:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="task type mismatch")

            resolved = await (
                await conn.execute(
                    "SELECT resolved_winner_slot FROM resolved_eval_tasks WHERE task_id = ?",
                    (payload.task_id,),
                )
            ).fetchone()
            if resolved is not None:
                summary = await _vote_summary(conn, payload.task_id)
                return EvalSubmitResponse(
                    accepted=False,
                    task_status="resolved",
                    vote_count=sum(summary.values()),
                    vote_summary=summary,
                    resolved_winner=_winner_slot(str(resolved["resolved_winner_slot"])),
                )

            try:
                await conn.execute(
                    """
                    INSERT INTO eval_responses (id, task_id, session_id, winner_slot, created_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                    """,
                    (str(uuid.uuid4()), payload.task_id, payload.session_id, payload.winner),
                )
                await conn.commit()
            except aiosqlite.IntegrityError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="session already submitted this task",
                ) from exc

            resolved_winner = await _try_resolve(conn, payload.task_id, max_votes)
            summary = await _vote_summary(conn, payload.task_id)
            return EvalSubmitResponse(
                accepted=True,
                task_status="resolved" if resolved_winner is not None else "pending",
                vote_count=sum(summary.values()),
                vote_summary=summary,
                resolved_winner=resolved_winner,
            )

    @router.get("/stats", response_model=EvalStatsResponse)
    async def eval_stats(session_id: str = Query(min_length=1)) -> EvalStatsResponse:
        async with connect(db_path) as conn:
            progress = await _load_progress(conn, session_id)
            responses = await _count(conn, "SELECT COUNT(*) FROM eval_responses")
            bt_row = await (
                await conn.execute("SELECT MAX(updated_at) AS updated_at FROM template_bt_scores")
            ).fetchone()
        updated_at = None if bt_row is None or bt_row["updated_at"] is None else str(bt_row["updated_at"])
        return EvalStatsResponse(
            session_done=progress.session_done,
            resolved=progress.resolved,
            total=progress.total,
            responses=responses,
            bt_updated_at=updated_at,
        )

    return router


async def _load_progress(conn: aiosqlite.Connection, session_id: str) -> EvalProgress:
    return EvalProgress(
        session_done=await _count(
            conn,
            "SELECT COUNT(*) FROM eval_responses WHERE session_id = ?",
            (session_id,),
        ),
        resolved=await _count(conn, "SELECT COUNT(*) FROM resolved_eval_tasks"),
        total=await _count(conn, "SELECT COUNT(*) FROM eval_tasks"),
    )


async def _try_resolve(
    conn: aiosqlite.Connection,
    task_id: str,
    max_votes: int,
) -> WinnerSlot | None:
    summary = await _vote_summary(conn, task_id)
    total = sum(summary.values())
    winner = _strict_majority(summary, total) if total >= min(MIN_VOTES_FOR_MAJORITY, max_votes) else None
    if winner is None and total >= max_votes:
        winner = "tie"
    if winner is None:
        return None

    await conn.execute(
        """
        INSERT INTO resolved_eval_tasks
          (task_id, resolved_winner_slot, vote_count, vote_summary, resolved_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(task_id) DO NOTHING
        """,
        (task_id, winner, total, json.dumps(summary, sort_keys=True)),
    )
    await conn.commit()
    return winner


def _strict_majority(summary: dict[str, int], total: int) -> WinnerSlot | None:
    for slot in ("a", "b", "tie"):
        if summary[slot] > total / 2:
            return _winner_slot(slot)
    return None


async def _vote_summary(conn: aiosqlite.Connection, task_id: str) -> dict[str, int]:
    summary = {"a": 0, "b": 0, "tie": 0}
    rows = await (
        await conn.execute(
            """
            SELECT winner_slot, COUNT(*) AS votes
            FROM eval_responses
            WHERE task_id = ?
            GROUP BY winner_slot
            """,
            (task_id,),
        )
    ).fetchall()
    for row in rows:
        slot = str(row["winner_slot"])
        if slot in summary:
            summary[slot] = int(row["votes"])
    return summary


async def _count(
    conn: aiosqlite.Connection,
    sql: str,
    params: tuple[str, ...] = (),
) -> int:
    row = await (await conn.execute(sql, params)).fetchone()
    if row is None:
        return 0
    return int(row[0])


def _public_ads(raw_ads: str) -> list[EvalAd]:
    data = json.loads(raw_ads)
    if not isinstance(data, list):
        raise ValueError("eval task ads must be a JSON array")

    ads: list[EvalAd] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("eval task ad must be a JSON object")
        ads.append(
            EvalAd(
                slot=str(item["slot"]),
                ad_id=str(item["ad_id"]),
                body=str(item["body"]),
            )
        )
    return ads


def _winner_slot(value: str) -> WinnerSlot:
    if value == "a" or value == "b" or value == "tie":
        return cast(WinnerSlot, value)
    raise ValueError(f"unsupported winner slot: {value}")
