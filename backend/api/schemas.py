from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

WinnerSlot = Literal["a", "b", "tie"]
TaskStatus = Literal["pending", "resolved"]


class EvalAd(BaseModel):
    slot: str
    ad_id: str
    body: str


class EvalProgress(BaseModel):
    session_done: int
    resolved: int
    total: int


class EvalNextResponse(BaseModel):
    task_id: str | None
    task_type: str | None
    category: str | None
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


class StructuredVariantResponse(BaseModel):
    template_id: str
    template_name: str
    sequence: list[str]
    output: str


class GenerateResponse(BaseModel):
    generation_id: str
    category: str
    product_desc: str
    structured_variants: list[StructuredVariantResponse]
    direct_output: str
