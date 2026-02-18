"""
Phase 2 E2E smoke test — run from backend/ with:
    uv run python scripts/e2e_phase2_smoke.py

Tests (deterministic only, no LLM calls needed):
  1. All 4 agent modules import cleanly
  2. TopicIntelligenceAgent.build_context() returns a valid GenerationContext
  3. QualityReviewerAgent corrects a wrong arithmetic answer
  4. DifficultyCalibrator applies sorting and hints for scaffolding=True
  5. Meta cache: second call logs HIT (mocked — verifies cache key logic)
  6. prompt_builder produces non-empty output for a known topic
  7. Full agent chain A→B→C→D without LLM (wiring check)

All checks are deterministic and run offline.
"""
import sys, os, time, asyncio, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Silence info-level noise so we can see test output clearly
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
results = []

def check(name, cond, detail=""):
    status = PASS if cond else FAIL
    print(f"  {status}  {name}" + (f"  [{detail}]" if detail else ""))
    results.append((name, cond))

# ---------------------------------------------------------------------------
print("\n━━━ STEP 1: Import checks ━━━")
# ---------------------------------------------------------------------------
try:
    from app.services.topic_intelligence import TopicIntelligenceAgent, GenerationContext, get_topic_intelligence_agent
    check("topic_intelligence imports", True)
except Exception as e:
    check("topic_intelligence imports", False, str(e))

try:
    from app.services.prompt_builder import build_compressed_curriculum_context, build_question_prompt
    check("prompt_builder imports", True)
except Exception as e:
    check("prompt_builder imports", False, str(e))

try:
    from app.services.quality_reviewer import QualityReviewerAgent, get_quality_reviewer
    check("quality_reviewer imports", True)
except Exception as e:
    check("quality_reviewer imports", False, str(e))

try:
    from app.services.difficulty_calibrator import DifficultyCalibrator, get_difficulty_calibrator
    check("difficulty_calibrator imports", True)
except Exception as e:
    check("difficulty_calibrator imports", False, str(e))

# ---------------------------------------------------------------------------
print("\n━━━ STEP 2: TopicIntelligenceAgent.build_context() ━━━")
# ---------------------------------------------------------------------------
ctx = None
try:
    agent = get_topic_intelligence_agent()
    t0 = time.perf_counter()
    ctx = asyncio.run(agent.build_context(
        child_id=None,
        topic_slug="Addition (carries)",
        subject="Maths",
        grade=3,
    ))
    elapsed = time.perf_counter() - t0
    check("Returns GenerationContext", isinstance(ctx, GenerationContext))
    check("ncert_chapter non-empty", bool(ctx.ncert_chapter), ctx.ncert_chapter)
    check("valid_skill_tags non-empty", len(ctx.valid_skill_tags) > 0, str(ctx.valid_skill_tags[:3]))
    check("ncert_subtopics is list", isinstance(ctx.ncert_subtopics, list))
    check("bloom_level is 'recall'", ctx.bloom_level == "recall", ctx.bloom_level)
    check("scaffolding=True (default)", ctx.scaffolding is True)
    check("challenge_mode=False (default)", ctx.challenge_mode is False)
    check(f"build_context < 0.5s", elapsed < 0.5, f"{elapsed*1000:.1f}ms")
except Exception as e:
    check("build_context() completed", False, str(e))
    ctx = None

# ---------------------------------------------------------------------------
print("\n━━━ STEP 3: prompt_builder output ━━━")
# ---------------------------------------------------------------------------
if ctx:
    try:
        curriculum_block = build_compressed_curriculum_context(ctx)
        check("curriculum_block non-empty", bool(curriculum_block))
        check("contains TOPIC:", "TOPIC:" in curriculum_block)
        check("contains OBJECTIVES:", "OBJECTIVES:" in curriculum_block)
        check("contains SKILL_TAGS:", "SKILL_TAGS:" in curriculum_block)
        check("contains BLOOM:", "BLOOM:" in curriculum_block)

        slot = {"slot_type": "application"}
        q_prompt = build_question_prompt(slot, ctx)
        check("question_prompt non-empty", bool(q_prompt))
        check("contains NCERT CURRICULUM CONTEXT", "NCERT CURRICULUM CONTEXT" in q_prompt)
        check("contains SCOPE:", "SCOPE:" in q_prompt)
    except Exception as e:
        check("prompt_builder output", False, str(e))

