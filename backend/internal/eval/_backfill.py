from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import aiosqlite
from openai import AsyncOpenAI

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from api.routes.eval import _try_resolve
from core.config import load_settings
from core.database import connect

AI_SESSION_IDS: tuple[str, ...] = (
    "ai_eval_1",
    "ai_eval_2",
    "ai_eval_3",
    "ai_eval_4",
    "ai_eval_5",
)
DEFAULT_MAX_PARALLEL_TASKS = 10

WinnerSlot = Literal["a", "b"]


@dataclass(frozen=True)
class EvalTaskAd:
    slot: Literal["a", "b"]
    ad_id: str
    body: str
    sequence: list[str]
    template_id: str
    cluster_id: str | None


@dataclass(frozen=True)
class PendingEvalTask:
    task_id: str
    category: str
    pair_scope: str
    cluster_id: str
    vote_count: int
    ads: tuple[EvalTaskAd, EvalTaskAd]
    used_session_ids: tuple[str, ...]


@dataclass(frozen=True)
class AiEvalSummary:
    requested_resolved: int
    resolved: int
    votes_written: int
    resolved_task_ids: tuple[str, ...]


class PairJudge(Protocol):
    async def choose_winner(self, task: PendingEvalTask, session_id: str) -> WinnerSlot: ...


class OpenAIPairJudge:
    def __init__(self, *, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def choose_winner(self, task: PendingEvalTask, session_id: str) -> WinnerSlot:
        response = await self._client.responses.create(
            model=self._model,
            reasoning={"effort": "medium"},
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "You are evaluating which ad copy is stronger. "
                                "Return only a single letter: A or B. "
                                "Never return tie, explanation, or any extra text."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _render_task_prompt(task=task, session_id=session_id),
                        }
                    ],
                },
            ],
        )
        return _parse_winner(response.output_text)


async def run_ai_eval(
    *,
    db_path: Path,
    target_resolved_count: int,
    max_votes: int,
    judge: PairJudge,
    max_parallel_tasks: int = DEFAULT_MAX_PARALLEL_TASKS,
) -> AiEvalSummary:
    if target_resolved_count <= 0:
        return AiEvalSummary(
            requested_resolved=target_resolved_count,
            resolved=0,
            votes_written=0,
            resolved_task_ids=(),
        )

    candidate_tasks = await _list_pending_tasks(
        db_path=db_path,
        limit=max(target_resolved_count, max_parallel_tasks),
    )
    selected_tasks = candidate_tasks[:target_resolved_count]
    if not selected_tasks:
        return AiEvalSummary(
            requested_resolved=target_resolved_count,
            resolved=0,
            votes_written=0,
            resolved_task_ids=(),
        )

    semaphore = asyncio.Semaphore(max(1, max_parallel_tasks))

    async def _run_one(task: PendingEvalTask) -> tuple[bool, int, str | None]:
        async with semaphore:
            return await _resolve_single_task(
                db_path=db_path,
                task=task,
                max_votes=max_votes,
                judge=judge,
            )

    results = await asyncio.gather(*[_run_one(task) for task in selected_tasks])
    resolved_task_ids = [task_id for resolved, _, task_id in results if resolved and task_id is not None]
    votes_written = sum(votes for _, votes, _ in results)
    return AiEvalSummary(
        requested_resolved=target_resolved_count,
        resolved=len(resolved_task_ids),
        votes_written=votes_written,
        resolved_task_ids=tuple(resolved_task_ids),
    )


async def _resolve_single_task(
    *,
    db_path: Path,
    task: PendingEvalTask,
    max_votes: int,
    judge: PairJudge,
) -> tuple[bool, int, str | None]:
    votes_written = 0
    available_sessions = [session_id for session_id in AI_SESSION_IDS if session_id not in task.used_session_ids]
    if not available_sessions:
        return False, 0, None

    for session_id in available_sessions:
        winner = await judge.choose_winner(task, session_id)
        accepted, resolved_winner = await _submit_ai_vote(
            db_path=db_path,
            task_id=task.task_id,
            session_id=session_id,
            winner=winner,
            max_votes=max_votes,
        )
        if not accepted:
            if resolved_winner is not None:
                return True, votes_written, task.task_id
            continue
        votes_written += 1
        if resolved_winner is not None:
            return True, votes_written, task.task_id
    return False, votes_written, None


async def _submit_ai_vote(
    *,
    db_path: Path,
    task_id: str,
    session_id: str,
    winner: WinnerSlot,
    max_votes: int,
) -> tuple[bool, str | None]:
    async with connect(db_path) as conn:
        resolved = await (
            await conn.execute(
                "SELECT resolved_winner_slot FROM resolved_eval_tasks WHERE task_id = ?",
                (task_id,),
            )
        ).fetchone()
        if resolved is not None:
            return False, str(resolved["resolved_winner_slot"])

        try:
            await conn.execute(
                """
                INSERT INTO eval_responses (id, task_id, session_id, winner_slot, created_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                """,
                (str(uuid.uuid4()), task_id, session_id, winner),
            )
            await conn.commit()
        except aiosqlite.IntegrityError:
            return False, None

        resolved_winner = await _try_resolve(conn, task_id, max_votes)
        return True, resolved_winner


