from app.services.release_gate import run_release_gate


def _q(idx: int = 1) -> dict:
    return {
        "id": f"q{idx}",
        "type": "short_answer",
        "text": "What is 2 + 2?",
        "question_text": "What is 2 + 2?",
        "correct_answer": "4",
        "answer": "4",
        "format": "short_answer",
        "role": "application",
        "skill_tag": "add_single",
    }


def test_strict_p1_blocks_degrade_rule():
    verdict = run_release_gate(
        questions=[_q()],
        grade_level="Class 3",
        subject="Maths",
        topic="Addition (carries)",
        num_questions=1,
        difficulty="medium",
        warnings=[],
        curriculum_available=False,  # triggers R04 (P1)
        worksheet_meta={"_quality_score": 90},
        strict_p1=True,
    )
    assert verdict.verdict == "blocked"
    assert any("R04_CURRICULUM_GROUNDED" in r for r in verdict.block_reasons)


def test_non_strict_p1_allows_best_effort_for_degrade_rule():
    verdict = run_release_gate(
        questions=[_q()],
        grade_level="Class 3",
        subject="Maths",
        topic="Addition (carries)",
        num_questions=1,
        difficulty="medium",
        warnings=[],
        curriculum_available=False,  # triggers R04 (P1)
        worksheet_meta={"_quality_score": 90},
        strict_p1=False,
    )
    assert verdict.verdict in ("best_effort", "released")