# ---------------------------------------------------------------------------
print("\n━━━ STEP 4: QualityReviewerAgent ━━━")
# ---------------------------------------------------------------------------
if ctx:
    try:
        reviewer = get_quality_reviewer()

        # CHECK 1: arithmetic correction
        q_wrong = {
            "id": 1, "slot_type": "recognition",
            "question_text": "What is 8 + 5?",
            "answer": "14",   # wrong — should be 13
            "skill_tag": ctx.valid_skill_tags[0],
            "difficulty": "easy",
        }
        result = reviewer.review_worksheet([q_wrong], ctx)
        check("Wrong arithmetic auto-corrected", result.corrections != [], str(result.corrections))
        check("Corrected answer is '13'", result.questions[0]["answer"] == "13",
              f"got '{result.questions[0]['answer']}'")
        check("_answer_corrected flag set", result.questions[0].get("_answer_corrected") is True)

        # CHECK 2: correct answer untouched
        q_correct = {
            "id": 2, "slot_type": "recognition",
            "question_text": "What is 8 + 5?",
            "answer": "13",
            "skill_tag": ctx.valid_skill_tags[0],
            "difficulty": "easy",
        }
        result2 = reviewer.review_worksheet([q_correct], ctx)
        check("Correct answer untouched", result2.corrections == [])
        check("Answer still '13'", result2.questions[0]["answer"] == "13")

        # CHECK 3: invalid skill_tag replaced
        q_bad_tag = {
            "id": 3, "slot_type": "recognition",
            "question_text": "A question",
            "answer": "42",
            "skill_tag": "invalid_tag_xyz",
            "difficulty": "easy",
        }
        result3 = reviewer.review_worksheet([q_bad_tag], ctx)
        check("Invalid skill_tag replaced", result3.errors != [], str(result3.errors))
        check("Replaced with first valid tag",
              result3.questions[0]["skill_tag"] == ctx.valid_skill_tags[0],
              f"got '{result3.questions[0]['skill_tag']}'")

        # CHECK 4: error_detection skipped
        q_ed = {
            "id": 4, "slot_type": "error_detection",
            "question_text": "Spot the error: 5 + 9 = 15",
            "answer": "15",  # intentionally wrong
            "skill_tag": ctx.valid_skill_tags[0],
            "difficulty": "medium",
        }
        result4 = reviewer.review_worksheet([q_ed], ctx)
        check("error_detection answer NOT auto-corrected", result4.corrections == [])

    except Exception as e:
        check("QualityReviewerAgent", False, str(e))

# ---------------------------------------------------------------------------
print("\n━━━ STEP 5: DifficultyCalibrator ━━━")
# ---------------------------------------------------------------------------
if ctx:
    try:
        calibrator = get_difficulty_calibrator()

        # Test scaffolding sort + hints
        ctx_scaffold = GenerationContext(
            topic_slug="Addition (carries)", subject="Maths", grade=3,
            ncert_chapter="Addition (carries)", ncert_subtopics=["obj1"],
            bloom_level="recall",
            format_mix={"mcq": 40, "fill_blank": 30, "word_problem": 30},
            scaffolding=True, challenge_mode=False,
            valid_skill_tags=ctx.valid_skill_tags, child_context={},
        )
        qs = [
            {"id": 1, "format": "word_problem",
             "question_text": "word " * 20,
             "answer": "42", "skill_tag": ctx.valid_skill_tags[0], "difficulty": "medium"},
            {"id": 2, "format": "missing_number",
             "question_text": "short",
             "answer": "7",  "skill_tag": ctx.valid_skill_tags[0], "difficulty": "easy"},
        ]
        out = calibrator.calibrate(qs, ctx_scaffold)
        check("scaffolding: easy question sorted first", out[0]["id"] == 2,
              f"first id = {out[0]['id']}")
        check("scaffolding: hard question sorted last",  out[1]["id"] == 1,
              f"second id = {out[1]['id']}")
        check("scaffolding: Q1 has hint", bool(out[0].get("hint")), out[0].get("hint"))
        check("scaffolding: Q2 has hint", bool(out[1].get("hint")), out[1].get("hint"))
        check("no bonus when challenge_mode=False", len(out) == 2)

        # Test challenge bonus
        ctx_challenge = GenerationContext(
            topic_slug="Addition (carries)", subject="Maths", grade=3,
            ncert_chapter="Addition (carries)", ncert_subtopics=[],
            bloom_level="reasoning",
            format_mix={},
            scaffolding=False, challenge_mode=True,
            valid_skill_tags=ctx.valid_skill_tags, child_context={},
        )
        qs2 = [{"id": 1, "format": "word_problem", "question_text": "A question",
                "answer": "5", "skill_tag": ctx.valid_skill_tags[0], "difficulty": "hard"}]
        out2 = calibrator.calibrate(qs2, ctx_challenge)
        check("challenge_mode: bonus appended", len(out2) == 2, f"len={len(out2)}")
        check("bonus has _is_bonus=True", out2[-1].get("_is_bonus") is True)
        check("bonus format is word_problem", out2[-1].get("format") == "word_problem")

        # Test pass-through (neither flag)
        ctx_plain = GenerationContext(
            topic_slug="Addition (carries)", subject="Maths", grade=3,
            ncert_chapter="Addition (carries)", ncert_subtopics=[],
            bloom_level="recall", format_mix={},
            scaffolding=False, challenge_mode=False,
            valid_skill_tags=ctx.valid_skill_tags, child_context={},
        )
        plain_qs = [{"id": 1, "format": "word_problem", "question_text": "A question",
                     "answer": "5", "skill_tag": ctx.valid_skill_tags[0], "difficulty": "easy"}]
        out3 = calibrator.calibrate(plain_qs, ctx_plain)
        check("plain: list length unchanged",   len(out3) == 1)
        check("plain: no hints injected",        not out3[0].get("hint"))
        check("plain: no bonus appended",        not any(q.get("_is_bonus") for q in out3))

    except Exception as e:
        check("DifficultyCalibrator", False, str(e))

