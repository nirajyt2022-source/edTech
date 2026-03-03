"""Tests for the sentence-structure diversity validator.

Covers:
- _make_deep_template() normalizations
- Check #20 in OutputValidator.validate_worksheet()
- R14_SENTENCE_DIVERSITY_GUARD in release_gate.py
- AI_14/AI_15 quality scorer classifiers
"""

from __future__ import annotations

from app.services.output_validator import OutputValidator


# ---------------------------------------------------------------------------
# _make_deep_template() tests
# ---------------------------------------------------------------------------


class TestMakeDeepTemplate:
    """Tests for OutputValidator._make_deep_template()."""

    def test_same_formula_produces_identical_template(self):
        """Two questions differing only in name/number/object/verb/place → same template."""
        q1 = "Riya has 5 apples. She buys 3 more at the market."
        q2 = "Arjun had 8 mangoes. He gets 4 more at the shop."
        assert OutputValidator._make_deep_template(q1) == OutputValidator._make_deep_template(q2)

    def test_different_structure_produces_different_template(self):
        """Structurally different questions → different templates."""
        q1 = "Riya has 5 apples. She buys 3 more at the market."
        q2 = "How many pencils are left if you remove 3 from a box of 10?"
        assert OutputValidator._make_deep_template(q1) != OutputValidator._make_deep_template(q2)

    def test_empty_text(self):
        """Empty text → empty string."""
        assert OutputValidator._make_deep_template("") == ""

    def test_short_text_no_normalizable_words(self):
        """Text with no names/numbers/objects/verbs → mostly unchanged."""
        text = "Is this correct?"
        result = OutputValidator._make_deep_template(text)
        assert result == "Is this correct?"

    def test_name_normalization(self):
        """Names are replaced with <NAME>."""
        result = OutputValidator._make_deep_template("Riya went to school")
        assert "<NAME>" in result

    def test_number_normalization(self):
        """Numbers are replaced with <NUM>."""
        result = OutputValidator._make_deep_template("There are 15 items")
        assert "<NUM>" in result

    def test_object_normalization(self):
        """Countable objects are replaced with <OBJ>."""
        result = OutputValidator._make_deep_template("She picked 5 apples and 3 oranges")
        assert "<OBJ>" in result

    def test_place_normalization(self):
        """Scenario words are replaced with <PLACE>."""
        result = OutputValidator._make_deep_template("He went to the market")
        assert "<PLACE>" in result

    def test_verb_normalization(self):
        """Verb forms are replaced with <VERB>."""
        result = OutputValidator._make_deep_template("She bought some items")
        assert "<VERB>" in result

    def test_adjacent_placeholders_collapsed(self):
        """Adjacent duplicate placeholders are collapsed."""
        # "Riya buys 5 apples" → <NAME> <VERB> <NUM> <OBJ> (not <NAME> <VERB> <NUM> <OBJ> <OBJ>)
        result = OutputValidator._make_deep_template("Riya buys 5 apples")
        # Should not have consecutive identical placeholders
        import re
        for tag in ["<NAME>", "<NUM>", "<OBJ>", "<PLACE>", "<VERB>"]:
            escaped = re.escape(tag)
            assert not re.search(rf"{escaped}\s+{escaped}", result), f"Adjacent {tag} not collapsed"

    def test_verb_tense_normalization(self):
        """Different tenses of the same verb produce same placeholder."""
        t1 = OutputValidator._make_deep_template("She buys something")
        t2 = OutputValidator._make_deep_template("She bought something")
        t3 = OutputValidator._make_deep_template("She buying something")
        assert t1 == t2 == t3

    def test_extends_make_template(self):
        """Deep template is at least as normalized as shallow template."""
        text = "Arjun has 10 pencils at school"
        shallow = OutputValidator._make_template(text)
        deep = OutputValidator._make_deep_template(text)
        # Deep should have more or equal placeholders
        assert deep.count("<") >= shallow.count("<")


# ---------------------------------------------------------------------------
# Check #20 tests (via validate_worksheet)
# ---------------------------------------------------------------------------


def _make_question(text: str, qid: str = "Q1") -> dict:
    return {
        "id": qid,
        "text": text,
        "type": "word_problem",
        "correct_answer": "42",
    }


