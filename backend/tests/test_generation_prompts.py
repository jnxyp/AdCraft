from __future__ import annotations

import pytest

from generation.prompts import (
    render_direct_system_prompt,
    render_direct_user_prompt,
    render_structured_system_prompt,
    render_structured_user_prompt,
)


def test_render_structured_prompt_contains_core_fields() -> None:
    system_prompt = render_structured_system_prompt()
    user_prompt = render_structured_user_prompt(
        category="tech",
        product_desc="A no-code analytics dashboard for indie teams.",
        template_name="AH→PP→FB→CTA",
        sequence=["AH", "PP", "FB", "CTA"],
        generation_prompt="Use a practical, confident tone.",
    )

    assert "strictly following the given structural pattern sequence" in system_prompt
    assert "Return only valid JSON" in system_prompt
    assert "exactly one sentence for each pattern step" in system_prompt
    assert "Do not use dash or hyphen characters" in system_prompt
    assert "must read as one continuous narrative" in system_prompt
    assert "Category: tech" in user_prompt
    assert "Template Name: AH→PP→FB→CTA" in user_prompt
    assert "Sequence: AH -> PP -> FB -> CTA" in user_prompt
    assert "Target Overall Length: about 4 sentences" in user_prompt
    assert "Sentence Constraint: each section must contain exactly 1 sentence." in user_prompt
    assert "Pattern Purposes:" in user_prompt
    assert "Coherence Constraint: transitions between adjacent sections must feel natural and logically connected." in user_prompt
    assert "- AH: Attention Hook" in user_prompt
    assert "- CTA: Call To Action" in user_prompt
    assert "Use a practical, confident tone." in user_prompt


def test_render_direct_prompt_uses_length_range() -> None:
    system_prompt = render_direct_system_prompt()
    user_prompt = render_direct_user_prompt(
        category="health",
        product_desc="An app that helps people improve sleep habits.",
        length="m",
        generation_prompt=None,
    )

    assert "one persuasive ad copy in English" in system_prompt
    assert "Target Length: m (64-100 words)" in user_prompt
    assert "Additional Guidance: None" in user_prompt


def test_render_direct_prompt_raises_for_unsupported_length() -> None:
    with pytest.raises(KeyError):
        render_direct_user_prompt(
            category="tech",
            product_desc="Whatever",
            length="xxl",
            generation_prompt=None,
        )
