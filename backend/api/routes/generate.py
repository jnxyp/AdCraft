from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol, cast

from fastapi import APIRouter, HTTPException, Request, status
from openai import AsyncOpenAI

from api.schemas import (
    FindTemplatesResponse,
    GenerateDirectResponse,
    GenerateRequest,
    RegenerateTemplateWithInstructionsRequest,
    SegmentEditInstruction,
    StructuredSegmentResponse,
    GenerateTemplateVariantRequest,
    StructuredVariantResponse,
    TemplateCandidateResponse,
)
from core.config import Settings
from generation.direct import generate_direct_output
from generation.structured import SegmentEdit, StructuredVariant, apply_structured_instructions, generate_structured_variants
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
            reasoning={"effort": "high"},
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
            templates=[
                _candidate_response(candidate, length=payload.length)
                for candidate in candidates
            ],
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

    @router.post("/generate/template-regenerate-full", response_model=StructuredVariantResponse)
    async def regenerate_template_full_endpoint(
        payload: GenerateTemplateVariantRequest,
        request: Request,
    ) -> StructuredVariantResponse:
        settings = settings_override or _settings_from_app(request)
        retriever = retriever_override or _retriever_from_app(request)
        text_generator = text_generator_override or OpenAITextGenerator(
            client=AsyncOpenAI(api_key=settings.openai_api_key),
            model=settings.openai_chat_model,
        )
        target = await _find_template_or_404(
            retriever=retriever,
            template_id=payload.template_id,
            category=payload.category,
            product_desc=payload.product_desc,
            length=payload.length,
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
                detail="Failed to regenerate variant",
            )
        return _variant_response(variants[0])

    @router.post("/generate/template-apply-instructions", response_model=StructuredVariantResponse)
    async def apply_template_instructions_endpoint(
        payload: RegenerateTemplateWithInstructionsRequest,
        request: Request,
    ) -> StructuredVariantResponse:
        settings = settings_override or _settings_from_app(request)
        retriever = retriever_override or _retriever_from_app(request)
        text_generator = text_generator_override or OpenAITextGenerator(
            client=AsyncOpenAI(api_key=settings.openai_api_key),
            model=settings.openai_chat_model,
        )
        target = await _find_template_or_404(
            retriever=retriever,
            template_id=payload.template_id,
            category=payload.category,
            product_desc=payload.product_desc,
            length=payload.length,
        )
        sequence = target["name"].split("→")
        if len(payload.current_segments) != len(sequence) or len(payload.instructions) != len(sequence):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="segments/instructions length must match template sequence",
            )
        variant = await apply_structured_instructions(
            text_generator=text_generator,
            category=payload.category,
            product_desc=payload.product_desc,
            generation_prompt=payload.generation_prompt,
            template=target,
            current_segments=[
                {
                    "label": segment.label,
                    "label_full": segment.label_full,
                    "text": segment.text,
                }
                for segment in payload.current_segments
            ],
            instructions=[_coerce_instruction(item) for item in payload.instructions],
        )
        return _variant_response(variant)

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


def _candidate_response(
    candidate: Template,
    *,
    length: Literal["xs", "s", "m", "l", "xl"],
) -> TemplateCandidateResponse:
    sequence = candidate["name"].split("→")
    semantic_rank = candidate.get("semantic_rank")
    if not isinstance(semantic_rank, int):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="semantic_rank missing from retriever result",
        )
    final_rank = candidate.get("final_rank")
    if not isinstance(final_rank, int):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="final_rank missing from retriever result",
        )
    final_score = candidate.get("final_score")
    if not isinstance(final_score, int | float):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="final_score missing from retriever result",
        )
    bt_score = candidate.get("bt_score")
    return TemplateCandidateResponse(
        template_id=candidate["id"],
        template_name=candidate["name"],
        sequence=sequence,
        category_tags=[item for item in candidate["categories"].split("|") if item],
        semantic_distance=candidate.get("semantic_distance"),
        semantic_rank=semantic_rank,
        length=length,
        bt_score=bt_score if isinstance(bt_score, int | float) else None,
        freq_score=candidate["freq_score"],
        final_score=float(final_score),
        final_rank=final_rank,
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


async def _find_template_or_404(
    *,
    retriever: RetrieverLike,
    template_id: str,
    category: str,
    product_desc: str,
    length: Literal["xs", "s", "m", "l", "xl"],
) -> Template:
    candidates = await retriever.query_ranked(
        category=category,
        product_desc=product_desc,
        length=length,
        limit=50,
    )
    target = next((candidate for candidate in candidates if candidate["id"] == template_id), None)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found in current category",
        )
    return target


def _coerce_instruction(item: SegmentEditInstruction) -> SegmentEdit:
    return {"mode": item.mode, "prompt": item.prompt}
