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

PATTERN_DEFINITIONS: dict[str, str] = {
    "AH": "Open with an attention-grabbing first line tied to the audience or context.",
    "PP": "State the audience's concrete pain point or friction clearly.",
    "AG": "Intensify the cost of inaction so the pain feels immediate and important.",
    "FB": "Present a specific feature and translate it into a user-facing benefit.",
    "SP": "Add trust signals like customer results, adoption, ratings, or testimonials.",
    "BA": "Contrast the current before state with the improved after state.",
    "AU": "Reinforce credibility with expert backing, credentials, or proven authority.",
    "UR": "Create urgency with a real reason to act now rather than later.",
    "OF": "Make the concrete offer explicit, including what is included and value.",
    "CTA": "Give a direct action instruction that tells the user exactly what to do next.",
}


def render_structured_system_prompt() -> str:
    return (
        "You are a professional advertising copywriter.\n"
        "Generate ad copy strictly following the given structural pattern sequence.\n"
        "Rules:\n"
        "- Generate exactly one sentence for each pattern step, in order.\n"
        "- Do not split a pattern step into multiple sentences.\n"
        "- Keep AH and CTA especially short and punchy.\n"
        "- Return only valid JSON, no markdown, no prose.\n"
        "- JSON schema: {\"segments\": [{\"label\": \"AH\", \"text\": \"...\"}]}\n"
        "- label must be exactly one of the sequence labels.\n"
        "- Language rule: use the same language as Product Description by default.\n"
        "- If Additional Guidance explicitly specifies a target language, follow that language.\n"
        "- Do not use dash or hyphen characters in generated copy text.\n"
        "- Maintain strong coherence: each section must connect naturally from the previous one.\n"
        "- The full copy must read as one continuous narrative, not isolated fragments.\n"
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
    target_sentence_count = len(sequence)
    label_lines = "\n".join(
        f"- {code}: {PATTERN_LABELS.get(code, 'Pattern Step')}" for code in sequence
    )
    definition_lines = "\n".join(
        f"- {code}: {PATTERN_DEFINITIONS.get(code, 'Follow the named pattern purpose.')}"
        for code in sequence
    )
    extra_guidance = generation_prompt.strip() if generation_prompt else "None"
    return (
        f"Category: {category}\n"
        f"Product Description: {product_desc}\n"
        f"Template Name: {template_name}\n"
        f"Sequence: {sequence_text}\n"
        f"Target Overall Length: about {target_sentence_count} sentences\n"
        "Sentence Constraint: each section must contain exactly 1 sentence.\n"
        f"Pattern Labels:\n{label_lines}\n"
        f"Pattern Purposes:\n{definition_lines}\n"
        "Style Constraint: AH should be concise and high-impact; CTA should be concise and action-oriented.\n"
        "Coherence Constraint: transitions between adjacent sections must feel natural and logically connected.\n"
        f"Additional Guidance: {extra_guidance}\n"
        "Return only JSON."
    )


def render_direct_system_prompt() -> str:
    return (
        "You are a professional advertising copywriter.\n"
        "Generate one ad copy.\n"
        "Language rule: use the same language as Product Description by default.\n"
        "If Additional Guidance explicitly specifies a target language, follow that language.\n"
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
