from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, cast

from fastapi import APIRouter, HTTPException, Request, status
from openai import AsyncOpenAI

from api.schemas import GenerateRequest, GenerateResponse, StructuredVariantResponse
from core.config import Settings
from core.database import connect
from generation.direct import generate_direct_output
from generation.structured import StructuredVariant, generate_structured_variants
from retrieval.retriever import Template


class RetrieverLike(Protocol):
    async def query(self, category: str, product_desc: str, length: str) -> list[Template]: ...


class TextGenerator(Protocol):
    async def generate(self, *, system_prompt: str, user_prompt: str) -> str: ...


class OpenAITextGenerator:
    def __init__(self, *, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        response = await self._client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
            ],
        )
        return response.output_text


def create_generate_router(
    db_path: Path,
    *,
    retriever_override: RetrieverLike | None = None,
    text_generator_override: TextGenerator | None = None,
    settings_override: Settings | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["generate"])

    @router.post("/generate", response_model=GenerateResponse)
    async def generate_endpoint(payload: GenerateRequest, request: Request) -> GenerateResponse:
        settings = settings_override or _settings_from_app(request)
        retriever = retriever_override or _retriever_from_app(request)
        text_generator = text_generator_override or OpenAITextGenerator(
            client=AsyncOpenAI(api_key=settings.openai_api_key),
            model=settings.openai_chat_model,
        )

        candidates = await retriever.query(
            category=payload.category,
            product_desc=payload.product_desc,
            length=payload.length,
        )
        if not candidates:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No candidate templates found",
            )

        structured_variants = await generate_structured_variants(
            text_generator=text_generator,
            category=payload.category,
            product_desc=payload.product_desc,
            generation_prompt=payload.generation_prompt,
            templates=candidates,
        )
        direct_output = await generate_direct_output(
            text_generator=text_generator,
            category=payload.category,
            product_desc=payload.product_desc,
            length=payload.length,
            generation_prompt=payload.generation_prompt,
        )

        generation_id = str(uuid.uuid4())
        await _insert_generation(
            db_path=db_path,
            generation_id=generation_id,
            category=payload.category,
            product_desc=payload.product_desc,
            generation_prompt=payload.generation_prompt,
            structured_variants=structured_variants,
            direct_output=direct_output,
        )

        return GenerateResponse(
            generation_id=generation_id,
            category=payload.category,
            product_desc=payload.product_desc,
            structured_variants=[StructuredVariantResponse(**variant) for variant in structured_variants],
            direct_output=direct_output,
        )

    return router


def _settings_from_app(request: Request) -> Settings:
    settings_obj: object = getattr(request.app.state, "settings", None)
    if not isinstance(settings_obj, Settings):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Application settings are not initialized",
        )
    return settings_obj


def _retriever_from_app(request: Request) -> RetrieverLike:
    retriever_obj: object = getattr(request.app.state, "retriever", None)
    if retriever_obj is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Retriever is not initialized",
        )
    if not hasattr(retriever_obj, "query"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Retriever is invalid",
        )
    return cast(RetrieverLike, retriever_obj)


async def _insert_generation(
    *,
    db_path: Path,
    generation_id: str,
    category: str,
    product_desc: str,
    generation_prompt: str | None,
    structured_variants: list[StructuredVariant],
    direct_output: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with connect(db_path) as conn:
        await conn.execute(
            """
            INSERT INTO generations (
                id,
                created_at,
                category,
                product_desc,
                generation_prompt,
                variants,
                direct_output,
                image_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                generation_id,
                now,
                category,
                product_desc,
                generation_prompt,
                json.dumps(structured_variants, ensure_ascii=False),
                direct_output,
                None,
            ),
        )
        await conn.commit()
