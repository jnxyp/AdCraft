from __future__ import annotations

from retrieval.retriever import LENGTH_RANGES

PATTERN_LABELS: dict[str, str] = {
    "AH": "Attention Hook",
    "PP": "Pain Point",
    "AG": "Agitation",
    "FB": "Feature-Benefit",
    "SP": "Social Proof",
    "BA": "Before-After",
    "AU": "Authority",
    "UR": "Urgency",
    "OF": "Offer",
    "CTA": "Call To Action",
}


def render_structured_system_prompt() -> str:
    return (
        "You are a professional advertising copywriter.\n"
        "Generate ad copy strictly following the given structural pattern sequence.\n"
        "Rules:\n"
        "- Generate 1-2 sentences per pattern step, in order.\n"
        "- Return only valid JSON, no markdown, no prose.\n"
        "- JSON schema: {\"segments\": [{\"label\": \"AH\", \"text\": \"...\"}]}\n"
        "- label must be exactly one of the sequence labels.\n"
        "- Keep the output in English.\n"
        "- Be specific and persuasive, and avoid generic filler."
    )


def render_structured_user_prompt(
    *,
    category: str,
    product_desc: str,
    template_name: str,
    sequence: list[str],
    generation_prompt: str | None,
) -> str:
    sequence_text = " -> ".join(sequence)
    label_lines = "\n".join(
        f"- {code}: {PATTERN_LABELS.get(code, 'Pattern Step')}" for code in sequence
    )
    extra_guidance = generation_prompt.strip() if generation_prompt else "None"
    return (
        f"Category: {category}\n"
        f"Product Description: {product_desc}\n"
        f"Template Name: {template_name}\n"
        f"Sequence: {sequence_text}\n"
        f"Pattern Labels:\n{label_lines}\n"
        f"Additional Guidance: {extra_guidance}\n"
        "Return only JSON."
    )


def render_direct_system_prompt() -> str:
    return (
        "You are a professional advertising copywriter.\n"
        "Write one persuasive ad copy in English.\n"
        "Do not include pattern labels or markdown."
    )


def render_direct_user_prompt(
    *,
    category: str,
    product_desc: str,
    length: str,
    generation_prompt: str | None,
) -> str:
    min_len, max_len = _length_word_range(length)
    extra_guidance = generation_prompt.strip() if generation_prompt else "None"
    return (
        f"Category: {category}\n"
        f"Product Description: {product_desc}\n"
        f"Target Length: {length} ({min_len}-{max_len} words)\n"
        f"Additional Guidance: {extra_guidance}\n"
        "Output one coherent ad copy."
    )


def _length_word_range(length: str) -> tuple[int, int]:
    min_seq_len, max_seq_len = LENGTH_RANGES[length]
    # Roughly 16-20 words per pattern step.
    return min_seq_len * 16, max_seq_len * 20
