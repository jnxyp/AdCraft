from __future__ import annotations

import json
import uuid
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, cast

from fastapi import APIRouter, HTTPException, Request, status
from openai import AsyncOpenAI

from api.schemas import (
    FindTemplatesResponse,
    GenerateDirectResponse,
    GenerateRequest,
    GenerateResponse,
    StructuredSegmentResponse,
    GenerateTemplateVariantRequest,
    StructuredVariantResponse,
    TemplateCandidateResponse,
)
from core.config import Settings
from core.database import connect
from generation.direct import generate_direct_output
from generation.structured import StructuredVariant, generate_structured_variants
from retrieval.retriever import Template


class RetrieverLike(Protocol):
    async def query(self, category: str, product_desc: str, length: str) -> list[Template]: ...
    async def query_ranked(
        self, category: str, product_desc: str, length: str, limit: int
    ) -> list[Template]: ...
    async def infer_category(self, product_desc: str, length: str) -> str: ...


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

    @router.post("/generate/find-templates", response_model=FindTemplatesResponse)
    async def find_templates_endpoint(payload: GenerateRequest, request: Request) -> FindTemplatesResponse:
        retriever = retriever_override or _retriever_from_app(request)
        resolved_category = payload.category
        if payload.category == "auto":
            resolved_category = await retriever.infer_category(payload.product_desc, payload.length)

        candidates = await retriever.query_ranked(
            category=resolved_category,
            product_desc=payload.product_desc,
            length=payload.length,
            limit=20,
        )
        if not candidates:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No candidate templates found",
            )
        return FindTemplatesResponse(
            category=resolved_category,
            product_desc=payload.product_desc,
            length=payload.length,
            templates=[_candidate_response(candidate) for candidate in candidates],
        )

    @router.post("/generate", response_model=GenerateResponse)
    async def generate_endpoint(payload: GenerateRequest, request: Request) -> GenerateResponse:
        settings = settings_override or _settings_from_app(request)
        retriever = retriever_override or _retriever_from_app(request)
        text_generator = text_generator_override or OpenAITextGenerator(
            client=AsyncOpenAI(api_key=settings.openai_api_key),
            model=settings.openai_chat_model,
        )

        resolved_category = payload.category
        if payload.category == "auto":
            resolved_category = await retriever.infer_category(payload.product_desc, payload.length)

        candidates = await retriever.query_ranked(
            category=resolved_category,
            product_desc=payload.product_desc,
            length=payload.length,
            limit=20,
        )
        if not candidates:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No candidate templates found",
            )

        structured_task = generate_structured_variants(
            text_generator=text_generator,
            category=resolved_category,
            product_desc=payload.product_desc,
            generation_prompt=payload.generation_prompt,
            templates=candidates[:3],
        )
        direct_task = generate_direct_output(
            text_generator=text_generator,
            category=resolved_category,
            product_desc=payload.product_desc,
            length=payload.length,
            generation_prompt=payload.generation_prompt,
        )
        structured_variants, direct_output = await asyncio.gather(structured_task, direct_task)

        generation_id = str(uuid.uuid4())
        await _insert_generation(
            db_path=db_path,
            generation_id=generation_id,
            category=resolved_category,
            product_desc=payload.product_desc,
            generation_prompt=payload.generation_prompt,
            structured_variants=structured_variants,
            direct_output=direct_output,
        )

        return GenerateResponse(
            generation_id=generation_id,
            category=resolved_category,
            product_desc=payload.product_desc,
            templates=[_candidate_response(candidate) for candidate in candidates],
            structured_variants=[_variant_response(variant) for variant in structured_variants],
            direct_output=direct_output,
        )

    @router.post("/generate/direct", response_model=GenerateDirectResponse)
    async def generate_direct_endpoint(payload: GenerateRequest, request: Request) -> GenerateDirectResponse:
        settings = settings_override or _settings_from_app(request)
        retriever = retriever_override or _retriever_from_app(request)
        text_generator = text_generator_override or OpenAITextGenerator(
            client=AsyncOpenAI(api_key=settings.openai_api_key),
            model=settings.openai_chat_model,
        )
        resolved_category = payload.category
        if payload.category == "auto":
            resolved_category = await retriever.infer_category(payload.product_desc, payload.length)
        output = await generate_direct_output(
            text_generator=text_generator,
            category=resolved_category,
            product_desc=payload.product_desc,
            length=payload.length,
            generation_prompt=payload.generation_prompt,
        )
        return GenerateDirectResponse(output=output)

    @router.post("/generate/template-variant", response_model=StructuredVariantResponse)
    async def generate_template_variant_endpoint(
        payload: GenerateTemplateVariantRequest,
        request: Request,
    ) -> StructuredVariantResponse:
        settings = settings_override or _settings_from_app(request)
        retriever = retriever_override or _retriever_from_app(request)
        text_generator = text_generator_override or OpenAITextGenerator(
            client=AsyncOpenAI(api_key=settings.openai_api_key),
            model=settings.openai_chat_model,
        )
        candidates = await retriever.query_ranked(
            category=payload.category,
            product_desc=payload.product_desc,
            length=payload.length,
            limit=50,
        )
        target = next((candidate for candidate in candidates if candidate["id"] == payload.template_id), None)
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found in current category",
            )
        variants = await generate_structured_variants(
            text_generator=text_generator,
            category=payload.category,
            product_desc=payload.product_desc,
            generation_prompt=payload.generation_prompt,
            templates=[target],
        )
        if not variants:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate variant",
            )
        return _variant_response(variants[0])

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


def _candidate_response(candidate: Template) -> TemplateCandidateResponse:
    sequence = candidate["name"].split("→")
    return TemplateCandidateResponse(
        template_id=candidate["id"],
        template_name=candidate["name"],
        sequence=sequence,
        category_tags=[item for item in candidate["categories"].split("|") if item],
        freq_score=candidate["freq_score"],
    )


def _variant_response(variant: StructuredVariant) -> StructuredVariantResponse:
    return StructuredVariantResponse(
        template_id=variant["template_id"],
        template_name=variant["template_name"],
        sequence=variant["sequence"],
        segments=[
            StructuredSegmentResponse(
                label=segment["label"],
                label_full=segment["label_full"],
                text=segment["text"],
            )
            for segment in variant["segments"]
        ],
        output=variant["output"],
    )


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