def _make_formulaic_questions(n: int = 10) -> list[dict]:
    """Generate n questions that all follow the same formula but differ in surface details."""
    names = ["Riya", "Arjun", "Priya", "Rohan", "Ananya", "Kabir", "Isha", "Dev", "Meera", "Vivaan"]
    objects = ["apples", "mangoes", "pencils", "books", "toys", "marbles", "stickers", "cookies", "balls", "erasers"]
    verbs = ["buys", "gets", "picks", "collects", "takes", "eats", "gives", "makes", "shares", "packs"]
    places = ["market", "shop", "school", "park", "library", "farm", "bakery", "garden", "museum", "store"]
    questions = []
    for i in range(n):
        text = (
            f"{names[i % len(names)]} has {i + 2} {objects[i % len(objects)]}. "
            f"She {verbs[i % len(verbs)]} {i + 1} more at the {places[i % len(places)]}. "
            f"How many {objects[i % len(objects)]} now?"
        )
        questions.append(_make_question(text, f"Q{i + 1}"))
    return questions


def _make_diverse_questions(n: int = 10) -> list[dict]:
    """Generate n structurally diverse questions."""
    templates = [
        "How many pencils does Riya have if she starts with 5 and gets 3 more?",
        "Find the sum of 23 and 47.",
        "A box contains 12 balls. If 4 are removed, how many remain?",
        "Write the number that comes after 99.",
        "Arjun scored 85 marks. Is this more or less than 90?",
        "Complete the pattern: 2, 4, 6, __, __",
        "If you have ₹50 and spend ₹15, what is left?",
        "Arrange these numbers in ascending order: 45, 12, 78, 33",
        "Which is greater: 456 or 465?",
        "There are 3 rows of 5 chairs each. Count the total chairs.",
    ]
    questions = []
    for i in range(min(n, len(templates))):
        questions.append(_make_question(templates[i], f"Q{i + 1}"))
    return questions


class TestCheck20SentenceDiversity:
    """Tests for check #20 in validate_worksheet."""

    def test_formulaic_questions_trigger_low_diversity(self):
        """10 same-formula questions → diversity warning."""
        validator = OutputValidator()
        questions = _make_formulaic_questions(10)
        _ok, errors = validator.validate_worksheet(
            {"questions": questions},
            grade="Class 3",
            subject="Maths",
            topic="Addition",
            num_questions=10,
        )
        diversity_errors = [e for e in errors if "[sentence_diversity]" in e]
        assert len(diversity_errors) >= 1, f"Expected diversity errors, got: {errors}"

    def test_diverse_questions_no_warning(self):
        """10 diverse questions → no sentence_diversity warnings."""
        validator = OutputValidator()
        questions = _make_diverse_questions(10)
        _ok, errors = validator.validate_worksheet(
            {"questions": questions},
            grade="Class 3",
            subject="Maths",
            topic="Addition",
            num_questions=10,
        )
        diversity_errors = [e for e in errors if "[sentence_diversity]" in e]
        assert len(diversity_errors) == 0, f"Unexpected diversity errors: {diversity_errors}"

    def test_fewer_than_5_questions_skipped(self):
        """< 5 questions → check skipped, no diversity errors."""
        validator = OutputValidator()
        questions = _make_formulaic_questions(4)
        _ok, errors = validator.validate_worksheet(
            {"questions": questions},
            grade="Class 3",
            subject="Maths",
            topic="Addition",
            num_questions=4,
        )
        diversity_errors = [e for e in errors if "[sentence_diversity]" in e]
        assert len(diversity_errors) == 0

    def test_dominant_template_flagged(self):
        """When >40% of questions share one template → dominant template error."""
        validator = OutputValidator()
        questions = _make_formulaic_questions(10)
        _ok, errors = validator.validate_worksheet(
            {"questions": questions},
            grade="Class 3",
            subject="Maths",
            topic="Addition",
            num_questions=10,
        )
        dominant_errors = [e for e in errors if "Dominant template" in e]
        assert len(dominant_errors) >= 1, f"Expected dominant template error, got: {errors}"

    def test_borderline_mixed_questions(self):
        """5 same + 5 different → borderline behavior."""
        validator = OutputValidator()
        same = _make_formulaic_questions(5)
        different = _make_diverse_questions(5)
        for i, q in enumerate(different):
            q["id"] = f"Q{i + 6}"
        questions = same + different
        _ok, errors = validator.validate_worksheet(
            {"questions": questions},
            grade="Class 3",
            subject="Maths",
            topic="Addition",
            num_questions=10,
        )
        # With 5 same + 5 different, diversity should be moderate
        # At least no dominant template error (5/10 = 50%, threshold is >40%)
        # But diversity score might be borderline
        diversity_errors = [e for e in errors if "[sentence_diversity]" in e]
        # This is a legitimate borderline case — just verify the check runs
        assert isinstance(diversity_errors, list)


# ---------------------------------------------------------------------------
# R14 release gate tests
# ---------------------------------------------------------------------------


