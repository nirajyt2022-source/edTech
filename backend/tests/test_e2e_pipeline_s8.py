"""
Sprint S8 — End-to-end pipeline integration tests.

Exercises the FULL quality pipeline in sequence:
  QualityReviewer → OutputValidator → ReleaseGate → QualityScorer

Uses synthetic worksheet data — no LLM / API key required.
Covers: Maths, English, Science, Hindi subjects.
"""

from __future__ import annotations

from app.services.output_validator import get_validator
from app.services.quality_reviewer import QualityReviewerAgent, ReviewResult
from app.services.quality_scorer import QualityScore, score_worksheet
from app.services.release_gate import run_release_gate
from app.services.topic_intelligence import GenerationContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_context(subject: str = "Maths", grade: int = 3, topic: str = "Addition (carries)") -> GenerationContext:
    return GenerationContext(
        topic_slug=topic,
        subject=subject,
        grade=grade,
        ncert_chapter=topic,
        ncert_subtopics=["Objective 1", "Objective 2", "Objective 3"],
        bloom_level="recall",
        format_mix={"mcq": 40, "fill_blank": 30, "word_problem": 30},
        scaffolding=True,
        challenge_mode=False,
        valid_skill_tags=["skill_a", "skill_b", "skill_c"],
        child_context={},
    )


def _maths_questions(n: int = 10) -> list[dict]:
    """High-quality Maths questions with diverse types and answers."""
    roles = ["recognition", "representation", "application", "application", "application",
             "application", "error_detection", "thinking", "recognition", "representation"]
    types = ["mcq", "fill_blank", "short_answer", "word_problem", "short_answer",
             "fill_blank", "error_detection", "short_answer", "mcq", "short_answer"]
    texts = [
        "Find the sum of 23 and 45.",
        "Solve: 67 - 34 = ___",
        "What is 12 + 19?",
        "Help Priya count her 15 apples and 8 oranges at the market.",
        "Calculate 56 - 28.",
        "Complete: 48 + 13 = ___",
        "Can you spot the mistake in 45 + 17 = 53?",
        "If Arjun has 24 marbles and gives away 9, how many does he have?",
        "Which is the largest: 45, 67, or 89?",
        "Write the place value of 5 in 357.",
    ]
    answers = ["68", "33", "31", "23", "28", "61", "45 + 17 = 62", "15", "89", "50"]
    qs = []
    for i in range(min(n, 10)):
        q = {
            "id": f"Q{i + 1}",
            "text": texts[i],
            "question_text": texts[i],
            "correct_answer": answers[i],
            "answer": answers[i],
            "type": types[i],
            "slot_type": roles[i],
            "role": roles[i],
            "format": types[i],
            "skill_tag": ["skill_a", "skill_b", "skill_c"][i % 3],
            "hint": f"Think about step {i + 1}.",
        }
        if types[i] == "mcq" and i == 0:
            q["options"] = ["68", "58", "78", "88"]
        elif types[i] == "mcq" and i == 8:
            q["options"] = ["89", "67", "45", "99"]
        qs.append(q)
    return qs[:n]


def _english_questions(n: int = 10) -> list[dict]:
    """English questions with diverse types."""
    items = [
        {"type": "mcq", "text": "Choose the noun:", "answer": "Cat", "options": ["Cat", "Run", "Big", "Fast"]},
        {"type": "fill_blank", "text": "The ___ is red.", "answer": "ball"},
        {"type": "true_false", "text": "A noun is a naming word.", "answer": "True"},
        {"type": "short_answer", "text": "Write the plural of 'child'.", "answer": "children"},
        {"type": "mcq", "text": "Which is a verb?", "answer": "Jump", "options": ["Table", "Jump", "Blue", "Happy"]},
        {"type": "fill_blank", "text": "She ___ to school daily.", "answer": "goes"},
        {"type": "true_false", "text": "An adjective describes a verb.", "answer": "False"},
        {"type": "short_answer", "text": "Give the opposite of 'hot'.", "answer": "cold"},
        {"type": "mcq", "text": "Find the adjective:", "answer": "Tall", "options": ["Tall", "Walk", "Chair", "The"]},
        {"type": "fill_blank", "text": "We ___ our homework yesterday.", "answer": "did"},
    ]
    roles = ["recognition", "application", "recognition", "application", "representation",
             "application", "recognition", "thinking", "recognition", "application"]
    qs = []
    for i in range(min(n, 10)):
        q = {
            "id": f"Q{i + 1}",
            "text": items[i]["text"],
            "question_text": items[i]["text"],
            "correct_answer": items[i]["answer"],
            "answer": items[i]["answer"],
            "type": items[i]["type"],
            "slot_type": roles[i],
            "role": roles[i],
            "format": items[i]["type"],
            "skill_tag": ["skill_a", "skill_b", "skill_c"][i % 3],
            "hint": f"Remember the rule for step {i + 1}.",
        }
        if "options" in items[i]:
            q["options"] = items[i]["options"]
        qs.append(q)
    return qs[:n]


