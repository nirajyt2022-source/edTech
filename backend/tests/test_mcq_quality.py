"""Tests for MCQ quality ban — S1.2."""

def _q(qid="Q1", text="Choose the correct answer.", qtype="mcq", options=None, answer="A", **kw):
    return {
        "id": qid,
        "text": text,
        "question_text": text,
        "correct_answer": answer,
        "type": qtype,
        "format": qtype,
        "options": options or ["A", "B", "C", "D"],
        "role": "recognition",
        "skill_tag": "mth_c3_add",
        **kw,
    }


class TestOutputValidatorMCQQuality:
    def test_banned_all_of_above(self):
        from app.services.output_validator import get_validator

        v = get_validator()
        questions = [
            _q(options=["5", "10", "15", "All of the above"]),
        ]
        _valid, errors = v.validate_worksheet(
            {"questions": questions}, grade="Class 3", subject="Maths", topic="Addition", num_questions=1
        )
        mcq_errors = [e for e in errors if "[mcq_quality]" in e]
        assert len(mcq_errors) >= 1
        assert "Banned option" in mcq_errors[0]

    def test_banned_none_of_above(self):
        from app.services.output_validator import get_validator

        v = get_validator()
        questions = [
            _q(options=["5", "10", "15", "None of the above"]),
        ]
        _valid, errors = v.validate_worksheet(
            {"questions": questions}, grade="Class 3", subject="Maths", topic="Addition", num_questions=1
        )
        mcq_errors = [e for e in errors if "[mcq_quality]" in e]
        assert len(mcq_errors) >= 1

    def test_normal_options_pass(self):
        from app.services.output_validator import get_validator

        v = get_validator()
        questions = [
            _q(options=["5", "10", "15", "20"], answer="15"),
        ]
        _valid, errors = v.validate_worksheet(
            {"questions": questions}, grade="Class 3", subject="Maths", topic="Addition", num_questions=1
        )
        mcq_errors = [e for e in errors if "[mcq_quality]" in e]
        assert len(mcq_errors) == 0

    def test_both_a_and_b_banned(self):
        from app.services.output_validator import get_validator

        v = get_validator()
        questions = [
            _q(options=["5", "10", "Both A and B", "20"]),
        ]
        _valid, errors = v.validate_worksheet(
            {"questions": questions}, grade="Class 3", subject="Maths", topic="Addition", num_questions=1
        )
        mcq_errors = [e for e in errors if "[mcq_quality]" in e]
        assert len(mcq_errors) >= 1


class TestReleaseGateR16:
    def test_r16_blocks_class_2(self):
        from app.services.release_gate import run_release_gate

        questions = [
            _q(options=["5", "10", "15", "All of the above"]),
        ]
        verdict = run_release_gate(
            questions=questions,
            grade_level="Class 2",
            subject="Maths",
            topic="Addition",
            num_questions=1,
            difficulty="easy",
            warnings=[],
        )
        assert "R16_MCQ_QUALITY_GUARD" in verdict.failed_rules

    def test_r16_degrades_class_4(self):
        from app.services.release_gate import run_release_gate

        questions = [
            _q(options=["5", "10", "15", "All of the above"]),
        ]
        verdict = run_release_gate(
            questions=questions,
            grade_level="Class 4",
            subject="Maths",
            topic="Addition",
            num_questions=1,
            difficulty="medium",
            warnings=[],
        )
        assert "R16_MCQ_QUALITY_GUARD" in verdict.failed_rules
        # Should degrade, not block (R16 result is DEGRADE for class 4)
        r16_result = [r for r in verdict.rule_results if r.rule_name == "R16_MCQ_QUALITY_GUARD"][0]
        assert r16_result.enforcement.value == "degrade"

    def test_r16_passes_normal_options(self):
        from app.services.release_gate import run_release_gate

        questions = [
            _q(options=["5", "10", "15", "20"], answer="15"),
        ]
        verdict = run_release_gate(
            questions=questions,
            grade_level="Class 3",
            subject="Maths",
            topic="Addition",
            num_questions=1,
            difficulty="medium",
            warnings=[],
        )
        assert "R16_MCQ_QUALITY_GUARD" not in verdict.failed_rules


class TestQualityScorerAI16:
    def test_mcq_quality_classified(self):
        from app.services.quality_scorer import score_worksheet

        ws = {
            "grade": "Class 3",
            "subject": "Maths",
            "topic": "Addition",
            "learning_objectives": ["Add numbers"],
            "chapter_ref": "Ch1",
            "skill_focus": "addition",
            "questions": [
                _q(options=["5", "10", "15", "All of the above"]),
            ],
        }
        result = score_worksheet(ws, expected_count=1)
        ai_ids = [f.check_id for f in result.ai_smell_flags]
        assert "AI_16" in ai_ids