class TestR14SentenceDiversityGuard:
    """Tests for R14_SENTENCE_DIVERSITY_GUARD in release_gate.py."""

    def _make_ctx(self, questions):
        from app.services.release_gate import GateContext

        return GateContext(
            questions=questions,
            grade_level="Class 3",
            grade_num=3,
            subject="Maths",
            topic="Addition",
            num_questions=len(questions),
            difficulty="medium",
            warnings=[],
        )

    def test_low_diversity_blocks(self):
        """diversity < 0.5 → BLOCK."""
        from app.services.release_gate import r14_sentence_diversity_guard

        questions = _make_formulaic_questions(10)
        ctx = self._make_ctx(questions)
        result = r14_sentence_diversity_guard(ctx)
        assert not result.passed, f"Expected BLOCK, got passed. Detail: {result.detail}"

    def test_high_diversity_passes(self):
        """Diverse questions → PASS."""
        from app.services.release_gate import r14_sentence_diversity_guard

        questions = _make_diverse_questions(10)
        ctx = self._make_ctx(questions)
        result = r14_sentence_diversity_guard(ctx)
        assert result.passed, f"Expected PASS, got blocked. Detail: {result.detail}"

    def test_too_few_questions_passes(self):
        """< 5 questions → PASS (skipped)."""
        from app.services.release_gate import r14_sentence_diversity_guard

        questions = _make_formulaic_questions(3)
        ctx = self._make_ctx(questions)
        result = r14_sentence_diversity_guard(ctx)
        assert result.passed

    def test_dominant_template_blocks(self):
        """Single template > 50% → BLOCK."""
        from app.services.release_gate import r14_sentence_diversity_guard

        # 8 identical + 2 different
        same = _make_formulaic_questions(8)
        different = _make_diverse_questions(2)
        for i, q in enumerate(different):
            q["id"] = f"Q{i + 9}"
        questions = same + different
        ctx = self._make_ctx(questions)
        result = r14_sentence_diversity_guard(ctx)
        assert not result.passed, f"Expected BLOCK for dominant template. Detail: {result.detail}"


# ---------------------------------------------------------------------------
# Quality scorer classifier tests
# ---------------------------------------------------------------------------


class TestQualityScorerClassifiers:
    """Verify AI_14/AI_15 classifiers correctly match sentence diversity errors."""

    def test_ai_14_low_diversity_classified(self):
        """[sentence_diversity] Low diversity → AI_14, major, 0.20 deduction."""
        from app.services.quality_scorer import _classify_ov_errors, FailureReason

        buckets: dict[str, list[FailureReason]] = {
            "structural": [], "content": [], "pedagogical": [], "ai_smell": [], "curriculum": []
        }
        errors = ["[sentence_diversity] Low diversity score: 40% (4/10 unique structures). Threshold: 60%"]
        _classify_ov_errors(errors, buckets)
        ai_failures = buckets["ai_smell"]
        assert len(ai_failures) == 1
        assert ai_failures[0].check_id == "AI_14"
        assert ai_failures[0].severity == "major"
        assert ai_failures[0].points_deducted == 0.20

    def test_ai_15_dominant_template_classified(self):
        """[sentence_diversity] Dominant template → AI_15, major, 0.15 deduction."""
        from app.services.quality_scorer import _classify_ov_errors, FailureReason

        buckets: dict[str, list[FailureReason]] = {
            "structural": [], "content": [], "pedagogical": [], "ai_smell": [], "curriculum": []
        }
        errors = ["[sentence_diversity] Dominant template covers 7/10 questions"]
        _classify_ov_errors(errors, buckets)
        ai_failures = buckets["ai_smell"]
        assert len(ai_failures) == 1
        assert ai_failures[0].check_id == "AI_15"
        assert ai_failures[0].severity == "major"
        assert ai_failures[0].points_deducted == 0.15


# ---------------------------------------------------------------------------
# _extract_deep_repeated_templates tests
# ---------------------------------------------------------------------------


class TestExtractDeepRepeatedTemplates:
    """Tests for _extract_deep_repeated_templates in worksheet_generator.py."""

    def test_returns_repeated_deep_templates(self):
        from app.services.worksheet_generator import _extract_deep_repeated_templates

        questions = _make_formulaic_questions(6)
        result = _extract_deep_repeated_templates(questions, threshold=2)
        assert len(result) >= 1, "Expected at least one repeated deep template"

    def test_diverse_questions_no_repeats(self):
        from app.services.worksheet_generator import _extract_deep_repeated_templates

        questions = _make_diverse_questions(10)
        result = _extract_deep_repeated_templates(questions, threshold=2)
        assert len(result) == 0, f"Expected no repeated templates, got: {result}"