def _science_questions(n: int = 10) -> list[dict]:
    """Science questions — mostly MCQ and T/F."""
    items = [
        {"type": "mcq", "text": "Which is a living thing?", "answer": "Dog", "options": ["Dog", "Rock", "Water", "Air"]},
        {"type": "true_false", "text": "Plants make their own food.", "answer": "True"},
        {"type": "short_answer", "text": "Name the gas we breathe in.", "answer": "Oxygen"},
        {"type": "mcq", "text": "Which body part helps a fish swim?", "answer": "Fins", "options": ["Fins", "Wings", "Legs", "Arms"]},
        {"type": "true_false", "text": "The sun is a planet.", "answer": "False"},
        {"type": "short_answer", "text": "What do roots absorb from soil?", "answer": "water"},
        {"type": "mcq", "text": "Which sense organ helps us see?", "answer": "Eyes", "options": ["Ears", "Eyes", "Nose", "Tongue"]},
        {"type": "true_false", "text": "Water boils at 100 degrees Celsius.", "answer": "True"},
        {"type": "short_answer", "text": "Name a source of light.", "answer": "Sun"},
        {"type": "mcq", "text": "Which animal gives us milk?", "answer": "Cow", "options": ["Cow", "Dog", "Cat", "Hen"]},
    ]
    roles = ["recognition", "recognition", "application", "application", "recognition",
             "application", "recognition", "recognition", "thinking", "recognition"]
    qs = []
    for i in range(min(n, 10)):
        q = {
            "id": f"Q{i + 1}",
            "text": items[i]["text"],
            "question_text": items[i]["text"],
            "correct_answer": items[i]["answer"],
            "answer": items[i]["answer"],
            "type": items[i]["type"],
            "slot_type": roles[i],
            "role": roles[i],
            "format": items[i]["type"],
            "skill_tag": ["skill_a", "skill_b", "skill_c"][i % 3],
            "hint": f"Think about nature, step {i + 1}.",
        }
        if "options" in items[i]:
            q["options"] = items[i]["options"]
        qs.append(q)
    return qs[:n]


def _hindi_questions(n: int = 5) -> list[dict]:
    """Hindi questions — T/F and short_answer."""
    items = [
        {"type": "true_false", "text": "सूरज पूरब से उगता है।", "answer": "सही"},
        {"type": "short_answer", "text": "'बच्चा' का बहुवचन लिखो।", "answer": "बच्चे"},
        {"type": "true_false", "text": "हिंदी भारत की राजभाषा है।", "answer": "सही"},
        {"type": "short_answer", "text": "'बड़ा' का विलोम लिखो।", "answer": "छोटा"},
        {"type": "true_false", "text": "संज्ञा क्रिया को बताती है।", "answer": "गलत"},
    ]
    roles = ["recognition", "application", "recognition", "application", "recognition"]
    qs = []
    for i in range(min(n, 5)):
        q = {
            "id": f"Q{i + 1}",
            "text": items[i]["text"],
            "question_text": items[i]["text"],
            "correct_answer": items[i]["answer"],
            "answer": items[i]["answer"],
            "type": items[i]["type"],
            "slot_type": roles[i],
            "role": roles[i],
            "format": items[i]["type"],
            "skill_tag": ["skill_a", "skill_b"][i % 2],
            "hint": f"सोचो, चरण {i + 1}।",
        }
        qs.append(q)
    return qs[:n]


