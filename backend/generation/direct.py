from __future__ import annotations

from typing import Protocol

from generation.prompts import render_direct_system_prompt, render_direct_user_prompt


class TextGenerator(Protocol):
    async def generate(self, *, system_prompt: str, user_prompt: str) -> str: ...


async def generate_direct_output(
    *,
    text_generator: TextGenerator,
    category: str,
    product_desc: str,
    length: str,
    generation_prompt: str | None,
) -> str:
    output = await text_generator.generate(
        system_prompt=render_direct_system_prompt(),
        user_prompt=render_direct_user_prompt(
            category=category,
            product_desc=product_desc,
            length=length,
            generation_prompt=generation_prompt,
        ),
    )
    return output.strip()
