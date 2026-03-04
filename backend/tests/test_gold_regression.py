"""
Gold Standard Regression Tests — parametrized over 15 fixture worksheets.

Pins expected quality outcomes across class/subject combinations.
Any change that shifts scores, verdicts, or error counts outside expected
ranges will cause a test failure, catching regressions early.
"""

import pytest

from app.services.quality_scorer import score_worksheet
from app.services.release_gate import run_release_gate

from tests.fixtures.gold_worksheets import GOLD_FIXTURES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_fixture(fixture_id: str) -> dict:
    """Build a worksheet from the fixture registry."""
    spec = GOLD_FIXTURES[fixture_id]
    return spec["builder"]()


def _run_gate(ws: dict) -> object:
    """Run the release gate on a worksheet dict."""
    grade = ws.get("grade", "Class 3")
    num_q = len(ws.get("questions", []))
    return run_release_gate(
        questions=ws.get("questions", []),
        grade_level=grade,
        subject=ws.get("subject", "Maths"),
        topic=ws.get("topic", ""),
        num_questions=num_q,
        difficulty=ws.get("difficulty", "Medium"),
        warnings=[],
        worksheet_meta=ws,
    )


def _run_ov(ws: dict) -> tuple[bool, list[str]]:
    """Run OutputValidator on a worksheet."""
    from app.services.output_validator import get_validator
    validator = get_validator()
    return validator.validate_worksheet(
        {"questions": ws.get("questions", [])},
        grade=ws.get("grade", "Class 3"),
        subject=ws.get("subject", ""),
        topic=ws.get("topic", ""),
        num_questions=len(ws.get("questions", [])),
    )


# ===========================================================================
# Parametrized regression tests
# ===========================================================================


@pytest.mark.parametrize("fixture_id", list(GOLD_FIXTURES.keys()))
class TestGoldRegression:
    """Run every gold fixture through the quality stack and assert expectations."""

    def test_quality_score(self, fixture_id: str):
        """Quality score in expected range."""
        spec = GOLD_FIXTURES[fixture_id]
        ws = _build_fixture(fixture_id)
        result = score_worksheet(ws)

        assert result.total_score >= spec["min_score"], (
            f"{fixture_id}: score {result.total_score} < min {spec['min_score']}. "
            f"Failures: {[f.message for f in result.failures[:5]]}"
        )
        assert result.total_score <= spec["max_score"], (
            f"{fixture_id}: score {result.total_score} > max {spec['max_score']}"
        )

    def test_release_verdict(self, fixture_id: str):
        """Release gate verdict matches expected."""
        spec = GOLD_FIXTURES[fixture_id]
        ws = _build_fixture(fixture_id)
        verdict = _run_gate(ws)

        expected = spec["expected_verdict"]
        if expected == "released":
            assert verdict.verdict in ("released",), (
                f"{fixture_id}: expected released, got {verdict.verdict}. "
                f"Block: {verdict.block_reasons[:3]}, Degrade: {verdict.degrade_reasons[:3]}"
            )
        elif expected == "best_effort":
            assert verdict.verdict in ("best_effort", "released"), (
                f"{fixture_id}: expected best_effort/released, got {verdict.verdict}. "
                f"Block: {verdict.block_reasons[:3]}"
            )
        elif expected == "blocked":
            assert verdict.verdict == "blocked", (
                f"{fixture_id}: expected blocked, got {verdict.verdict}"
            )

    def test_no_critical_failures(self, fixture_id: str):
        """Clean fixtures have zero critical failures."""
        spec = GOLD_FIXTURES[fixture_id]
        if spec["max_critical"] is None:
            pytest.skip("Fixture allows critical failures")

        ws = _build_fixture(fixture_id)
        result = score_worksheet(ws)
        criticals = [f for f in result.failures if f.severity == "critical"]

        assert len(criticals) <= spec["max_critical"], (
            f"{fixture_id}: {len(criticals)} critical failure(s), max allowed {spec['max_critical']}. "
            f"Issues: {[f.message for f in criticals[:5]]}"
        )

    def test_output_validator(self, fixture_id: str):
        """OV error count matches expectations — clean fixtures should have minimal errors."""
        spec = GOLD_FIXTURES[fixture_id]
        ws = _build_fixture(fixture_id)
        _is_valid, errors = _run_ov(ws)

        if spec["expected_verdict"] == "released":
            # Clean fixtures: OV should find few if any structural errors
            structural_errors = [e for e in errors if "empty question" in e or "missing correct_answer" in e]
            assert len(structural_errors) == 0, (
                f"{fixture_id}: clean fixture has structural OV errors: {structural_errors[:5]}"
            )
        elif spec["expected_verdict"] == "blocked":
            # Blocked fixtures: OV should find issues
            assert len(errors) > 0, (
                f"{fixture_id}: blocked fixture has no OV errors — fixture may be too clean"
            )
