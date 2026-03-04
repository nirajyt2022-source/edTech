"""Tests for quality_scorer.score_worksheet() — composite scoring engine."""

import time

from app.services.quality_scorer import (
    QualityScore,
    score_worksheet,
)


# ── Helper builders ──────────────────────────────────────────────────────────


def _q(
    qid: int,
    text: str = "",
    answer: str = "42",
    qtype: str = "short_answer",
    role: str = "application",
    skill_tag: str = "mth_c3_add",
    hint: str = "Think carefully",
    **extra,
) -> dict:
    return {
        "id": f"Q{qid}",
        "text": text or f"What is {qid} + {qid + 1}?",
        "correct_answer": answer,
        "type": qtype,
        "role": role,
        "skill_tag": skill_tag,
        "hint": hint,
        "format": qtype,
        **extra,
    }


def _diverse_questions(n: int = 10) -> list[dict]:
    """Build a diverse, high-quality set of questions."""
    roles = ["recognition", "representation", "application", "application", "application",
             "application", "error_detection", "thinking", "recognition", "representation"]
    types = ["mcq", "fill_blank", "short_answer", "word_problem", "short_answer",
             "fill_blank", "error_spot", "thinking", "mcq", "short_answer"]
    tags = ["mth_c3_add", "mth_c3_sub", "mth_c3_add", "mth_c3_word", "mth_c3_sub",
            "mth_c3_add", "mth_c3_error", "mth_c3_think", "mth_c3_sub", "mth_c3_add"]
    # Vary opening verbs and scenarios
    texts = [
        "Find the sum of 23 and 45.",
        "Solve: 67 - 34 = ___",
        "What is 12 + 19?",
        "Help Priya count her 15 apples and 8 oranges at the market.",
        "Calculate 56 - 28.",
        "Complete the pattern: 3, 6, 9, ___",
        "Can you spot the mistake in 45 + 17 = 53?",
        "If Arjun has 24 marbles and gives away 9, how many does he have?",
        "Which number comes after 99?",
        "Write the place value of 5 in 357.",
    ]
    answers = ["68", "33", "31", "23", "28", "12", "45 + 17 = 62", "15", "100", "50"]
    qs = []
    for i in range(min(n, 10)):
        q = _q(
            i + 1,
            text=texts[i],
            answer=answers[i],
            role=roles[i],
            qtype=types[i],
            skill_tag=tags[i],
        )
        if types[i] == "mcq" and i == 0:
            q["options"] = ["A) 68", "B) 58", "C) 78", "D) 88"]
            q["correct_answer"] = "A) 68"
        elif types[i] == "mcq" and i == 8:
            q["options"] = ["A) 100", "B) 98", "C) 101", "D) 110"]
            q["correct_answer"] = "A) 100"
        qs.append(q)
    return qs[:n]


def _worksheet(
    questions: list[dict] | None = None,
    grade: str = "Class 3",
    subject: str = "Maths",
    topic: str = "Addition (carries)",
    **extras,
) -> dict:
    return {
        "title": "Test Worksheet",
        "grade": grade,
        "subject": subject,
        "topic": topic,
        "difficulty": "Medium",
        "language": "English",
        "questions": questions or _diverse_questions(),
        "learning_objectives": extras.pop("learning_objectives", ["Understand addition with carrying"]),
        "chapter_ref": extras.pop("chapter_ref", "NCERT Ch 3"),
        "skill_focus": extras.pop("skill_focus", "Addition with carry"),
        **extras,
    }


# ── Basic scoring tests ──────────────────────────────────────────────────────