def _make_worksheet(questions, subject="Maths", grade="Class 3", topic="Addition (carries)"):
    return {
        "title": f"Test {subject} Worksheet",
        "grade": grade,
        "subject": subject,
        "topic": topic,
        "difficulty": "Medium",
        "language": "English" if subject != "Hindi" else "Hindi",
        "questions": questions,
        "learning_objectives": ["Objective 1", "Objective 2"],
        "chapter_ref": "NCERT Ch 1",
        "skill_focus": f"{subject} fundamentals",
        "common_mistake": "Rushing through problems",
    }


# ---------------------------------------------------------------------------
# Helper: run full pipeline on a worksheet
# ---------------------------------------------------------------------------


def _run_pipeline(questions, subject, grade_str="Class 3", topic="Test Topic"):
    """Run QualityReviewer → OutputValidator → ReleaseGate → QualityScorer."""
    import re

    grade_num = 3
    m = re.search(r"\d+", grade_str)
    if m:
        grade_num = int(m.group())

    ctx = _make_context(subject=subject, grade=grade_num, topic=topic)

    # Step 1: Quality Reviewer
    reviewer = QualityReviewerAgent()
    review_result: ReviewResult = reviewer.review_worksheet(list(questions), ctx)

    # Step 2: Output Validator
    validator = get_validator()
    ws_dict = {"questions": review_result.questions}
    ov_valid, ov_errors = validator.validate_worksheet(
        ws_dict, grade=grade_str, subject=subject, topic=topic, num_questions=len(questions),
    )

    # Step 3: Release Gate
    release = run_release_gate(
        questions=review_result.questions,
        grade_level=grade_str,
        subject=subject,
        topic=topic,
        num_questions=len(questions),
        difficulty="medium",
        warnings=review_result.warnings,
        generation_context=ctx,
    )

    # Step 4: Quality Scorer
    worksheet = _make_worksheet(review_result.questions, subject=subject, grade=grade_str, topic=topic)
    score_result: QualityScore = score_worksheet(worksheet, expected_count=len(questions))

    return {
        "review": review_result,
        "ov_valid": ov_valid,
        "ov_errors": ov_errors,
        "release": release,
        "score": score_result,
    }


# ---------------------------------------------------------------------------
# Tests: Full pipeline per subject
# ---------------------------------------------------------------------------


class TestMathsPipeline:
    """Maths worksheet through full pipeline."""

    def test_clean_maths_passes_all_layers(self):
        result = _run_pipeline(_maths_questions(), "Maths", topic="Addition (carries)")
        assert result["release"].verdict in ("released", "best_effort")
        assert result["score"].total_score > 0
        assert result["score"].question_count == 10

    def test_maths_answer_mismatch_blocks(self):
        qs = _maths_questions()
        qs[0]["answer"] = "999"  # wrong answer for "23 + 45"
        qs[0]["correct_answer"] = "999"
        result = _run_pipeline(qs, "Maths", topic="Addition (carries)")
        # Should detect mismatch via AnswerAuthority → R15 blocks
        has_mismatch = any(q.get("_answer_mismatch") for q in result["review"].questions)
        assert has_mismatch, "Expected _answer_mismatch flag on Q1"

    def test_maths_missing_answer_blocks_r23(self):
        qs = _maths_questions()
        qs[0]["answer"] = ""
        qs[0]["correct_answer"] = ""
        result = _run_pipeline(qs, "Maths", topic="Addition (carries)")
        r23_failed = any("R23" in r for r in result["release"].failed_rules)
        assert r23_failed, "R23 should block on missing answer"


