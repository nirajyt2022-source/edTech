"""
Async tests for the worksheet generation pipeline.

Tests cover:
  - build_system_prompt: composable prompt blocks (standard/visual/mixed)
  - build_user_prompt: parameter injection, Bloom's taxonomy, Hindi Devanagari
  - validate_response: JSON parsing, schema repair, maths verification, topic drift
  - _map_question / _infer_render_format: API response mapping
  - generate_worksheet: end-to-end with mocked LLM (synchronous call, async wrapper)

All tests run FULLY OFFLINE — no LLM calls, no Supabase connection.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.worksheet_generator import (
    build_system_prompt,
    build_user_prompt,
    validate_response,
)
from app.api.worksheets_v2 import _map_question, _infer_render_format


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_question(
    qid: str = "q1",
    qtype: str = "mcq",
    text: str = "What is 2 + 3?",
    options: list | None = None,
    correct_answer: str = "5",
    role: str = "recognition",
    difficulty: str = "easy",
    visual_type: str | None = None,
    visual_data: dict | None = None,
) -> dict:
    return {
        "id": qid,
        "type": qtype,
        "text": text,
        "options": options or (["3", "4", "5", "6"] if qtype == "mcq" else None),
        "correct_answer": correct_answer,
        "explanation": "2 + 3 = 5",
        "difficulty": difficulty,
        "hint": "Count on your fingers",
        "role": role,
        "image_keywords": None,
        "visual_type": visual_type,
        "visual_data": visual_data,
    }


def _make_raw_response(num_questions: int = 5, topic: str = "Addition (carries)") -> str:
    """Build a valid JSON response as the LLM would return."""
    questions = []
    types = ["mcq", "fill_blank", "true_false", "short_answer", "word_problem"]
    roles = ["recognition", "application", "representation", "error_detection", "thinking"]

    for i in range(num_questions):
        q = _make_question(
            qid=f"q{i + 1}",
            qtype=types[i % len(types)],
            text=f"What is {i + 2} + {i + 3}? (addition carry)" if types[i % len(types)] != "fill_blank"
                 else f"{i + 10} + {i + 15} = ______",
            options=["A", "B", "C", "D"] if types[i % len(types)] == "mcq" else
                    (["True", "False"] if types[i % len(types)] == "true_false" else None),
            correct_answer=str(2 * i + 5) if types[i % len(types)] != "true_false" else "True",
            role=roles[i % len(roles)],
        )
        questions.append(q)

    return json.dumps({
        "title": f"Worksheet: {topic}",
        "skill_focus": "Addition with carrying",
        "common_mistake": "Forgetting to carry",
        "parent_tip": "Practice with real coins",
        "learning_objectives": ["Add 2-digit numbers", "Understand carrying"],
        "questions": questions,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 1. build_system_prompt
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildSystemPrompt:
    def test_standard_omits_visual_block(self):
        prompt = build_system_prompt("standard", "Maths")
        assert "VISUAL TYPES" not in prompt
        assert "VISUAL RULES" not in prompt
        assert "RULES:" in prompt

    def test_visual_includes_visual_block(self):
        prompt = build_system_prompt("visual", "Maths")
        assert "VISUAL TYPES" in prompt
        assert "clock" in prompt

    def test_mixed_includes_visual_block(self):
        prompt = build_system_prompt("mixed", "EVS")
        assert "VISUAL TYPES" in prompt

    def test_standard_uses_standard_output_format(self):
        prompt = build_system_prompt("standard", "Maths")
        assert "visual_type" in prompt  # still in schema, just null
        assert "FEW-SHOT EXAMPLES" in prompt

    def test_visual_includes_image_block_for_evs(self):
        prompt = build_system_prompt("visual", "EVS")
        assert "IMAGES:" in prompt or "image_keywords" in prompt

    @pytest.mark.parametrize("style", ["standard", "visual", "mixed"])
    def test_core_rules_always_present(self, style: str):
        prompt = build_system_prompt(style, "Maths")
        assert "CBSE" in prompt
        assert "DIFFICULTY LEVELS" in prompt
        assert "QUESTION TYPES" in prompt


# ─────────────────────────────────────────────────────────────────────────────
# 2. build_user_prompt
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildUserPrompt:
    def test_contains_all_parameters(self):
        prompt = build_user_prompt(
            board="CBSE", grade_level="Class 3", subject="Maths",
            topic="Fractions", difficulty="medium", num_questions=10,
            language="English",
        )
        assert "CBSE" in prompt
        assert "Class 3" in prompt
        assert "Maths" in prompt
        assert "Fractions" in prompt
        assert "medium" in prompt
        assert "10" in prompt

    def test_hindi_devanagari_directive(self):
        prompt = build_user_prompt(
            board="CBSE", grade_level="Class 2", subject="Hindi",
            topic="Matra", difficulty="easy", num_questions=5,
            language="Hindi",
        )
        assert "Devanagari" in prompt
        assert "NEVER use transliterated" in prompt

    def test_fractions_constraint(self):
        prompt = build_user_prompt(
            board="CBSE", grade_level="Class 4", subject="Maths",
            topic="Fractions basics", difficulty="easy", num_questions=5,
            language="English",
        )
        assert "FRACTIONS CONSTRAINT" in prompt

    def test_custom_instructions_appended(self):
        prompt = build_user_prompt(
            board="CBSE", grade_level="Class 3", subject="Maths",
            topic="Addition", difficulty="easy", num_questions=5,
            language="English", custom_instructions="Focus on 3-digit numbers",
        )
        assert "Focus on 3-digit numbers" in prompt

    def test_standard_mode_no_images(self):
        prompt = build_user_prompt(
            board="CBSE", grade_level="Class 3", subject="Maths",
            topic="Addition", difficulty="easy", num_questions=5,
            language="English", problem_style="standard",
        )
        assert "Do NOT use image_keywords" in prompt

    def test_bloom_directive_included(self):
        prompt = build_user_prompt(
            board="CBSE", grade_level="Class 3", subject="Maths",
            topic="Addition", difficulty="hard", num_questions=5,
            language="English",
        )
        assert "COGNITIVE LEVEL" in prompt


# ─────────────────────────────────────────────────────────────────────────────
# 3. validate_response
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateResponse:
    def test_valid_json_parses(self):
        raw = _make_raw_response(5, "Addition (carries)")
        data, warnings = validate_response(raw, "Maths", "Addition (carries)", 5)
        assert "questions" in data
        assert len(data["questions"]) == 5

    def test_markdown_fences_stripped(self):
        inner = _make_raw_response(5, "Addition")
        raw = f"```json\n{inner}\n```"
        data, warnings = validate_response(raw, "Maths", "Addition", 5)
        assert len(data["questions"]) == 5

    def test_empty_questions_raises(self):
        raw = json.dumps({"questions": []})
        with pytest.raises(ValueError, match="no questions"):
            validate_response(raw, "Maths", "Addition", 5)

    def test_unknown_type_defaulted(self):
        raw_data = json.loads(_make_raw_response(1, "Addition"))
        raw_data["questions"][0]["type"] = "bogus_type"
        raw = json.dumps(raw_data)
        data, warnings = validate_response(raw, "Maths", "Addition", 1)
        assert data["questions"][0]["type"] == "short_answer"
        assert any("unknown type" in w for w in warnings)

    def test_count_mismatch_warning(self):
        raw = _make_raw_response(3, "Addition")
        data, warnings = validate_response(raw, "Maths", "Addition", 10)
        assert any("Requested 10 questions" in w for w in warnings)

    def test_maths_answer_auto_correction(self):
        """If the LLM gives a wrong math answer, validation should correct it."""
        raw_data = json.loads(_make_raw_response(1, "Addition"))
        # Set a fill_blank with arithmetic
        raw_data["questions"][0]["type"] = "fill_blank"
        raw_data["questions"][0]["text"] = "25 + 37 = ______"
        raw_data["questions"][0]["correct_answer"] = "99"  # wrong
        raw = json.dumps(raw_data)
        data, warnings = validate_response(raw, "Maths", "Addition", 1)
        # Should auto-correct to 62
        assert data["questions"][0]["correct_answer"] == "62"

    def test_invalid_json_raises(self):
        with pytest.raises((ValueError, json.JSONDecodeError)):
            validate_response("not json at all {{{", "Maths", "Addition", 5)


# ─────────────────────────────────────────────────────────────────────────────
# 4. _map_question / _infer_render_format
# ─────────────────────────────────────────────────────────────────────────────


class TestMapQuestion:
    def test_mcq_mapping(self):
        raw = _make_question(qtype="mcq")
        q = _map_question(raw, 0)
        assert q.id == "q1"
        assert q.type == "mcq"
        assert q.format == "mcq_4"
        assert len(q.options) == 4

    def test_fill_blank_mapping(self):
        raw = _make_question(qtype="fill_blank", text="5 + 3 = ______", options=None)
        q = _map_question(raw, 0)
        assert q.format == "fill_blank"

    def test_true_false_mapping(self):
        raw = _make_question(qtype="true_false", options=["True", "False"])
        q = _map_question(raw, 0)
        assert q.format == "true_false"

    def test_short_answer_default(self):
        raw = _make_question(qtype="short_answer", options=None)
        q = _map_question(raw, 0)
        assert q.format == "short_answer"

    def test_missing_id_gets_default(self):
        raw = _make_question()
        del raw["id"]
        q = _map_question(raw, 3)
        assert q.id == "q4"

    def test_visual_data_preserved(self):
        raw = _make_question(
            visual_type="clock",
            visual_data={"hour": 3, "minute": 30},
        )
        q = _map_question(raw, 0)
        assert q.visual_type == "clock"
        assert q.visual_data == {"hour": 3, "minute": 30}


class TestInferRenderFormat:
    @pytest.mark.parametrize("q_type,options,expected", [
        ("mcq", ["A", "B", "C", "D"], "mcq_4"),
        ("mcq", ["A", "B", "C"], "mcq_3"),
        ("mcq", None, "mcq_4"),
        ("fill_blank", None, "fill_blank"),
        ("true_false", ["True", "False"], "true_false"),
        ("short_answer", None, "short_answer"),
        ("word_problem", None, "short_answer"),
        ("error_detection", None, "short_answer"),
    ])
    def test_format_mapping(self, q_type: str, options: list | None, expected: str):
        assert _infer_render_format(q_type, options) == expected


# ─────────────────────────────────────────────────────────────────────────────
# 5. Async wrapper: generate_worksheet via asyncio.to_thread
# ─────────────────────────────────────────────────────────────────────────────


class TestGenerateWorksheetAsync:
    """Test that generate_worksheet works when called from an async context
    (as the v2 endpoint does via asyncio.to_thread)."""

    def test_generate_worksheet_with_mock_client(self):
        """End-to-end: mock the LLM client, get a valid worksheet back."""
        from app.services.worksheet_generator import generate_worksheet

        # Build a mock client that returns a valid JSON string
        mock_client = MagicMock()
        raw_response = _make_raw_response(5, "Addition (carries)")
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=raw_response))]
        )

        # Patch curriculum context to avoid DB
        with patch("app.services.curriculum.get_curriculum_context", return_value=None):
            data, elapsed_ms, warnings = generate_worksheet(
                client=mock_client,
                board="CBSE",
                grade_level="Class 3",
                subject="Maths",
                topic="Addition (carries)",
                difficulty="easy",
                num_questions=5,
            )

        assert "questions" in data
        assert len(data["questions"]) == 5
        assert elapsed_ms >= 0
        assert isinstance(warnings, list)
        mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_worksheet_async_wrapper(self):
        """Test the asyncio.to_thread pattern used by the v2 endpoint."""
        from app.services.worksheet_generator import generate_worksheet

        mock_client = MagicMock()
        raw_response = _make_raw_response(3, "Subtraction")
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=raw_response))]
        )

        with patch("app.services.curriculum.get_curriculum_context", return_value=None):
            data, elapsed_ms, warnings = await asyncio.to_thread(
                generate_worksheet,
                client=mock_client,
                board="CBSE",
                grade_level="Class 3",
                subject="Maths",
                topic="Subtraction",
                difficulty="medium",
                num_questions=3,
            )

        assert len(data["questions"]) == 3

    def test_generate_worksheet_retries_on_invalid_json(self):
        """If the first LLM call returns garbage, it should retry."""
        from app.services.worksheet_generator import generate_worksheet

        valid = _make_raw_response(5, "Division basics")
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            content = "NOT JSON" if call_count == 1 else valid
            return MagicMock(choices=[MagicMock(message=MagicMock(content=content))])

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = side_effect

        with patch("app.services.curriculum.get_curriculum_context", return_value=None):
            data, elapsed_ms, warnings = generate_worksheet(
                client=mock_client,
                board="CBSE",
                grade_level="Class 3",
                subject="Maths",
                topic="Division basics",
                difficulty="easy",
                num_questions=5,
            )

        assert "questions" in data
        assert call_count == 2  # retried once