class TestScoreWorksheet:
    def test_returns_quality_score(self):
        result = score_worksheet(_worksheet())
        assert isinstance(result, QualityScore)
        assert 0 <= result.total_score <= 100

    def test_has_five_dimensions(self):
        result = score_worksheet(_worksheet())
        assert set(result.dimensions.keys()) == {
            "structural", "content", "pedagogical", "ai_smell", "curriculum",
        }

    def test_weights_sum_to_100(self):
        result = score_worksheet(_worksheet())
        total_weight = sum(d.weight for d in result.dimensions.values())
        assert total_weight == 100

    def test_perfect_worksheet_scores_high(self):
        result = score_worksheet(_worksheet(), export_threshold=70)
        assert result.total_score >= 70, f"Expected ≥70, got {result.total_score}"
        assert result.export_allowed is True

    def test_empty_worksheet_scores_zero(self):
        """Empty worksheet has STRUCT_01 (critical) → P0 kill switch → score 0."""
        ws = {
            "title": "Empty",
            "grade": "Class 3",
            "subject": "Maths",
            "topic": "Addition (carries)",
            "difficulty": "Medium",
            "language": "English",
            "questions": [],
            "learning_objectives": [],
            "chapter_ref": None,
            "skill_focus": "",
        }
        result = score_worksheet(ws, expected_count=10)
        assert result.question_count == 0
        assert result.total_score == 0.0
        assert result.export_allowed is False
        assert any(f.check_id == "STRUCT_01" for f in result.failures)

    def test_export_threshold_respected(self):
        result = score_worksheet(_worksheet(), export_threshold=99)
        assert result.export_allowed is False
        assert result.export_threshold == 99

    def test_low_threshold_allows_export(self):
        result = score_worksheet(_worksheet(), export_threshold=1)
        assert result.export_allowed is True

    def test_question_count_reported(self):
        result = score_worksheet(_worksheet())
        assert result.question_count == 10

    def test_grade_subject_reported(self):
        result = score_worksheet(_worksheet(grade="Class 4", subject="English"))
        assert result.grade == "Class 4"
        assert result.subject == "English"


# ── Structural dimension ─────────────────────────────────────────────────────


class TestStructuralDimension:
    def test_missing_answers_deducts(self):
        qs = _diverse_questions()
        qs[0]["correct_answer"] = ""
        qs[1]["correct_answer"] = ""
        result = score_worksheet(_worksheet(qs))
        struct = result.dimensions["structural"]
        assert struct.raw_score < 1.0
        assert any(f.check_id == "STRUCT_03" for f in struct.failures)

    def test_empty_text_deducts(self):
        qs = _diverse_questions()
        qs[0]["text"] = ""
        result = score_worksheet(_worksheet(qs))
        struct = result.dimensions["structural"]
        assert any(f.check_id == "STRUCT_02" for f in struct.failures)


# ── Content dimension ────────────────────────────────────────────────────────


class TestContentDimension:
    def test_fallback_questions_deduct(self):
        qs = _diverse_questions()
        qs[0]["is_fallback"] = True
        qs[1]["is_fallback"] = True
        result = score_worksheet(_worksheet(qs))
        content = result.dimensions["content"]
        assert content.raw_score < 1.0
        fallback_failures = [f for f in content.failures if f.check_id == "CONTENT_06"]
        assert len(fallback_failures) == 2

    def test_math_unverified_deducts(self):
        qs = _diverse_questions()
        qs[0]["_math_unverified"] = True
        result = score_worksheet(_worksheet(qs))
        content = result.dimensions["content"]
        assert any(f.check_id == "CONTENT_01" for f in content.failures)

    def test_needs_regen_flag_deducts(self):
        """CONTENT_03: _needs_regen flag should deduct 0.30."""
        qs = _diverse_questions()
        qs[0]["_needs_regen"] = True
        result = score_worksheet(_worksheet(qs))
        content = result.dimensions["content"]
        regen_failures = [f for f in content.failures if f.check_id == "CONTENT_03"]
        assert len(regen_failures) == 1
        assert regen_failures[0].points_deducted == 0.30

    def test_math_unverified_deducts_030(self):
        """CONTENT_01 recalibrated to 0.30."""
        qs = _diverse_questions()
        qs[0]["_math_unverified"] = True
        result = score_worksheet(_worksheet(qs))
        content = result.dimensions["content"]
        unverified = [f for f in content.failures if f.check_id == "CONTENT_01"]
        assert unverified[0].points_deducted == 0.30

    def test_fallback_deducts_030(self):
        """CONTENT_06 recalibrated to 0.30."""
        qs = _diverse_questions()
        qs[0]["is_fallback"] = True
        result = score_worksheet(_worksheet(qs))
        content = result.dimensions["content"]
        fb = [f for f in content.failures if f.check_id == "CONTENT_06"]
        assert fb[0].points_deducted == 0.30


