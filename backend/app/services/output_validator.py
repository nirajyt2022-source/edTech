"""
Output validation for all AI-generated content.

Validates worksheet questions, revision notes, flashcards, and grading results
BEFORE they reach the user. If validation fails, triggers a retry with error feedback.

Usage:
    from app.services.output_validator import get_validator
    validator = get_validator()

    is_valid, errors = validator.validate_worksheet(data, grade="Class 4", subject="Maths", topic="Fractions", num_questions=10)
    if not is_valid:
        # retry or return with warnings
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("skolar.validator")


class OutputValidator:
    """Validates AI-generated outputs before they reach users."""

    # ── Verb normalization for deep template ──────────────────────────────

    _VERB_FORMS: dict[str, str] = {
        "buys": "buy",
        "bought": "buy",
        "buying": "buy",
        "gives": "give",
        "gave": "give",
        "giving": "give",
        "given": "give",
        "has": "have",
        "had": "have",
        "having": "have",
        "gets": "get",
        "got": "get",
        "getting": "get",
        "eats": "eat",
        "ate": "eat",
        "eating": "eat",
        "sells": "sell",
        "sold": "sell",
        "selling": "sell",
        "makes": "make",
        "made": "make",
        "making": "make",
        "takes": "take",
        "took": "take",
        "taking": "take",
        "reads": "read",
        "reading": "read",
        "writes": "write",
        "wrote": "write",
        "writing": "write",
        "picks": "pick",
        "picked": "pick",
        "picking": "pick",
        "shares": "share",
        "shared": "share",
        "sharing": "share",
        "collects": "collect",
        "collected": "collect",
        "collecting": "collect",
        "distributes": "distribute",
        "distributed": "distribute",
        "spends": "spend",
        "spent": "spend",
        "spending": "spend",
        "saves": "save",
        "saved": "save",
        "saving": "save",
        "plants": "plant",
        "planted": "plant",
        "planting": "plant",
        "counts": "count",
        "counted": "count",
        "counting": "count",
        "arranges": "arrange",
        "arranged": "arrange",
        "packs": "pack",
        "packed": "pack",
        "packing": "pack",
    }

    # ── Worksheet Validation ──────────────────────────────────────────────

    def validate_worksheet(
        self,
        data: dict[str, Any],
        grade: str = "",
        subject: str = "",
        topic: str = "",
        num_questions: int = 10,
    ) -> tuple[bool, list[str]]:
        """
        Validate a generated worksheet.
        Returns (is_valid, list_of_errors).
        """
        errors: list[str] = []
        questions = data.get("questions", [])

        # 1. Question count — exact match required (retry trigger)
        if len(questions) < num_questions:
            errors.append(f"[count_mismatch] Too few questions: got {len(questions)}, need {num_questions}")

        # 2. Every question needs required fields
        for i, q in enumerate(questions):
            qid = q.get("id", f"Q{i + 1}")

            if not q.get("text", "").strip():
                errors.append(f"{qid}: empty question text")

            if not q.get("correct_answer") and q.get("correct_answer") != 0:
                errors.append(f"{qid}: missing correct_answer")

            # MCQ must have options
            q_type = q.get("type", "")
            if q_type == "mcq" and (not q.get("options") or len(q.get("options", [])) < 3):
                errors.append(f"{qid}: MCQ needs at least 3 options")

            # True/false answer must be valid (English: True/False, Hindi: सही/गलत)
            if q_type == "true_false":
                ans = str(q.get("correct_answer", "")).strip().lower()
                if ans not in ("true", "false", "सही", "गलत"):
                    errors.append(f"{qid}: true_false answer must be 'True' or 'False', got '{ans}'")

            # MCQ answer must be in options
            if q_type == "mcq" and q.get("options") and q.get("correct_answer"):
                answer = str(q["correct_answer"]).strip()
                options_text = [str(o).strip() for o in q["options"]]
                # Check if answer matches any option (by text or by letter like A/B/C/D)
                letters = [chr(65 + j) for j in range(len(options_text))]
                if answer not in options_text and answer.upper() not in letters:
                    errors.append(f"{qid}: MCQ answer '{answer}' not in options")

        # 3. Duplicate detection — exact + pattern-based near-duplicates
        texts = [q.get("text", "").strip().lower() for q in questions if q.get("text")]
        seen = set()
        for t in texts:
            # Normalize whitespace for comparison
            normalized = re.sub(r"\s+", " ", t)
            if normalized in seen:
                errors.append("Duplicate question detected")
                break
            seen.add(normalized)

        # 3b. Near-duplicate detection — strip names/numbers/times to create templates
        if len(questions) >= 4:
            templates: list[str] = []
            for q in questions:
                text = q.get("text", "").strip().lower()
                tmpl = self._make_template(text)
                templates.append(tmpl)
            from collections import Counter

            counts = Counter(templates)
            threshold = max(3, int(len(questions) * 0.50) + 1)
            for tmpl, cnt in counts.items():
                if cnt >= threshold:
                    errors.append(
                        f"Near-duplicate pattern detected: {cnt}/{len(questions)} questions share the same structure"
                    )
                    break

        # 4. Grade-level appropriateness
        grade_num = self._parse_grade_num(grade)
        if grade_num:
            for i, q in enumerate(questions):
                qid = q.get("id", f"Q{i + 1}")
                text = q.get("text", "")

                # Class 1-2: questions shouldn't be too long
                if grade_num <= 2 and len(text.split()) > 40:
                    errors.append(f"{qid}: question too long for {grade} ({len(text.split())} words)")

                # Class 1-2: shouldn't use complex vocabulary
                if grade_num <= 2:
                    complex_words = {
                        "approximately",
                        "calculate",
                        "determine",
                        "evaluate",
                        "demonstrate",
                        "illustrate",
                        "hypothesis",
                        "consequently",
                    }
                    used_complex = [w for w in text.lower().split() if w in complex_words]
                    if used_complex:
                        errors.append(f"{qid}: complex vocabulary for {grade}: {', '.join(used_complex)}")

        # 5. Type diversity — no single question type > 40% of the worksheet
        if len(questions) >= 5:
            from collections import Counter as _Counter

            type_counts = _Counter(q.get("type", "unknown") for q in questions)
            for qtype, cnt in type_counts.items():
                if cnt / len(questions) > 0.40:
                    errors.append(
                        f"Type diversity: '{qtype}' is {cnt}/{len(questions)} "
                        f"({cnt * 100 // len(questions)}%), max allowed is 40%"
                    )
                    break  # one error is enough

        # 6. Disallowed keyword check (from topic profile)
        if topic:
            try:
                from app.data.topic_profiles import get_topic_profile

                profile = get_topic_profile(topic, subject or None, grade)
                if profile:
                    disallowed = profile.get("disallowed_keywords", [])
                    if disallowed:
                        for i, q in enumerate(questions):
                            qid = q.get("id", f"Q{i + 1}")
                            text_lower = q.get("text", "").lower()
                            for kw in disallowed:
                                if kw.lower() in text_lower:
                                    errors.append(f"{qid}: disallowed keyword '{kw}' for topic '{topic}'")
                                    break  # one keyword per question is enough
            except Exception as exc:
                logger.debug("Disallowed keyword check skipped for topic '%s': %s", topic, exc)

        # 7. Maths answer verification (basic checks)
        if subject.lower() in ("maths", "mathematics", "math"):
            for i, q in enumerate(questions):
                qid = q.get("id", f"Q{i + 1}")
                verified = self._verify_math_answer(q)
                if verified is False:
                    errors.append(f"{qid}: math answer appears incorrect")

        # 7b. Visual-answer coherence
        for i, q in enumerate(questions):
            if q.get("visual_type"):
                qid = q.get("id", f"Q{i + 1}")
                coherence = self._verify_visual_answer_coherence(q)
                if coherence is False:
                    errors.append(f"{qid}: visual data does not match correct_answer")

        # 7c. Visual-topic appropriateness (disallowed visual types)
        if topic:
            try:
                from app.data.topic_profiles import get_topic_profile

                profile = get_topic_profile(topic, subject or None, grade)
                if profile:
                    disallowed_visuals = profile.get("disallowed_visual_types", [])
                    if disallowed_visuals:
                        disallowed_set = set(v.lower() for v in disallowed_visuals)
                        for i, q in enumerate(questions):
                            vtype = q.get("visual_type", "")
                            if vtype and vtype.lower() in disallowed_set:
                                qid = q.get("id", f"Q{i + 1}")
                                errors.append(f"{qid}: visual type '{vtype}' is disallowed for topic '{topic}'")
            except Exception as exc:
                logger.debug("Visual-topic check skipped for topic '%s': %s", topic, exc)

        # 8. Must have answer_key or answers extractable from questions
        answer_key = data.get("answer_key", {})
        if not answer_key and all(not q.get("correct_answer") for q in questions):
            errors.append("No answer key and no answers in questions")

        # 9. Opening verb diversity — no verb may start >2 questions
        if len(questions) >= 5:
            opening_verbs: list[str] = []
            for q in questions:
                text = q.get("text", "").strip()
                if text:
                    first_word = text.split()[0].lower().rstrip(".:,;!?")
                    opening_verbs.append(first_word)
            if opening_verbs:
                from collections import Counter as _VerbCounter

                verb_counts = _VerbCounter(opening_verbs)
                for verb, cnt in verb_counts.most_common(1):
                    if cnt > 2:
                        errors.append(f"Opening verb '{verb}' repeats {cnt} times (max 2 per worksheet)")

        # 10. Countable object uniqueness — no object noun in >1 question
        if len(questions) >= 5:
            _OBJECT_RE = re.compile(
                r"\b(\w+(?:es|s))\b"  # plural nouns (rough heuristic)
            )
            _COUNTABLE_OBJECTS = frozenset(
                {
                    "apples",
                    "oranges",
                    "mangoes",
                    "bananas",
                    "pencils",
                    "pens",
                    "erasers",
                    "books",
                    "notebooks",
                    "pages",
                    "marbles",
                    "balls",
                    "sweets",
                    "toffees",
                    "chocolates",
                    "stickers",
                    "stamps",
                    "coins",
                    "rupees",
                    "toys",
                    "flowers",
                    "leaves",
                    "trees",
                    "birds",
                    "fishes",
                    "eggs",
                    "cups",
                    "plates",
                    "bottles",
                    "bags",
                    "boxes",
                    "beads",
                    "shells",
                    "stones",
                    "buttons",
                    "seeds",
                    "cookies",
                    "cakes",
                    "candies",
                    "balloons",
                    "candles",
                    "ribbons",
                    "stars",
                    "tickets",
                    "cards",
                    "crayons",
                    "colours",
                    "colors",
                    "caps",
                    "cars",
                    "buses",
                }
            )
            object_to_questions: dict[str, int] = {}
            for q in questions:
                text = q.get("text", "").lower()
                found_objects = set(_OBJECT_RE.findall(text)) & _COUNTABLE_OBJECTS
                for obj in found_objects:
                    object_to_questions[obj] = object_to_questions.get(obj, 0) + 1
            for obj, cnt in object_to_questions.items():
                if cnt > 1:
                    errors.append(f"Countable object '{obj}' appears in {cnt} questions (max 1 per worksheet)")
                    break  # one error is enough

        # 11. Number reuse across questions — no number in >2 questions
        if len(questions) >= 5:
            number_to_questions: dict[str, int] = {}
            _NUM_RE = re.compile(r"\b(\d+)\b")
            for q in questions:
                text = q.get("text", "")
                nums_in_q = set(_NUM_RE.findall(text))
                for n in nums_in_q:
                    if n in ("0", "1"):
                        continue  # trivial numbers excluded
                    number_to_questions[n] = number_to_questions.get(n, 0) + 1
            for num_str, cnt in number_to_questions.items():
                if cnt > 2:
                    errors.append(f"Number '{num_str}' appears in {cnt} questions (max 2 per worksheet)")
                    break  # one error is enough

        # 12. Round number cap — ≤30% of numbers may be multiples of 5 or 10
        if len(questions) >= 5 and subject.lower() in ("maths", "mathematics", "math"):
            all_nums: list[int] = []
            _NUM_RE_12 = re.compile(r"\b(\d+)\b")
            for q in questions:
                text = q.get("text", "")
                for n_str in _NUM_RE_12.findall(text):
                    n = int(n_str)
                    if n > 1:  # skip 0 and 1
                        all_nums.append(n)
            if len(all_nums) >= 5:
                round_count = sum(1 for n in all_nums if n % 5 == 0)
                round_pct = round_count / len(all_nums)
                if round_pct > 0.30:
                    errors.append(
                        f"Round number overuse: {round_count}/{len(all_nums)} "
                        f"({round_pct:.0%}) are multiples of 5 or 10 (max 30%)"
                    )

        # 13. Number pair diversity — addition/subtraction pairs need digit variety
        if len(questions) >= 5 and subject.lower() in ("maths", "mathematics", "math"):
            _PAIR_RE = re.compile(r"(\d+)\s*[+\-]\s*(\d+)")
            pairs_seen: list[tuple[int, int]] = []
            for q in questions:
                text = q.get("text", "")
                m = _PAIR_RE.search(text)
                if m:
                    pairs_seen.append((int(m.group(1)), int(m.group(2))))
            if len(pairs_seen) >= 3:
                last_digits = set()
                for a, b in pairs_seen:
                    last_digits.add(a % 10)
                    last_digits.add(b % 10)
                if len(last_digits) < 3:
                    errors.append(
                        f"Number pair monotony: only {len(last_digits)} unique last digits "
                        f"across {len(pairs_seen)} pairs (need ≥3)"
                    )

        # 14. Engagement framing — at least 20% of questions should use warm framing
        if len(questions) >= 5:
            _ENGAGEMENT_RE = re.compile(
                r"(?i)^(help|can you|try to|figure out|let'?s|guess)",
            )
            engagement_count = sum(1 for q in questions if _ENGAGEMENT_RE.match(q.get("text", "").strip()))
            target = max(2, len(questions) // 5)
            if engagement_count < target:
                errors.append(
                    f"Low engagement framing: {engagement_count}/{len(questions)} questions use "
                    f"'Help…'/'Can you…' style (need ≥{target})"
                )

        # 15. Sentence structure diversity (L2) — ≥3 distinct structures per 10Q
        if len(questions) >= 5:
            _QUESTION_WORD_RE = re.compile(r"(?i)^(what|which|how|who|where|when|why)\b")
            _IMPERATIVE_RE = re.compile(
                r"(?i)^(find|solve|write|fill|complete|calculate|match|draw|circle|count|add|subtract|multiply|divide|arrange|list|name|identify)\b"
            )
            _CONDITIONAL_RE = re.compile(r"(?i)^(if|suppose|imagine|given|when)\b")
            structures: set[str] = set()
            for q in questions:
                text = q.get("text", "").strip()
                if not text:
                    continue
                if _QUESTION_WORD_RE.match(text):
                    structures.add("question_word")
                elif _IMPERATIVE_RE.match(text):
                    structures.add("imperative")
                elif _CONDITIONAL_RE.match(text):
                    structures.add("conditional")
                else:
                    structures.add("statement")
            min_structures = 3 if len(questions) >= 10 else 2
            if len(structures) < min_structures:
                errors.append(
                    f"Sentence structure monotony: only {len(structures)} structure type(s) "
                    f"({', '.join(sorted(structures))}), need ≥{min_structures}"
                )

        # 16. Filler phrase ban (L3) — no "the following"/"given below" unless visual
        _FILLER_PHRASES = ["the following", "given below", "mentioned below", "shown below", "listed below"]
        for i, q in enumerate(questions):
            text = q.get("text", "").lower()
            has_visual = bool(q.get("visual_type") or q.get("visual_data"))
            if not has_visual:
                for filler in _FILLER_PHRASES:
                    if filler in text:
                        qid = q.get("id", f"Q{i + 1}")
                        errors.append(f"{qid}: filler phrase '{filler}' without visual context")
                        break

        # 17. Sequence step variety (N4) — pattern/sequence questions should vary step sizes
        if len(questions) >= 5 and subject.lower() in ("maths", "mathematics", "math"):
            _SEQ_RE = re.compile(r"(\d+)\s*,\s*(\d+)\s*,\s*(\d+)")
            step_sizes: list[int] = []
            for q in questions:
                text = q.get("text", "")
                m = _SEQ_RE.search(text)
                if m:
                    a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    step1 = b - a
                    step2 = c - b
                    if step1 == step2 and step1 != 0:
                        step_sizes.append(abs(step1))
            if len(step_sizes) >= 3:
                unique_steps = set(step_sizes)
                if len(unique_steps) == 1:
                    errors.append(
                        f"Sequence step monotony: all {len(step_sizes)} sequences use step={step_sizes[0]}, "
                        f"need variety"
                    )

        # 18. No scenario repeat (R2) — word problems should use unique scenarios
        if len(questions) >= 5:
            _SCENARIO_WORDS = frozenset(
                {
                    "market",
                    "shop",
                    "store",
                    "school",
                    "park",
                    "zoo",
                    "kitchen",
                    "festival",
                    "playground",
                    "station",
                    "library",
                    "farm",
                    "bakery",
                    "hospital",
                    "garden",
                    "field",
                    "party",
                    "temple",
                    "beach",
                    "museum",
                    "cinema",
                    "restaurant",
                    "home",
                    "classroom",
                    "bus",
                    "train",
                }
            )
            scenario_counts: dict[str, int] = {}
            for q in questions:
                text = q.get("text", "").lower()
                words = set(re.findall(r"\b\w+\b", text))
                found_scenarios = words & _SCENARIO_WORDS
                for sc in found_scenarios:
                    scenario_counts[sc] = scenario_counts.get(sc, 0) + 1
            for sc, cnt in scenario_counts.items():
                if cnt > 1:
                    errors.append(
                        f"Scenario '{sc}' repeated in {cnt} questions (each word problem should use a unique setting)"
                    )
                    break  # one error is enough

        # 19. Visual mandatory compliance (informational warnings, non-blocking)
        if subject.lower() == "maths":
            from app.data.topic_profiles import get_topic_profile

            _profile = get_topic_profile(topic, subject or None, grade)
            _mandatory = _profile.get("mandatory_visuals") if _profile else None
            if _mandatory:
                from app.services.worksheet_generator import effective_min_count

                _req_types = _mandatory.get("required_types", [])
                _min_ct = effective_min_count(_mandatory.get("min_count", 0), num_questions)
                _found: dict[str, int] = {}
                for q in questions:
                    _vt = q.get("visual_type")
                    if _vt:
                        _found[_vt] = _found.get(_vt, 0) + 1
                _total_vis = sum(_found.values())
                _missing_req = [t for t in _req_types if t not in _found]
                if _missing_req:
                    errors.append(f"[visual_mandatory] Missing required visual types: {', '.join(_missing_req)}")
                if _total_vis < _min_ct:
                    errors.append(f"[visual_mandatory] {_total_vis}/{_min_ct} visual questions (below minimum)")

        # 20. Deep sentence-structure diversity — flag if too many questions share a formula
        if len(questions) >= 5:
            deep_templates = [self._make_deep_template(q.get("text", "")) for q in questions]
            unique_count = len(set(deep_templates))
            diversity_score = unique_count / len(deep_templates)

            if diversity_score < 0.6:
                errors.append(
                    f"[sentence_diversity] Low diversity score: {diversity_score:.0%} "
                    f"({unique_count}/{len(deep_templates)} unique structures). Threshold: 60%"
                )

            # Flag dominant template if it covers >40% of questions
            from collections import Counter as _DivCounter

            tmpl_counts = _DivCounter(deep_templates)
            for tmpl, cnt in tmpl_counts.most_common(1):
                if cnt > max(2, int(len(questions) * 0.4)):
                    errors.append(f"[sentence_diversity] Dominant template covers {cnt}/{len(questions)} questions")

        # 21. MCQ option quality — ban "all/none of the above" and lazy meta-options
        _BANNED_MCQ_PHRASES = frozenset(
            {
                "all of the above",
                "none of the above",
                "both a and b",
                "all the above",
                "none of above",
                "both (a) and (b)",
                "all of these",
                "none of these",
            }
        )
        for i, q in enumerate(questions):
            q_type = q.get("type", "")
            if q_type != "mcq":
                continue
            options = [str(o).strip().lower() for o in q.get("options", [])]
            for opt in options:
                if opt in _BANNED_MCQ_PHRASES:
                    qid = q.get("id", f"Q{i + 1}")
                    errors.append(f"{qid}: [mcq_quality] Banned option '{opt}'")
                    break

        # 22. Fill-in-the-blank ambiguity detection
        _FB_BLANK_RE_22 = re.compile(r"_{2,}|\.{3,}|\?{2,}|______|\[blank\]|\[___\]", re.IGNORECASE)
        _FB_GENERIC_22 = frozenset(
            {
                "a",
                "an",
                "the",
                "is",
                "are",
                "was",
                "were",
                "it",
                "this",
                "that",
                "of",
                "in",
                "on",
                "at",
                "to",
                "for",
                "with",
                "by",
                "from",
                "and",
                "or",
                "but",
                "not",
                "yes",
                "no",
                "very",
                "so",
                "too",
            }
        )
        _FB_SUBJECTIVE_22 = re.compile(
            r"(?i)(write a|write any|give an example|give a|name a|name any|"
            r"your own|your favou?rite|anything|any word|any name|any number|any suitable)"
        )
        for i, q in enumerate(questions):
            q_type = q.get("type", "")
            if q_type not in ("fill_blank", "fill_in_blank"):
                continue
            qid = q.get("id", f"Q{i + 1}")
            text = q.get("text", "")
            if not _FB_BLANK_RE_22.search(text):
                errors.append(f"{qid}: fill-blank ambiguity — missing blank marker")
            if _FB_SUBJECTIVE_22.search(text):
                errors.append(f"{qid}: fill-blank ambiguity — subjective fill prompt")
            ans = str(q.get("correct_answer", "") or "").strip().lower()
            if ans in _FB_GENERIC_22:
                errors.append(f"{qid}: fill-blank ambiguity — generic fill-blank answer '{ans}'")

        # 23. Render integrity — phantom visual references
        _VISUAL_REF_RE_23 = re.compile(
            r"(?i)\b(?:look at|see|observe|refer to|check|examine|study)"
            r"\s+(?:the\s+)?(?:picture|diagram|image|figure|table|chart|graph|number line|clock|grid|map|pattern)"
        )
        _TABLE_REF_RE_23 = re.compile(r"(?i)\b(?:the following|given|below)\s+(?:table|chart|graph|diagram)")
        for i, q in enumerate(questions):
            qid = q.get("id", f"Q{i + 1}")
            text = q.get("text", "")
            vis_match = _VISUAL_REF_RE_23.search(text) or _TABLE_REF_RE_23.search(text)
            if vis_match:
                has_visual = bool(q.get("visual_type") or q.get("visual_data") or q.get("images"))
                if not has_visual:
                    errors.append(
                        f"{qid}: render integrity — phantom visual reference "
                        f"(text says '{vis_match.group()}' but no visual attached)"
                    )

        is_valid = len(errors) == 0
        if not is_valid:
            logger.warning("Worksheet validation failed", extra={"errors": errors, "topic": topic, "grade": grade})
        return is_valid, errors

    # ── Revision Notes Validation ─────────────────────────────────────────

    def validate_revision(self, data: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate revision notes output."""
        errors: list[str] = []

        if not data.get("key_concepts") or len(data.get("key_concepts", [])) < 2:
            errors.append("Too few key concepts (need at least 2)")

        if not data.get("worked_examples") or len(data.get("worked_examples", [])) < 1:
            errors.append("Missing worked examples")

        if not data.get("introduction", "").strip():
            errors.append("Missing introduction")

        # Each key concept should have title and explanation
        for i, concept in enumerate(data.get("key_concepts", [])):
            if not concept.get("title", "").strip():
                errors.append(f"Key concept {i + 1}: missing title")
            if not concept.get("explanation", "").strip():
                errors.append(f"Key concept {i + 1}: missing explanation")

        if not data.get("quick_quiz") or len(data.get("quick_quiz", [])) < 2:
            errors.append("Need at least 2 quick quiz questions")

        is_valid = len(errors) == 0
        if not is_valid:
            logger.warning("Revision validation failed", extra={"errors": errors})
        return is_valid, errors

    # ── Flashcard Validation ──────────────────────────────────────────────

    def validate_flashcards(self, data: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate flashcard output."""
        errors: list[str] = []
        cards = data.get("cards", [])

        if len(cards) < 8:
            errors.append(f"Too few cards: {len(cards)} (need at least 8)")

        for i, card in enumerate(cards):
            if not card.get("front", "").strip():
                errors.append(f"Card {i + 1}: empty front")
            if not card.get("back", "").strip():
                errors.append(f"Card {i + 1}: empty back")
            # Front should be short (it's a card)
            if len(card.get("front", "").split()) > 20:
                errors.append(f"Card {i + 1}: front too long ({len(card['front'].split())} words)")

        # Check for duplicate fronts
        fronts = [c.get("front", "").strip().lower() for c in cards]
        if len(fronts) != len(set(fronts)):
            errors.append("Duplicate flashcard fronts detected")

        is_valid = len(errors) == 0
        if not is_valid:
            logger.warning("Flashcard validation failed", extra={"errors": errors})
        return is_valid, errors

    # ── Grading Validation ────────────────────────────────────────────────

    def validate_grading(self, data: dict[str, Any], total_questions: int = 0) -> tuple[bool, list[str]]:
        """Validate grading results."""
        errors: list[str] = []

        results = data.get("results", [])
        if not results:
            errors.append("No grading results returned")

        score = data.get("score", -1)
        total = data.get("total", -1)

        if score < 0 or total < 0:
            errors.append("Invalid score or total")
        if total > 0 and score > total:
            errors.append(f"Score ({score}) exceeds total ({total})")

        for i, r in enumerate(results):
            if "is_correct" not in r and "status" not in r:
                errors.append(f"Result {i + 1}: missing is_correct/status field")

        is_valid = len(errors) == 0
        if not is_valid:
            logger.warning("Grading validation failed", extra={"errors": errors})
        return is_valid, errors

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _make_template(text: str) -> str:
        """Strip names, numbers, and times from question text to create a structural template.

        Used for near-duplicate detection — two questions that differ only in
        names/numbers/times will produce the same template.
        """
        # Replace time patterns (e.g. "3:45 PM", "10:30 AM")
        tmpl = re.sub(r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?", "<TIME>", text)
        # Replace numbers (including currency like ₹500)
        tmpl = re.sub(r"₹?\d+(?:\.\d+)?", "<NUM>", tmpl)
        # Replace common Indian names (case-insensitive)
        _NAMES_PATTERN = (
            r"\b(?:aarav|ananya|vihaan|diya|reyansh|saanvi|arjun|isha|kabir|myra|"
            r"aditya|kiara|rohan|priya|vivaan|anika|krishna|zara|rudra|pari|"
            r"atharv|navya|shaurya|aadhya|dhruv|riya|arnav|sara|dev|anvi|"
            r"ishan|tara|kian|meera|yash|nisha|aryan|siya|neil|pooja|"
            r"rahul|sneha|manav|kavya|sameer|tanvi|kunal|ritika|"
            r"ravi|kiran|anita|deepa|suresh|sunita|mohan)\b"
        )
        tmpl = re.sub(_NAMES_PATTERN, "<NAME>", tmpl, flags=re.IGNORECASE)
        # Collapse whitespace
        tmpl = re.sub(r"\s+", " ", tmpl).strip()
        return tmpl

    @classmethod
    def _make_deep_template(cls, text: str) -> str:
        """Create a deeper structural template by normalizing names, numbers,
        times, countable objects, scenario words, and verb forms.

        Two questions that differ only in surface-level details (names, numbers,
        objects, verbs, places) will produce the same deep template.
        """
        # Step 1: Apply existing template (handles names, numbers, times)
        tmpl = cls._make_template(text)

        # Step 2: Normalize countable objects → <OBJ>
        _COUNTABLE_OBJ_PATTERN = (
            r"\b(?:apples|oranges|mangoes|bananas|pencils|pens|erasers|books|"
            r"notebooks|pages|marbles|balls|sweets|toffees|chocolates|stickers|"
            r"stamps|coins|rupees|toys|flowers|leaves|trees|birds|fishes|eggs|"
            r"cups|plates|bottles|bags|boxes|beads|shells|stones|buttons|seeds|"
            r"cookies|cakes|candies|balloons|candles|ribbons|stars|tickets|cards|"
            r"crayons|colours|colors|caps|cars|buses)\b"
        )
        tmpl = re.sub(_COUNTABLE_OBJ_PATTERN, "<OBJ>", tmpl, flags=re.IGNORECASE)

        # Step 3: Normalize scenario/location words → <PLACE>
        _SCENARIO_PATTERN = (
            r"\b(?:market|shop|store|school|park|zoo|kitchen|festival|playground|"
            r"station|library|farm|bakery|hospital|garden|field|party|temple|"
            r"beach|museum|cinema|restaurant|home|classroom|bus|train)\b"
        )
        tmpl = re.sub(_SCENARIO_PATTERN, "<PLACE>", tmpl, flags=re.IGNORECASE)

        # Step 4: Normalize verb forms → <VERB>
        def _replace_verb(m: re.Match) -> str:
            word = m.group(0).lower()
            return "<VERB>" if word in cls._VERB_FORMS else m.group(0)

        _verb_keys = "|".join(re.escape(v) for v in cls._VERB_FORMS)
        tmpl = re.sub(rf"\b({_verb_keys})\b", _replace_verb, tmpl, flags=re.IGNORECASE)

        # Step 5: Normalize pronouns → <NAME>
        tmpl = re.sub(r"\b(?:she|he|her|his|him|they|them|their)\b", "<NAME>", tmpl, flags=re.IGNORECASE)

        # Step 6: Collapse adjacent duplicate placeholders and whitespace
        tmpl = re.sub(r"(<(?:NAME|NUM|OBJ|PLACE|VERB|TIME)>)(\s*\1)+", r"\1", tmpl)
        tmpl = re.sub(r"\s+", " ", tmpl).strip()
        return tmpl

    @staticmethod
    def _parse_grade_num(grade: str) -> int | None:
        """Extract number from 'Class 4' -> 4."""
        match = re.search(r"\d+", grade)
        return int(match.group()) if match else None

    @staticmethod
    def _verify_clock_answer(q: dict) -> bool | None:
        """Verify that clock visual_data matches the correct_answer.

        Returns True (match), False (mismatch), or None (can't verify).
        """
        vd = q.get("visual_data")
        answer = str(q.get("correct_answer", ""))
        if not vd or not isinstance(vd, dict):
            return None
        hour = vd.get("hour")
        minute = vd.get("minute")
        if hour is None or minute is None:
            return None
        match = re.search(r"(\d{1,2}):(\d{2})", answer)
        if not match:
            return None
        ans_hour = int(match.group(1))
        ans_minute = int(match.group(2))
        if ans_hour == int(hour) and ans_minute == int(minute):
            return True
        logger.warning(
            "Clock coherence failed",
            extra={"visual": {"hour": hour, "minute": minute}, "answer": answer},
        )
        return False

    @staticmethod
    def _verify_object_group_answer(q: dict) -> bool | None:
        """Verify that object_group visual_data matches the correct_answer.

        Returns True (match), False (mismatch), or None (can't verify).
        """
        vd = q.get("visual_data")
        answer = str(q.get("correct_answer", ""))
        if not vd or not isinstance(vd, dict):
            return None
        groups = vd.get("groups")
        operation = vd.get("operation", "+")
        if not groups or not isinstance(groups, list):
            return None
        counts = []
        for g in groups:
            c = g.get("count")
            if c is None:
                return None
            counts.append(int(c))
        if not counts:
            return None
        if operation == "+":
            expected = sum(counts)
        elif operation == "-":
            expected = counts[0] - sum(counts[1:])
        else:
            return None
        # Parse numeric answer (strip ₹ prefix, commas)
        cleaned = re.sub(r"[₹,\s]", "", answer)
        num_match = re.search(r"-?\d+", cleaned)
        if not num_match:
            return None
        ans_num = int(num_match.group())
        if ans_num == expected:
            return True
        logger.warning(
            "Object group coherence failed",
            extra={"expected": expected, "answer": answer, "operation": operation},
        )
        return False

    @classmethod
    def _verify_visual_answer_coherence(cls, q: dict) -> bool | None:
        """Dispatch visual-answer coherence check based on visual_type.

        Returns True (match), False (mismatch), or None (can't verify / not applicable).
        """
        vtype = q.get("visual_type", "")
        if not vtype:
            return None
        if vtype == "clock":
            return cls._verify_clock_answer(q)
        if vtype == "object_group":
            return cls._verify_object_group_answer(q)
        return None

    @staticmethod
    def _verify_math_answer(q: dict) -> bool | None:
        """
        Try to verify math answers (simple and multi-step).
        Returns True (correct), False (wrong), or None (can't verify).
        """
        from app.services.quality_reviewer import _extract_arithmetic_expression

        text = q.get("text", "")
        answer = q.get("correct_answer", "")
        q_type = q.get("type", "")

        # Only verify fill_blank/short_answer math questions with numeric answers
        if q_type not in ("fill_blank", "short_answer"):
            return None

        extracted = _extract_arithmetic_expression(text)
        if extracted is None:
            return None

        _expr, expected = extracted
        try:
            answer_num = float(str(answer).replace(",", "").strip())
        except (ValueError, TypeError):
            return None

        if abs(answer_num - expected) < 0.01:
            return True

        logger.warning(
            "Math verification failed",
            extra={"question": text[:80], "expected": expected, "got": answer_num},
        )
        return False


# Singleton
_validator: OutputValidator | None = None


def get_validator() -> OutputValidator:
    global _validator
    if _validator is None:
        _validator = OutputValidator()
    return _validator