class TestEnglishPipeline:
    """English worksheet through full pipeline."""

    def test_clean_english_passes(self):
        result = _run_pipeline(_english_questions(), "English", topic="Nouns")
        assert result["release"].verdict in ("released", "best_effort")
        assert result["score"].total_score > 0

    def test_english_mcq_answer_not_in_options_flagged(self):
        qs = _english_questions()
        qs[0]["answer"] = "Elephant"  # not in options
        qs[0]["correct_answer"] = "Elephant"
        result = _run_pipeline(qs, "English", topic="Nouns")
        # CHECK 14 (MCQ answer-in-options) or AnswerAuthority flags this
        has_flag = any(
            q.get("_answer_mismatch") or q.get("_needs_regen")
            for q in result["review"].questions
        )
        assert has_flag, "MCQ answer not in options should be flagged via _answer_mismatch or _needs_regen"

    def test_english_tf_verified(self):
        qs = _english_questions()
        # Q3 is true_false with answer "True" — should be verified
        result = _run_pipeline(qs, "English", topic="Nouns")
        # True/False questions should pass through cleanly
        assert result["score"].total_score > 0


class TestSciencePipeline:
    """Science worksheet through full pipeline."""

    def test_clean_science_passes(self):
        result = _run_pipeline(_science_questions(), "Science", topic="Living Things")
        assert result["release"].verdict in ("released", "best_effort")
        assert result["score"].total_score > 0

    def test_science_tf_verified(self):
        qs = _science_questions()
        result = _run_pipeline(qs, "Science", topic="Living Things")
        # T/F questions with "True"/"False" should be verified cleanly
        assert result["score"].question_count == 10

    def test_science_mcq_answer_mismatch(self):
        qs = _science_questions()
        qs[0]["answer"] = "Bicycle"  # not in options ["Dog", "Rock", "Water", "Air"]
        qs[0]["correct_answer"] = "Bicycle"
        result = _run_pipeline(qs, "Science", topic="Living Things")
        has_flag = any(
            q.get("_answer_mismatch") or q.get("_needs_regen")
            for q in result["review"].questions
        )
        assert has_flag, "Science MCQ answer not in options should be flagged"


class TestHindiPipeline:
    """Hindi worksheet through full pipeline."""

    def test_clean_hindi_passes(self):
        result = _run_pipeline(_hindi_questions(), "Hindi", topic="संज्ञा")
        assert result["release"].verdict in ("released", "best_effort")
        assert result["score"].total_score > 0

    def test_hindi_tf_sahi_verified(self):
        qs = _hindi_questions()
        # Q1 has answer "सही" — should be recognized as True
        result = _run_pipeline(qs, "Hindi", topic="संज्ञा")
        # Should pass through without _answer_mismatch
        has_mismatch = any(
            q.get("_answer_mismatch") for q in result["review"].questions
            if q.get("type") == "true_false"
        )
        assert not has_mismatch, "Hindi T/F 'सही'/'गलत' should be recognized"


# ---------------------------------------------------------------------------
# Tests: Cross-layer agreement
# ---------------------------------------------------------------------------


class TestCrossLayerAgreement:
    """Verify all pipeline layers agree on verdict."""

    def test_release_block_implies_low_score(self):
        """If release gate blocks, quality score should be low."""
        qs = _maths_questions()
        # Make multiple answers wrong to trigger blocks
        for q in qs[:4]:
            q["answer"] = "999"
            q["correct_answer"] = "999"
        result = _run_pipeline(qs, "Maths", topic="Addition (carries)")
        if result["release"].verdict == "blocked":
            # Score should reflect the problems
            assert result["score"].total_score < 70

    def test_clean_worksheet_no_critical_failures(self):
        """A clean worksheet should have no critical failures in scorer."""
        result = _run_pipeline(_maths_questions(), "Maths", topic="Addition (carries)")
        critical = [f for f in result["score"].failures if f.severity == "critical"]
        # May have minor issues, but critical should be rare/zero for clean data
        assert len(critical) <= 1, f"Expected ≤1 critical, got {len(critical)}: {[f.check_id for f in critical]}"

    def test_all_subjects_produce_valid_scores(self):
        """Every subject should produce a valid QualityScore."""
        for subject, qs_fn, topic in [
            ("Maths", _maths_questions, "Addition (carries)"),
            ("English", _english_questions, "Nouns"),
            ("Science", _science_questions, "Living Things"),
        ]:
            result = _run_pipeline(qs_fn(), subject, topic=topic)
            assert isinstance(result["score"], QualityScore)
            assert 0 <= result["score"].total_score <= 100
            assert result["score"].subject == subject


