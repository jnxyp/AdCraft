from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

WinnerSlot = Literal["a", "b", "tie"]
TaskStatus = Literal["pending", "resolved"]


class EvalAd(BaseModel):
    slot: str
    ad_id: str
    body: str
    sequence: list[str]
    seq_len: int
    length_bucket: Literal["xs", "s", "m", "l", "xl"]
    cluster_id: str | None = None


class EvalProgress(BaseModel):
    session_done: int
    responses: int
    resolved: int
    total: int
    resolved_generated: int = 0
    total_generated: int = 0


class EvalNextResponse(BaseModel):
    task_id: str | None
    task_type: str | None
    category: str | None
    pair_scope: str | None
    cluster_id: str | None
    progress: EvalProgress
    ads: list[EvalAd]


class EvalSubmitRequest(BaseModel):
    task_id: str
    task_type: Literal["pair"]
    winner: WinnerSlot
    session_id: str


class EvalSubmitResponse(BaseModel):
    accepted: bool
    task_status: TaskStatus
    vote_count: int
    vote_summary: dict[str, int]
    resolved_winner: WinnerSlot | None


class EvalStatsResponse(BaseModel):
    session_done: int
    resolved: int
    total: int
    responses: int
    bt_updated_at: str | None


class GenerateRequest(BaseModel):
    category: str
    product_desc: str
    length: Literal["xs", "s", "m", "l", "xl"]
    generation_prompt: str | None = None


class StructuredSegmentResponse(BaseModel):
    label: str
    label_full: str
    text: str


class StructuredVariantResponse(BaseModel):
    template_id: str
    template_name: str
    sequence: list[str]
    segments: list[StructuredSegmentResponse]
    output: str


class TemplateCandidateResponse(BaseModel):
    template_id: str
    template_name: str
    sequence: list[str]
    category_tags: list[str]
    semantic_distance: float | None
    semantic_rank: int
    length: Literal["xs", "s", "m", "l", "xl"]
    bt_score: float | None
    freq_score: float
    final_score: float
    final_rank: int


class FindTemplatesResponse(BaseModel):
    category: str
    product_desc: str
    length: Literal["xs", "s", "m", "l", "xl"]
    templates: list[TemplateCandidateResponse]


class GenerateTemplateVariantRequest(BaseModel):
    template_id: str
    category: str
    product_desc: str
    length: Literal["xs", "s", "m", "l", "xl"]
    generation_prompt: str | None = None


class GenerateDirectResponse(BaseModel):
    output: str


SegmentEditMode = Literal["none", "disable", "regenerate", "longer", "shorter"]


class SegmentEditInstruction(BaseModel):
    mode: SegmentEditMode
    prompt: str | None = None


class RegenerateTemplateWithInstructionsRequest(BaseModel):
    template_id: str
    category: str
    product_desc: str
    length: Literal["xs", "s", "m", "l", "xl"]
    generation_prompt: str | None = None
    current_segments: list[StructuredSegmentResponse]
    instructions: list[SegmentEditInstruction]