async def _list_pending_tasks(*, db_path: Path, limit: int) -> list[PendingEvalTask]:
    async with connect(db_path) as conn:
        rows = await (
            await conn.execute(
                """
                SELECT
                  e.id,
                  e.category,
                  e.pair_scope,
                  e.cluster_id,
                  e.ads,
                  (SELECT COUNT(*) FROM eval_responses r WHERE r.task_id = e.id) AS vote_count
                FROM eval_tasks e
                WHERE NOT EXISTS (
                  SELECT 1 FROM resolved_eval_tasks rt WHERE rt.task_id = e.id
                )
                ORDER BY vote_count DESC, e.id
                LIMIT ?
                """,
                (limit,),
            )
        ).fetchall()

        tasks: list[PendingEvalTask] = []
        for row in rows:
            task_id = str(row["id"])
            used_rows = await (
                await conn.execute(
                    "SELECT session_id FROM eval_responses WHERE task_id = ? ORDER BY created_at, id",
                    (task_id,),
                )
            ).fetchall()
            used_session_ids = tuple(str(item["session_id"]) for item in used_rows)
            if all(session_id in used_session_ids for session_id in AI_SESSION_IDS):
                continue
            tasks.append(
                PendingEvalTask(
                    task_id=task_id,
                    category=str(row["category"]),
                    pair_scope=str(row["pair_scope"]),
                    cluster_id=str(row["cluster_id"]),
                    vote_count=int(row["vote_count"]),
                    ads=_parse_ads(str(row["ads"])),
                    used_session_ids=used_session_ids,
                )
            )
        return tasks


def _parse_ads(raw_ads: str) -> tuple[EvalTaskAd, EvalTaskAd]:
    data = json.loads(raw_ads)
    if not isinstance(data, list) or len(data) != 2:
        raise ValueError("eval task ads must be a JSON array of length 2")

    ads: list[EvalTaskAd] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("eval task ad must be a JSON object")
        raw_sequence = item.get("sequence")
        if not isinstance(raw_sequence, list):
            raise ValueError("eval task ad sequence must be a JSON array")
        slot = str(item["slot"])
        if slot not in ("a", "b"):
            raise ValueError(f"unsupported eval slot: {slot}")
        ads.append(
            EvalTaskAd(
                slot=slot,
                ad_id=str(item["ad_id"]),
                body=str(item["body"]),
                sequence=[str(part) for part in raw_sequence],
                template_id=str(item["template_id"]),
                cluster_id=str(item["cluster_id"]) if item.get("cluster_id") is not None else None,
            )
        )
    ads.sort(key=lambda ad: ad.slot)
    return ads[0], ads[1]


def _render_task_prompt(*, task: PendingEvalTask, session_id: str) -> str:
    ad_a, ad_b = task.ads
    return (
        f"Session ID: {session_id}\n"
        f"Category: {task.category}\n"
        f"Pair Scope: {task.pair_scope}\n"
        f"Current Vote Count: {task.vote_count}\n\n"
        f"Ad A\n"
        f"- Template ID: {ad_a.template_id}\n"
        f"- Pattern Sequence: {' -> '.join(ad_a.sequence)}\n"
        f"- Body:\n{ad_a.body}\n\n"
        f"Ad B\n"
        f"- Template ID: {ad_b.template_id}\n"
        f"- Pattern Sequence: {' -> '.join(ad_b.sequence)}\n"
        f"- Body:\n{ad_b.body}\n\n"
        "Choose which ad is more effective overall as ad copy. "
        "Reply with only A or B."
    )


def _parse_winner(raw_output: str) -> WinnerSlot:
    normalized = raw_output.strip().upper()
    if normalized.startswith("A"):
        return "a"
    if normalized.startswith("B"):
        return "b"
    raise ValueError(f"AI judge returned unsupported winner: {raw_output!r}")


async def _print_summary(db_path: Path, summary: AiEvalSummary) -> None:
    async with connect(db_path) as conn:
        unresolved_row = await (
            await conn.execute(
                "SELECT COUNT(*) FROM eval_tasks e WHERE NOT EXISTS (SELECT 1 FROM resolved_eval_tasks rt WHERE rt.task_id = e.id)"
            )
        ).fetchone()
        unresolved = int(unresolved_row[0]) if unresolved_row is not None else 0
    print(f"Requested resolved tasks: {summary.requested_resolved}")
    print(f"Resolved by AI run: {summary.resolved}")
    print(f"Votes written: {summary.votes_written}")
    print(f"Unresolved tasks remaining: {unresolved}")
    if summary.resolved_task_ids:
        print("Resolved task ids:")
        for task_id in summary.resolved_task_ids:
            print(f"- {task_id}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve eval tasks with AI votes.")
    parser.add_argument("target_resolved_count", type=int, help="How many tasks to resolve in this run")
    parser.add_argument("--model", default=None, help="Override OpenAI chat model")
    parser.add_argument(
        "--parallel",
        type=int,
        default=DEFAULT_MAX_PARALLEL_TASKS,
        help="How many tasks to evaluate concurrently",
    )
    args = parser.parse_args()

    settings = load_settings()
    model = args.model or settings.openai_chat_model
    judge = OpenAIPairJudge(
        client=AsyncOpenAI(api_key=settings.openai_api_key),
        model=model,
    )
    summary = await run_ai_eval(
        db_path=settings.db_path,
        target_resolved_count=args.target_resolved_count,
        max_votes=settings.eval_max_votes,
        judge=judge,
        max_parallel_tasks=args.parallel,
    )
    await _print_summary(settings.db_path, summary)


if __name__ == "__main__":
    asyncio.run(main())