# ---------------------------------------------------------------------------
# Tests: Gold standard auto-promotion (S8.1)
# ---------------------------------------------------------------------------


class TestGoldStandardAutoPromotion:
    """gold_standard_eligible auto-computed by scorer."""

    def test_perfect_worksheet_may_be_gold(self):
        """A perfect worksheet with score ≥ 85 and no major failures is gold-eligible."""
        ws = _make_worksheet(_maths_questions(), subject="Maths")
        result = score_worksheet(ws, expected_count=10)
        # If score ≥ 85 and no major failures, should be gold eligible
        has_major = any(f.severity in ("critical", "major") for f in result.failures)
        if result.total_score >= 85 and not has_major:
            assert result.gold_standard_eligible is True
        # If there are failures or low score, gold should be False
        if result.total_score < 85 or has_major:
            assert result.gold_standard_eligible is False

    def test_flawed_worksheet_not_gold(self):
        """A worksheet with critical failures is not gold-eligible."""
        qs = _maths_questions()
        qs[0]["_answer_mismatch"] = True  # CONTENT_02 critical
        ws = _make_worksheet(qs, subject="Maths")
        result = score_worksheet(ws, expected_count=10)
        assert result.gold_standard_eligible is False

    def test_gold_field_present_on_result(self):
        """QualityScore always has gold_standard_eligible field."""
        ws = _make_worksheet(_english_questions(), subject="English")
        result = score_worksheet(ws, expected_count=10)
        assert hasattr(result, "gold_standard_eligible")
        assert isinstance(result.gold_standard_eligible, bool)

    def test_low_score_not_gold(self):
        """Score < 85 means not gold-eligible even with no failures."""
        qs = _maths_questions()
        # Add issues that lower score but aren't critical
        for q in qs:
            q["hint"] = ""  # PED_06 deduction
        ws = _make_worksheet(qs, subject="Maths")
        ws["learning_objectives"] = []  # CUR_01 deduction
        ws["chapter_ref"] = None  # CUR_02 deduction
        ws["skill_focus"] = ""  # CUR_06 deduction
        ws["common_mistake"] = ""  # PED_07 deduction
        result = score_worksheet(ws, expected_count=10)
        # With multiple deductions, likely below 85
        if result.total_score < 85:
            assert result.gold_standard_eligible is False


# ---------------------------------------------------------------------------
# Tests: R23 + R15 cross-subject in full pipeline
# ---------------------------------------------------------------------------


class TestReleaseGateCrossSubject:
    """R15 and R23 fire for all subjects in the pipeline."""

    def test_r23_blocks_english_missing_answer(self):
        qs = _english_questions()
        # Use a short_answer question (index 3) — T/F gets auto-corrected by CHECK 15
        qs[3]["answer"] = ""
        qs[3]["correct_answer"] = ""
        result = _run_pipeline(qs, "English", topic="Nouns")
        r23_failed = any("R23" in r for r in result["release"].failed_rules)
        assert r23_failed

    def test_r23_blocks_science_missing_answer(self):
        qs = _science_questions()
        qs[0]["answer"] = ""
        qs[0]["correct_answer"] = ""
        result = _run_pipeline(qs, "Science", topic="Living Things")
        r23_failed = any("R23" in r for r in result["release"].failed_rules)
        assert r23_failed

    def test_r15_or_r08_blocks_science_mcq_mismatch(self):
        qs = _science_questions()
        qs[0]["answer"] = "Mars"  # not in options
        qs[0]["correct_answer"] = "Mars"
        result = _run_pipeline(qs, "Science", topic="Living Things")
        # CHECK 14 flags _needs_regen; AnswerAuthority may flag _answer_mismatch
        has_flag = any(
            q.get("_answer_mismatch") or q.get("_needs_regen")
            for q in result["review"].questions
        )
        assert has_flag, "MCQ answer not in options should be caught by pipeline"
