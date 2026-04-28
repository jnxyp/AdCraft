from __future__ import annotations

import asyncio
from typing import Protocol, TypedDict

from generation.prompts import render_structured_system_prompt, render_structured_user_prompt
from retrieval.retriever import Template


class StructuredVariant(TypedDict):
    template_id: str
    template_name: str
    sequence: list[str]
    output: str


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
    output = await text_generator.generate(
        system_prompt=render_structured_system_prompt(),
        user_prompt=render_structured_user_prompt(
            category=category,
            product_desc=product_desc,
            template_name=template["name"],
            sequence=sequence,
            generation_prompt=generation_prompt,
        ),
    )
    return StructuredVariant(
        template_id=template["id"],
        template_name=template["name"],
        sequence=sequence,
        output=output.strip(),
    )