# ---------------------------------------------------------------------------
print("\n━━━ STEP 6: Meta cache key logic ━━━")
# ---------------------------------------------------------------------------
try:
    from app.services.slot_engine import _meta_cache_key, _get_cached_meta, _set_cached_meta, _META_CACHE
    key1 = _meta_cache_key(3, "Maths", "Addition (carries)", "recall")
    key2 = _meta_cache_key(3, "Maths", "Addition (carries)", "recall")
    key3 = _meta_cache_key(3, "Maths", "Subtraction (borrowing)", "recall")
    check("Same inputs → same key", key1 == key2, key1[:12])
    check("Different topic → different key", key1 != key3)
    check("Key is md5 hex string (32 chars)", len(key1) == 32)

    # Simulate a cache miss then hit
    _META_CACHE.clear()
    miss = _get_cached_meta(key1)
    check("Cache MISS returns None", miss is None)

    fake_meta = {"title": "test", "instructions": "test instructions"}
    _set_cached_meta(key1, fake_meta)
    hit = _get_cached_meta(key1)
    check("Cache HIT returns stored value", hit == fake_meta)
    check("Cache HIT has correct title", hit.get("title") == "test")
    _META_CACHE.clear()  # clean up
except Exception as e:
    check("Meta cache logic", False, str(e))

# ---------------------------------------------------------------------------
print("\n━━━ STEP 7: Full agent chain A → B → C → D (wiring check) ━━━")
# ---------------------------------------------------------------------------
if ctx:
    try:
        # Simulate what run_slot_pipeline_async does after generation:
        # QualityReviewer → DifficultyCalibrator

        questions = [
            {"id": i, "slot_type": st, "format": fmt,
             "question_text": text, "answer": ans,
             "skill_tag": ctx.valid_skill_tags[0], "difficulty": "easy"}
            for i, (st, fmt, text, ans) in enumerate([
                ("recognition",    "column_setup",  "What is 4 + 9?",    "13"),
                ("application",    "word_problem",  "A long word problem with many words here and there.", "5"),
                ("representation", "missing_number","Find the missing",   "7"),
                ("error_detection","error_spot",    "Spot error: 3+3=7", "7"),
                ("thinking",       "thinking",      "Why does this work?","Because addition is commutative"),
            ], 1)
        ]

        # Scaffold context: should sort + add hints
        scaffold_ctx = GenerationContext(
            topic_slug="Addition (carries)", subject="Maths", grade=3,
            ncert_chapter="Addition (carries)", ncert_subtopics=["Add with carry"],
            bloom_level="recall",
            format_mix={"mcq": 0, "fill_blank": 0, "word_problem": 20},
            scaffolding=True, challenge_mode=False,
            valid_skill_tags=ctx.valid_skill_tags, child_context={},
        )

        # Step C: Quality review
        reviewer = get_quality_reviewer()
        reviewed = reviewer.review_worksheet(questions, scaffold_ctx)

        # Step D: Difficulty calibrate
        calibrator = get_difficulty_calibrator()
        final = calibrator.calibrate(reviewed.questions, scaffold_ctx)

        check("Chain output is a list", isinstance(final, list))
        check("Chain output has correct count", len(final) == 5, f"len={len(final)}")
        check("First question is shortest (sort worked)",
              len(final[0]["question_text"].split()) <= len(final[-1]["question_text"].split()))
        check("First 2 questions have hints",
              bool(final[0].get("hint")) and bool(final[1].get("hint")))
        check("error_detection answer not corrected",
              next(q for q in final if q["slot_type"] == "error_detection")["answer"] == "7")
        check("All questions have skill_tag",
              all(q.get("skill_tag") for q in final))

    except Exception as e:
        check("Full agent chain", False, str(e))

# ---------------------------------------------------------------------------
print("\n━━━ STEP 8: Singleton identity ━━━")
# ---------------------------------------------------------------------------
try:
    from app.services.topic_intelligence import get_topic_intelligence_agent
    a1, a2 = get_topic_intelligence_agent(), get_topic_intelligence_agent()
    check("TopicIntelligenceAgent singleton", a1 is a2)

    r1, r2 = get_quality_reviewer(), get_quality_reviewer()
    check("QualityReviewerAgent singleton", r1 is r2)

    c1, c2 = get_difficulty_calibrator(), get_difficulty_calibrator()
    check("DifficultyCalibrator singleton", c1 is c2)
except Exception as e:
    check("Singleton identity", False, str(e))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print()
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
total  = len(results)
print(f"━━━ PHASE 2 E2E: {passed}/{total} checks passed" + (f" — {failed} FAILED" if failed else " — ALL PASS ✓") + " ━━━")
if failed:
    print("\nFailed checks:")
    for name, ok in results:
        if not ok:
            print(f"  ✗  {name}")
    sys.exit(1)
