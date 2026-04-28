from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, cast

import chromadb
from chromadb.utils import embedding_functions
from fastapi import FastAPI

from api.routes.eval import create_eval_router
from api.routes.generate import create_generate_router
from core.config import Settings, load_settings
from core.database import connect, init_schema
from ranking.bradley_terry import build_comparisons_from_resolved_tasks, fit
from retrieval.retriever import ChromaClient as RetrieverChromaClient
from retrieval.retriever import Retriever
from sync.artifact_sync import ChromaClient as SyncChromaClient
from sync.artifact_sync import run_sync


class BtScoreSink(Protocol):
    def refresh_bt_scores(self, scores: dict[str, float]) -> None: ...


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    await init_schema(settings.db_path)

    chroma_client_object: object = chromadb.PersistentClient(path=settings.chromadb_dir)
    embedding_function: object = embedding_functions.OpenAIEmbeddingFunction(
        api_key=settings.openai_api_key,
        model_name=settings.openai_embedding_model,
    )
    await run_sync(
        db_path=settings.db_path,
        templates_json=settings.pipeline_data_dir / "ds0_templates.json",
        eval_tasks_json=settings.pipeline_data_dir / "ds0_eval_tasks.json",
        chroma_client=cast(SyncChromaClient, chroma_client_object),
        collection_name=settings.chroma_collection_name,
        embedding_function=embedding_function,
    )

    retriever = Retriever(
        cast(RetrieverChromaClient, chroma_client_object),
        collection_name=settings.chroma_collection_name,
    )
    retriever.refresh_bt_scores(await load_bt_scores(settings.db_path))
    app.state.settings = settings
    app.state.retriever = retriever

    refit_task = asyncio.create_task(bt_refit_task(settings.db_path, retriever, settings.bt_refit_interval_seconds))
    try:
        yield
    finally:
        refit_task.cancel()
        try:
            await refit_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="AD Craft API", lifespan=lifespan)
app.include_router(create_eval_router(load_settings().db_path, max_votes=load_settings().eval_max_votes))
app.include_router(create_generate_router(load_settings().db_path))


async def bt_refit_task(
    db_path: Path,
    retriever: BtScoreSink,
    interval_seconds: int,
) -> None:
    last_count = await count_resolved_tasks(db_path)
    while True:
        await asyncio.sleep(interval_seconds)
        current_count = await count_resolved_tasks(db_path)
        if current_count > last_count:
            await refit_bt_scores_once(db_path, retriever)
            last_count = current_count


async def refit_bt_scores_once(db_path: Path, retriever: BtScoreSink) -> dict[str, float]:
    comparisons = await build_comparisons_from_resolved_tasks(db_path)
    scores = fit(comparisons)
    await replace_bt_scores(db_path, scores)
    retriever.refresh_bt_scores(scores)
    return scores


async def load_bt_scores(db_path: Path) -> dict[str, float]:
    async with connect(db_path) as conn:
        rows = await (await conn.execute("SELECT template_id, beta FROM template_bt_scores")).fetchall()
    return {str(row["template_id"]): float(row["beta"]) for row in rows}


async def replace_bt_scores(db_path: Path, scores: dict[str, float]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with connect(db_path) as conn:
        await conn.execute("BEGIN")
        await conn.execute("DELETE FROM template_bt_scores")
        for template_id, beta in scores.items():
            await conn.execute(
                """
                INSERT INTO template_bt_scores (template_id, beta, updated_at)
                VALUES (?, ?, ?)
                """,
                (template_id, beta, now),
            )
        await conn.commit()


async def count_resolved_tasks(db_path: Path) -> int:
    async with connect(db_path) as conn:
        row = await (await conn.execute("SELECT COUNT(*) FROM resolved_eval_tasks")).fetchone()
    if row is None:
        return 0
    return int(row[0])
