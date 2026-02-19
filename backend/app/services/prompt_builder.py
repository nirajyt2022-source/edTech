"""
Prompt Builder — grounded prompt construction for worksheet generation.

Two public functions:

  build_compressed_curriculum_context(context: GenerationContext) -> str
    Encodes curriculum metadata into a compact, token-efficient string that
    grounds the LLM in NCERT chapter scope. Uses structured text formatting
    (no external dependencies) to pack maximum information into minimum tokens.

  build_question_prompt(slot: dict, context: GenerationContext) -> str
    Returns additional instruction text to append to a slot_instruction.
    Injects NCERT chapter, valid skill tags, Bloom's level, and
    scaffolding/challenge directives as appropriate.

Note on "toonify": there is no real Python package called toonify for text
encoding. The equivalent goal — compressing curriculum context for LLM prompts —
is achieved here with structured plain-text formatting, which is more
token-efficient and fully dependency-free.
"""
from __future__ import annotations

from app.services.topic_intelligence import GenerationContext

# ---------------------------------------------------------------------------
# Bloom's taxonomy directives
# ---------------------------------------------------------------------------

_BLOOM_DIRECTIVES: dict[str, str] = {
    "recall": (
        "RECALL-LEVEL question: ask the child to identify, name, or state a fact "
        "directly from what they have learned. No multi-step reasoning required."
    ),
    "application": (
        "APPLICATION-LEVEL question: ask the child to use their knowledge to solve "
        "a new problem or a real-life scenario. One or two steps is appropriate."
    ),
    "reasoning": (
        "REASONING-LEVEL question: ask the child to analyse, justify, compare, or "
        "evaluate. Multi-step thinking is required and expected."
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_compressed_curriculum_context(context: GenerationContext) -> str:
    """
    Build a compact, token-efficient encoding of the curriculum metadata.

    The encoding uses a structured plain-text format that packs maximum
    information into minimum tokens — more efficient than JSON for LLM prompts.

    Example output:
        TOPIC: Addition (carries) | CHAPTER: Addition (carries) | GRADE: 3 | SUBJECT: Maths
        OBJECTIVES: Add 3-digit numbers where carrying is needed; Spot common errors; Solve word problems
        SKILL_TAGS: column_add_with_carry, addition_word_problem, addition_error_spot
        BLOOM: recall | SCAFFOLDING: true | CHALLENGE: false
    """
    # Line 1: Identity
    line1 = (
        f"TOPIC: {context.topic_slug} | "
        f"CHAPTER: {context.ncert_chapter} | "
        f"GRADE: {context.grade} | "
        f"SUBJECT: {context.subject}"
    )

    # Line 2: NCERT learning objectives — the "what to teach" ground truth
    if context.ncert_subtopics:
        objectives_str = "; ".join(context.ncert_subtopics)
    else:
        objectives_str = context.topic_slug  # fallback: topic name is the objective
    line2 = f"OBJECTIVES: {objectives_str}"

    # Line 3: Valid skill tags — constrain what question types the LLM can generate.
    # Capped at 8 to stay token-efficient.
    if context.valid_skill_tags:
        tags_str = ", ".join(context.valid_skill_tags[:8])
    else:
        tags_str = "general"
    line3 = f"SKILL_TAGS: {tags_str}"

    # Line 4: Adaptive difficulty config
    line4 = (
        f"BLOOM: {context.bloom_level} | "
        f"SCAFFOLDING: {str(context.scaffolding).lower()} | "
        f"CHALLENGE: {str(context.challenge_mode).lower()}"
    )

    return "\n".join([line1, line2, line3, line4])


def build_question_prompt(slot: dict, context: GenerationContext) -> str:
    """
    Build grounded additional prompt text for a single slot.

    This text is appended to the existing slot_instruction so the LLM:
      - Stays within NCERT chapter scope for this topic
      - Generates at the correct Bloom's taxonomy level
      - Applies scaffolding hints or challenge escalation as appropriate
      - Uses only valid skill tags for this topic

    Args:
        slot: dict with at minimum {"slot_type": str}.
              May also contain "skill_tag", "format_hint", "carry_required", etc.
        context: GenerationContext from TopicIntelligenceAgent.build_context()

    Returns:
        A multi-line string to append to slot_instruction.
        Returns an empty string if context carries no useful information.
    """
    curriculum_block = build_compressed_curriculum_context(context)
    parts: list[str] = [
        "--- NCERT CURRICULUM CONTEXT ---",
        curriculum_block,
        "--- END CURRICULUM CONTEXT ---",
    ]

    # Bloom's taxonomy directive
    bloom_directive = _BLOOM_DIRECTIVES.get(
        context.bloom_level, _BLOOM_DIRECTIVES["recall"]
    )
    parts.append(f"COGNITIVE LEVEL: {bloom_directive}")

    # Scaffolding directive
    if context.scaffolding:
        parts.append(
            "SCAFFOLDING ON: Include a worked example OR a brief hint in the "
            "question stem to support a learner who is still building confidence."
        )

    # Challenge mode directive
    if context.challenge_mode:
        parts.append(
            "CHALLENGE MODE ON: Increase difficulty — use multi-step reasoning, "
            "introduce an unusual context, or require the child to spot a "
            "non-obvious connection."
        )

    # Scope constraint — keep the LLM inside the NCERT chapter boundary
    slot_type = slot.get("slot_type", "")
    if context.valid_skill_tags:
        # Filter tags relevant to this slot type for a tighter constraint
        relevant = [
            t for t in context.valid_skill_tags
            if slot_type.split("_")[0] in t or t.split("_")[0] in slot_type
        ]
        scope_tags = (relevant or context.valid_skill_tags)[:4]
        parts.append(
            f"SCOPE: Generate a question appropriate for: {', '.join(scope_tags)}. "
            f"Stay strictly within the NCERT chapter '{context.ncert_chapter}'."
        )

    # Hindi: inject Devanagari script anchor from profile
    if context.subject.lower() == "hindi":
        try:
            from app.services.slot_engine import get_topic_profile as _gtp  # lazy — avoids circular import
            _profile = _gtp(context.topic_slug)
            _deva = (_profile or {}).get("devanagari_examples", [])
        except Exception:
            _deva = []
        if _deva:
            examples_str = "  ".join(_deva[:8])
            parts.append(
                "HINDI SCRIPT REQUIREMENT: Generate ALL question content in Devanagari "
                f"script. Use these example words as reference: {examples_str}. "
                "NEVER use transliterated Hindi (Roman script for Hindi words). "
                "All Hindi words must use proper Devanagari Unicode characters."
            )
        else:
            parts.append(
                "HINDI SCRIPT REQUIREMENT: Generate ALL question content in Devanagari "
                "script. NEVER use transliterated Hindi (Roman script for Hindi words). "
                "All Hindi words must use proper Devanagari Unicode characters."
            )

    return "\n".join(parts)