# ── AI Smell dimension ───────────────────────────────────────────────────────


class TestAISmellDimension:
    def test_placeholder_content_deducts(self):
        qs = _diverse_questions()
        qs[0]["text"] = "[Generation failed for recognition question]"
        result = score_worksheet(_worksheet(qs))
        ai = result.dimensions["ai_smell"]
        assert any(f.check_id == "AI_08" for f in ai.failures)
        assert result.ai_smell_flags  # convenience accessor works

    def test_duplicate_questions_deduct(self):
        qs = [_q(i + 1, text="What is 5 + 3?") for i in range(10)]
        for i, q in enumerate(qs):
            q["role"] = ["recognition", "application"][i % 2]
        result = score_worksheet(_worksheet(qs))
        ai = result.dimensions["ai_smell"]
        assert ai.raw_score < 1.0


# ── Pedagogical dimension ────────────────────────────────────────────────────


class TestPedagogicalDimension:
    def test_single_role_deducts(self):
        qs = [_q(i + 1, role="application") for i in range(10)]
        result = score_worksheet(_worksheet(qs))
        ped = result.dimensions["pedagogical"]
        assert any(f.check_id == "PED_01" for f in ped.failures)

    def test_no_hints_deducts(self):
        qs = _diverse_questions()
        for q in qs:
            q["hint"] = ""
        result = score_worksheet(_worksheet(qs))
        ped = result.dimensions["pedagogical"]
        assert any(f.check_id == "PED_06" for f in ped.failures)

    def test_single_skill_tag_deducts(self):
        qs = [_q(i + 1, skill_tag="mth_c3_add") for i in range(10)]
        result = score_worksheet(_worksheet(qs))
        ped = result.dimensions["pedagogical"]
        assert any(f.check_id == "PED_04" for f in ped.failures)


# ── Curriculum dimension ─────────────────────────────────────────────────────


