from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from time import perf_counter

import pytest

from generation.direct import generate_direct_output
from generation.structured import generate_structured_variants


@dataclass
class FakeTextGenerator:
    delay_seconds: float = 0.0
    calls: list[tuple[str, str]] = field(default_factory=list)

    async def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        if "Return only valid JSON" in system_prompt:
            sequence_line = next(
                (line for line in user_prompt.splitlines() if line.startswith("Sequence: ")),
                "Sequence: AH -> CTA",
            )
            labels = [part.strip() for part in sequence_line.removeprefix("Sequence: ").split("->")]
            segment_payload = ",".join(
                f'{{"label":"{label}","text":"{label} line."}}' for label in labels
            )
            return f'{{"segments":[{segment_payload}]}}'
        return f"OUT::{len(self.calls)}"


@pytest.mark.asyncio
async def test_generate_structured_variants_returns_top_three() -> None:
    generator = FakeTextGenerator()
    templates = [
        {"id": "t1", "name": "AH→PP→FB→CTA", "categories": "tech", "freq_score": 0.8, "seq_len": 4, "example_product_desc": "d"},
        {"id": "t2", "name": "AH→FB→CTA", "categories": "tech", "freq_score": 0.6, "seq_len": 3, "example_product_desc": "d"},
        {"id": "t3", "name": "PP→FB→SP→CTA", "categories": "tech", "freq_score": 0.5, "seq_len": 4, "example_product_desc": "d"},
        {"id": "t4", "name": "AH→CTA", "categories": "tech", "freq_score": 0.2, "seq_len": 2, "example_product_desc": "d"},
    ]

    variants = await generate_structured_variants(
        text_generator=generator,
        category="tech",
        product_desc="No-code analytics for teams.",
        generation_prompt="Focus on practical outcomes.",
        templates=templates,  # type: ignore[arg-type]
    )

    assert len(variants) == 3
    assert [variant["template_id"] for variant in variants] == ["t1", "t2", "t3"]
    assert variants[0]["sequence"] == ["AH", "PP", "FB", "CTA"]
    assert variants[0]["segments"][0]["label_full"] == "Attention Hook"
    assert len(generator.calls) == 3


@pytest.mark.asyncio
async def test_generate_structured_variants_runs_concurrently() -> None:
    generator = FakeTextGenerator(delay_seconds=0.06)
    templates = [
        {"id": "t1", "name": "AH→PP→FB→CTA", "categories": "tech", "freq_score": 0.8, "seq_len": 4, "example_product_desc": "d"},
        {"id": "t2", "name": "AH→FB→CTA", "categories": "tech", "freq_score": 0.6, "seq_len": 3, "example_product_desc": "d"},
        {"id": "t3", "name": "PP→FB→SP→CTA", "categories": "tech", "freq_score": 0.5, "seq_len": 4, "example_product_desc": "d"},
    ]
    start = perf_counter()
    await generate_structured_variants(
        text_generator=generator,
        category="tech",
        product_desc="No-code analytics for teams.",
        generation_prompt=None,
        templates=templates,  # type: ignore[arg-type]
    )
    elapsed = perf_counter() - start

    assert elapsed < 0.14


@pytest.mark.asyncio
async def test_generate_direct_output_trims_result() -> None:
    generator = FakeTextGenerator()
    result = await generate_direct_output(
        text_generator=generator,
        category="health",
        product_desc="A sleep routine app.",
        length="m",
        generation_prompt="Warm tone.",
    )

    assert result == "OUT::1"
    assert len(generator.calls) == 1
