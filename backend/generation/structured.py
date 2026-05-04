from __future__ import annotations

import asyncio
import json
from typing import Literal, Protocol, TypedDict

from generation.prompts import (
    PATTERN_LABELS,
    render_structured_apply_system_prompt,
    render_structured_apply_user_prompt,
    render_structured_system_prompt,
    render_structured_user_prompt,
)
from retrieval.retriever import Template


class StructuredSegment(TypedDict):
    label: str
    label_full: str
    text: str


class StructuredVariant(TypedDict):
    template_id: str
    template_name: str
    sequence: list[str]
    segments: list[StructuredSegment]
    output: str


SegmentEditMode = Literal["none", "disable", "regenerate", "longer", "shorter"]


class SegmentEdit(TypedDict):
    mode: SegmentEditMode
    prompt: str | None


class TextGenerator(Protocol):
    async def generate(self, *, system_prompt: str, user_prompt: str) -> str: ...


async def generate_structured_variants(
    *,
    text_generator: TextGenerator,
    category: str,
    product_desc: str,
    generation_prompt: str | None,
    templates: list[Template],
) -> list[StructuredVariant]:
    tasks = [
        asyncio.create_task(
            _generate_one(
                text_generator=text_generator,
                category=category,
                product_desc=product_desc,
                generation_prompt=generation_prompt,
                template=template,
            )
        )
        for template in templates[:3]
    ]
    if not tasks:
        return []
    return await asyncio.gather(*tasks)


async def _generate_one(
    *,
    text_generator: TextGenerator,
    category: str,
    product_desc: str,
    generation_prompt: str | None,
    template: Template,
) -> StructuredVariant:
    sequence = template["name"].split("→")
    raw_output = await text_generator.generate(
        system_prompt=render_structured_system_prompt(),
        user_prompt=render_structured_user_prompt(
            category=category,
            product_desc=product_desc,
            template_name=template["name"],
            sequence=sequence,
            generation_prompt=generation_prompt,
        ),
    )
    segments = _parse_segments(raw_output, sequence)
    output = "\n".join(segment["text"] for segment in segments if segment["text"])
    return StructuredVariant(
        template_id=template["id"],
        template_name=template["name"],
        sequence=sequence,
        segments=segments,
        output=output.strip(),
    )


def _parse_segments(raw_output: str, sequence: list[str]) -> list[StructuredSegment]:
    data = json.loads(raw_output)
    if not isinstance(data, dict):
        raise ValueError("structured output must be JSON object")
    raw_segments = data.get("segments")
    if not isinstance(raw_segments, list):
        raise ValueError("structured output must contain segments array")

    parsed: list[StructuredSegment] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            raise ValueError("segment item must be object")
        label = item.get("label")
        text = item.get("text")
        if not isinstance(label, str) or not isinstance(text, str):
            raise ValueError("segment fields label/text must be strings")
        if label not in sequence:
            raise ValueError(f"segment label {label} not in sequence")
        parsed.append(
            StructuredSegment(
                label=label,
                label_full=PATTERN_LABELS.get(label, label),
                text=text.strip(),
            )
        )

    if len(parsed) != len(sequence):
        raise ValueError("segment count does not match sequence length")
    return parsed


async def apply_structured_instructions(
    *,
    text_generator: TextGenerator,
    category: str,
    product_desc: str,
    generation_prompt: str | None,
    template: Template,
    current_segments: list[StructuredSegment],
    instructions: list[SegmentEdit],
) -> StructuredVariant:
    sequence = template["name"].split("→")
    if len(current_segments) != len(sequence) or len(instructions) != len(sequence):
        raise ValueError("segments/instructions length must match template sequence")

    current_pairs = [(segment["label"], segment["text"]) for segment in current_segments]
    instruction_pairs = [(edit["mode"], edit.get("prompt")) for edit in instructions]

    raw_output = await text_generator.generate(
        system_prompt=render_structured_apply_system_prompt(),
        user_prompt=render_structured_apply_user_prompt(
            category=category,
            product_desc=product_desc,
            template_name=template["name"],
            sequence=sequence,
            generation_prompt=generation_prompt,
            current_segments=current_pairs,
            instructions=instruction_pairs,
        ),
    )
    next_segments = _parse_segments(raw_output, sequence)
    enforced_segments = _apply_strict_unchanged(
        current_segments=current_segments,
        generated_segments=next_segments,
        instructions=instructions,
    )
    output = "\n".join(segment["text"] for segment in enforced_segments if segment["text"].strip())
    return StructuredVariant(
        template_id=template["id"],
        template_name=template["name"],
        sequence=sequence,
        segments=enforced_segments,
        output=output.strip(),
    )


def _apply_strict_unchanged(
    *,
    current_segments: list[StructuredSegment],
    generated_segments: list[StructuredSegment],
    instructions: list[SegmentEdit],
) -> list[StructuredSegment]:
    merged: list[StructuredSegment] = []
    for index, generated in enumerate(generated_segments):
        mode = instructions[index]["mode"]
        current = current_segments[index]
        if mode == "none":
            merged.append(
                StructuredSegment(
                    label=generated["label"],
                    label_full=generated["label_full"],
                    text=current["text"],
                )
            )
            continue
        if mode == "disable":
            merged.append(
                StructuredSegment(
                    label=generated["label"],
                    label_full=generated["label_full"],
                    text="",
                )
            )
            continue
        merged.append(generated)
    return merged