class TestCurriculumDimension:
    def test_missing_objectives_deducts(self):
        result = score_worksheet(_worksheet(learning_objectives=[]))
        cur = result.dimensions["curriculum"]
        assert any(f.check_id == "CUR_01" for f in cur.failures)

    def test_missing_chapter_ref_deducts(self):
        result = score_worksheet(_worksheet(chapter_ref=None))
        cur = result.dimensions["curriculum"]
        assert any(f.check_id == "CUR_02" for f in cur.failures)

    def test_missing_skill_focus_deducts(self):
        result = score_worksheet(_worksheet(skill_focus=""))
        cur = result.dimensions["curriculum"]
        assert any(f.check_id == "CUR_06" for f in cur.failures)

    def test_missing_chapter_ref_deducts_020(self):
        """CUR_02 recalibrated to 0.20."""
        result = score_worksheet(_worksheet(chapter_ref=None))
        cur = result.dimensions["curriculum"]
        ch = [f for f in cur.failures if f.check_id == "CUR_02"]
        assert ch[0].points_deducted == 0.20

    def test_missing_objectives_deducts_020(self):
        """CUR_01 recalibrated to 0.20."""
        result = score_worksheet(_worksheet(learning_objectives=[]))
        cur = result.dimensions["curriculum"]
        obj = [f for f in cur.failures if f.check_id == "CUR_01"]
        assert obj[0].points_deducted == 0.20

    def test_word_count_violation_class1(self):
        """CUR_05B: Class 1 limit is 15 words; >22 words should trigger."""
        long_text = "This is a very long question with way too many words for a young class one student to read"
        qs = _diverse_questions()
        qs[0]["text"] = long_text  # 19 words, >15*1.5=22.5? Let's count...
        # Actually need >22 words for Class 1
        qs[0]["text"] = " ".join(["word"] * 25)  # 25 words > 22.5
        result = score_worksheet(_worksheet(qs, grade="Class 1"))
        cur = result.dimensions["curriculum"]
        wc_failures = [f for f in cur.failures if f.check_id == "CUR_05B"]
        assert len(wc_failures) >= 1
        assert wc_failures[0].points_deducted == 0.10

    def test_word_count_ok_class3(self):
        """CUR_05B: Class 3 limit is 25; 30 words should be OK (< 37.5)."""
        qs = _diverse_questions()
        qs[0]["text"] = " ".join(["word"] * 30)  # 30 < 37.5
        result = score_worksheet(_worksheet(qs, grade="Class 3"))
        cur = result.dimensions["curriculum"]
        wc_failures = [f for f in cur.failures if f.check_id == "CUR_05B"]
        # 30 words should NOT trigger for Class 3 (limit 25, threshold 37.5)
        assert not any(f.question_ids == ["Q1"] for f in wc_failures)

    def test_word_count_violation_class3(self):
        """CUR_05B: Class 3 limit is 25; 40 words should trigger (> 37.5)."""
        qs = _diverse_questions()
        qs[0]["text"] = " ".join(["word"] * 40)  # 40 > 37.5
        result = score_worksheet(_worksheet(qs, grade="Class 3"))
        cur = result.dimensions["curriculum"]
        wc_failures = [f for f in cur.failures if f.check_id == "CUR_05B" and "Q1" in f.question_ids]
        assert len(wc_failures) == 1


# ── Recalibration integration ────────────────────────────────────────────────


class TestRecalibration:
    def test_flawed_worksheet_blocked_at_70(self):
        """A worksheet with wrong answer + no chapter + word count violations should score < 70."""
        long = " ".join(["word"] * 25)  # > 15*1.5=22.5 for Class 1
        qs = [_q(i + 1, text=long, role="application") for i in range(10)]
        qs[0]["_needs_regen"] = True
        ws = _worksheet(
            qs,
            grade="Class 1",
            chapter_ref=None,
            learning_objectives=[],
        )
        result = score_worksheet(ws, export_threshold=70)
        assert result.total_score < 70, f"Expected < 70, got {result.total_score}"
        assert result.export_allowed is False


# ── FailureReason structure ──────────────────────────────────────────────────


class TestFailureStructure:
    def test_failures_have_required_fields(self):
        qs = _diverse_questions()
        qs[0]["correct_answer"] = ""
        result = score_worksheet(_worksheet(qs))
        for f in result.failures:
            assert f.dimension, "dimension must be set"
            assert f.check_id, "check_id must be set"
            assert f.severity in ("critical", "major", "minor"), f"invalid severity: {f.severity}"
            assert f.message, "message must be set"
            assert isinstance(f.question_ids, list)
            assert f.points_deducted >= 0


# ── Performance ──────────────────────────────────────────────────────────────


class TestPerformance:
    def test_20_question_worksheet_under_100ms(self):
        qs = _diverse_questions(10) + _diverse_questions(10)
        for i, q in enumerate(qs):
            q["id"] = f"Q{i + 1}"
            q["text"] = f"Question {i + 1}: What is {i * 3} + {i * 2}?"
        ws = _worksheet(qs)

        # Warm up (first call may be slower due to imports)
        score_worksheet(ws)

        start = time.monotonic()
        score_worksheet(ws)
        elapsed_ms = (time.monotonic() - start) * 1000
        assert elapsed_ms < 100, f"Scoring took {elapsed_ms:.0f}ms, must be < 100ms"
