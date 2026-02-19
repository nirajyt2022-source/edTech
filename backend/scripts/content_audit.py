#!/usr/bin/env python3
"""
PracticeCraft Content Audit — Live API
=======================================
Generates 3 questions per topic against the production Railway API and runs
5 quality checks on every generated question.

Usage:
    cd backend
    python scripts/content_audit.py <auth_token>

Get auth_token from:
  Browser → DevTools → Application → Local Storage → sb-*-auth-token → access_token
"""

import json
import operator
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROD_API_BASE       = "https://edtech-production-c7ec.up.railway.app"
REPORT_PATH         = Path(__file__).parent / "content_audit_report.json"
CANON_PATH          = Path(__file__).parent.parent / "app" / "data" / "curriculum_canon.json"
RATE_LIMIT_SECONDS  = 2.0   # gap between API calls — be gentle on prod
QUESTIONS_PER_TOPIC = 3

# ---------------------------------------------------------------------------
# Topic matrix — matches WorksheetGenerator.tsx exactly
# Classes 1-2 Science sent as "EVS" to match backend subject guard
# ---------------------------------------------------------------------------

MATHS_TOPICS: dict[int, list[str]] = {
    1: [
        "Numbers 1 to 50 (Class 1)", "Numbers 51 to 100 (Class 1)",
        "Addition up to 20 (Class 1)", "Subtraction within 20 (Class 1)",
        "Basic Shapes (Class 1)", "Spatial sense (in/out, near/far) (Class 1)",
        "Measurement (Class 1)", "Time (Class 1)", "Money (Class 1)",
    ],
    2: [
        "Numbers up to 1000 (Class 2)", "Addition (2-digit with carry)",
        "Subtraction (2-digit with borrow)", "Multiplication (tables 2-5)",
        "Division (sharing equally)", "Shapes and space (2D)",
        "Measurement (length, weight)", "Time (hour, half-hour)",
        "Money (coins and notes)", "Data handling (pictographs)",
    ],
    3: [
        "Addition (carries)", "Subtraction (borrowing)",
        "Addition and subtraction (3-digit)", "Multiplication (tables 2-10)",
        "Division basics", "Numbers up to 10000",
        "Fractions (halves, quarters)", "Fractions",
        "Time (reading clock, calendar)", "Money (bills and change)",
        "Symmetry", "Patterns and sequences",
    ],
    4: [
        "Large numbers (up to 1,00,000)", "Addition and subtraction (5-digit)",
        "Multiplication (3-digit × 2-digit)", "Division (long division)",
        "Fractions (equivalent, comparison)", "Decimals (tenths, hundredths)",
        "Geometry (angles, lines)", "Perimeter and area",
        "Time (minutes, 24-hour clock)", "Money (bills, profit/loss)",
    ],
    5: [
        "Numbers up to 10 lakh (Class 5)", "Factors and multiples (Class 5)",
        "HCF and LCM (Class 5)", "Fractions (add and subtract) (Class 5)",
        "Decimals (all operations) (Class 5)", "Percentage (Class 5)",
        "Area and volume (Class 5)", "Geometry (circles, symmetry) (Class 5)",
        "Data handling (pie charts) (Class 5)", "Speed distance time (Class 5)",
    ],
}

ENGLISH_TOPICS: dict[int, list[str]] = {
    1: [
        "Alphabet (Class 1)", "Phonics (Class 1)",
        "Self and Family Vocabulary (Class 1)", "Animals and Food Vocabulary (Class 1)",
        "Greetings and Polite Words (Class 1)", "Seasons (Class 1)",
        "Simple Sentences (Class 1)",
    ],
    2: [
        "Nouns (Class 2)", "Verbs (Class 2)", "Pronouns (Class 2)",
        "Sentences (Class 2)", "Rhyming Words (Class 2)", "Punctuation (Class 2)",
    ],
    3: [
        "Nouns (Class 3)", "Verbs (Class 3)", "Adjectives (Class 3)",
        "Pronouns (Class 3)", "Tenses (Class 3)", "Punctuation (Class 3)",
        "Vocabulary (Class 3)", "Reading Comprehension (Class 3)",
    ],
    4: [
        "Tenses (Class 4)", "Sentence Types (Class 4)", "Conjunctions (Class 4)",
        "Prepositions (Class 4)", "Adverbs (Class 4)",
        "Prefixes and Suffixes (Class 4)", "Vocabulary (Class 4)",
        "Reading Comprehension (Class 4)",
    ],
    5: [
        "Active and Passive Voice (Class 5)", "Direct and Indirect Speech (Class 5)",
        "Complex Sentences (Class 5)", "Summary Writing (Class 5)",
        "Comprehension (Class 5)", "Synonyms and Antonyms (Class 5)",
        "Formal Letter Writing (Class 5)", "Creative Writing (Class 5)",
        "Clauses (Class 5)",
    ],
}

# EVS = Classes 1-2, Science = Classes 3-5
EVS_TOPICS: dict[int, list[str]] = {
    1: [
        "My Family (Class 1)", "My Body (Class 1)", "Plants Around Us (Class 1)",
        "Animals Around Us (Class 1)", "Food We Eat (Class 1)",
        "Seasons and Weather (Class 1)",
    ],
    2: [
        "Plants (Class 2)", "Animals and Habitats (Class 2)",
        "Food and Nutrition (Class 2)", "Water (Class 2)",
        "Shelter (Class 2)", "Our Senses (Class 2)",
    ],
}

SCIENCE_TOPICS: dict[int, list[str]] = {
    3: [
        "Plants (Class 3)", "Animals (Class 3)", "Food and Nutrition (Class 3)",
        "Shelter (Class 3)", "Water (Class 3)", "Air (Class 3)", "Our Body (Class 3)",
    ],
    4: [
        "Living Things (Class 4)", "Human Body (Class 4)",
        "States of Matter (Class 4)", "Force and Motion (Class 4)",
        "Simple Machines (Class 4)", "Photosynthesis (Class 4)",
        "Animal Adaptation (Class 4)",
    ],
    5: [
        "Circulatory System (Class 5)", "Respiratory and Nervous System (Class 5)",
        "Reproduction in Plants and Animals (Class 5)",
        "Physical and Chemical Changes (Class 5)", "Forms of Energy (Class 5)",
        "Solar System and Earth (Class 5)", "Ecosystem and Food Chains (Class 5)",
    ],
}

HINDI_TOPICS: dict[int, list[str]] = {
    1: [
        "Varnamala Swar (Class 1)", "Varnamala Vyanjan (Class 1)",
        "Family Words (Class 1)", "Simple Sentences in Hindi (Class 1)",
    ],
    2: [
        "Matras Introduction (Class 2)", "Two Letter Words (Class 2)",
        "Three Letter Words (Class 2)", "Rhymes and Poems (Class 2)",
        "Nature Vocabulary (Class 2)",
    ],
    3: [
        "Varnamala (Class 3)", "Matras (Class 3)", "Shabd Rachna (Class 3)",
        "Vakya Rachna (Class 3)", "Kahani Lekhan (Class 3)",
    ],
    4: [
        "Anusvaar and Visarg (Class 4)", "Vachan and Ling (Class 4)",
        "Kaal (Class 4)", "Patra Lekhan (Class 4)", "Comprehension Hindi (Class 4)",
    ],
    5: [
        "Muhavare (Class 5)", "Paryayvachi Shabd (Class 5)",
        "Vilom Shabd (Class 5)", "Samas (Class 5)", "Samvad Lekhan (Class 5)",
    ],
}

COMPUTER_TOPICS: dict[int, list[str]] = {
    1: ["Parts of Computer (Class 1)", "Using Mouse and Keyboard (Class 1)"],
    2: ["Desktop and Icons (Class 2)", "Basic Typing (Class 2)", "Special Keys (Class 2)"],
    3: ["MS Paint Basics (Class 3)", "Keyboard Shortcuts (Class 3)", "Files and Folders (Class 3)"],
    4: ["MS Word Basics (Class 4)", "Introduction to Scratch (Class 4)", "Internet Safety (Class 4)"],
    5: ["Scratch Programming (Class 5)", "Internet Basics (Class 5)", "MS PowerPoint Basics (Class 5)", "Digital Citizenship (Class 5)"],
}

GK_TOPICS: dict[int, list[str]] = {
    3: ["Famous Landmarks (Class 3)", "National Symbols (Class 3)", "Solar System Basics (Class 3)", "Current Awareness (Class 3)"],
    4: ["Continents and Oceans (Class 4)", "Famous Scientists (Class 4)", "Festivals of India (Class 4)", "Sports and Games (Class 4)"],
    5: ["Indian Constitution (Class 5)", "World Heritage Sites (Class 5)", "Space Missions (Class 5)", "Environmental Awareness (Class 5)"],
}

MORAL_TOPICS: dict[int, list[str]] = {
    1: ["Sharing (Class 1)", "Honesty (Class 1)"],
    2: ["Kindness (Class 2)", "Respecting Elders (Class 2)"],
    3: ["Teamwork (Class 3)", "Empathy (Class 3)", "Environmental Care (Class 3)"],
    4: ["Leadership (Class 4)"],
    5: ["Global Citizenship (Class 5)", "Digital Ethics (Class 5)"],
}

HEALTH_TOPICS: dict[int, list[str]] = {
    1: ["Personal Hygiene (Class 1)", "Good Posture (Class 1)", "Basic Physical Activities (Class 1)"],
    2: ["Healthy Eating Habits (Class 2)", "Outdoor Play (Class 2)", "Basic Stretching (Class 2)"],
    3: ["Balanced Diet (Class 3)", "Team Sports Rules (Class 3)", "Safety at Play (Class 3)"],
    4: ["First Aid Basics (Class 4)", "Yoga Introduction (Class 4)", "Importance of Sleep (Class 4)"],
    5: ["Fitness and Stamina (Class 5)", "Nutrition Labels Reading (Class 5)", "Mental Health Awareness (Class 5)"],
}

# Build flat TOPICS list
TOPICS: list[dict] = []
for _subject, _grade_map in [
    ("Maths",         MATHS_TOPICS),
    ("English",       ENGLISH_TOPICS),
    ("EVS",           EVS_TOPICS),       # Classes 1-2 only
    ("Science",       SCIENCE_TOPICS),   # Classes 3-5 only
    ("Hindi",         HINDI_TOPICS),
    ("Computer",      COMPUTER_TOPICS),
    ("GK",            GK_TOPICS),
    ("Moral Science", MORAL_TOPICS),
    ("Health",        HEALTH_TOPICS),
]:
    for _grade_num, _topic_list in sorted(_grade_map.items()):
        for _topic in _topic_list:
            TOPICS.append({
                "subject":   _subject,
                "grade":     f"Class {_grade_num}",
                "grade_num": _grade_num,
                "topic":     _topic,
            })

# ---------------------------------------------------------------------------
# Grade-prohibited vocabulary
# ---------------------------------------------------------------------------

GRADE_PROHIBITED: dict[int, list[str]] = {
    1: [
        "population", "estimate", "approximately", "equivalent",
        "perpendicular", "parallel", "denominator", "numerator",
        "hypothesis", "analysis", "calculate", "evaluate",
    ],
    2: [
        "population", "perpendicular", "hypothesis", "denominator", "numerator",
        "equivalent fraction", "prime", "HCF", "LCM",
    ],
}

# ---------------------------------------------------------------------------
# CHECK 1 — Subject contamination
# ---------------------------------------------------------------------------

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_PURE_ARITH_RE = re.compile(r"^\s*what is \d+\s*[+\-]\s*\d+", re.IGNORECASE)
_NUM_ESTIM_RE  = re.compile(r"estimate.*between \d+ and \d+", re.IGNORECASE)
_FRACTION_RE   = re.compile(r"\d+/\d+")


def check_subject_contamination(q_text: str, subject: str, topic: str) -> list[str]:
    issues: list[str] = []
    text_lower = q_text.lower()

    if subject in ("EVS", "Science"):
        if _PURE_ARITH_RE.search(text_lower):
            issues.append(f"SUBJECT_CONTAMINATION: Pure arithmetic in {subject} question")
        if _NUM_ESTIM_RE.search(text_lower):
            issues.append(f"SUBJECT_CONTAMINATION: Numerical estimation in {subject} question")

    if subject == "Maths" and "fraction" in topic.lower():
        has_fraction = bool(_FRACTION_RE.search(q_text))
        has_word = any(w in text_lower for w in (
            "fraction", "half", "quarter", "third", "numerator", "denominator"))
        if not has_fraction and not has_word:
            issues.append(f"TOPIC_DRIFT: No fraction content in Fractions question: {q_text[:80]}")

    if subject == "Hindi":
        if not _DEVANAGARI_RE.search(q_text):
            issues.append("HINDI_NO_DEVANAGARI: Hindi question has no Devanagari script")

    if subject == "English":
        if _DEVANAGARI_RE.search(q_text):
            issues.append("SUBJECT_CONTAMINATION: Devanagari in English question")

    return issues


# ---------------------------------------------------------------------------
# CHECK 2 — Grade-level vocabulary
# ---------------------------------------------------------------------------

def check_grade_vocabulary(q_text: str, grade_num: int) -> list[str]:
    issues: list[str] = []
    text_lower = q_text.lower()
    for word in GRADE_PROHIBITED.get(grade_num, []):
        if word in text_lower:
            issues.append(f"GRADE_VOCAB: '{word}' too advanced for Class {grade_num}")
    return issues


# ---------------------------------------------------------------------------
# CHECK 3 — Answer key integrity (Maths only)
# ---------------------------------------------------------------------------

_ARITH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([+\-×÷*/])\s*(\d+(?:\.\d+)?)")


def _safe_compute(expr: str):
    """Evaluate a single arithmetic expression. Returns None if too complex."""
    expr = expr.replace("×", "*").replace("÷", "/")
    m = _ARITH_RE.search(expr)
    if not m:
        return None
    a, op_sym, b = float(m.group(1)), m.group(2), float(m.group(3))
    ops = {"+": operator.add, "-": operator.sub, "*": operator.mul}
    if op_sym == "/" and b == 0:
        return None
    result = (a / b) if op_sym == "/" else ops[op_sym](a, b)
    return int(result) if result == int(result) else round(result, 4)


# Question patterns that cannot be validated by simple regex — skip these
_SKIP_VALIDATION_RE = re.compile(
    r"which is (greater|larger|smaller|less|more)|"
    r"explain your reasoning|"
    r"estimate|round(ed|ing)?|"
    r"wrote.*answer|student.*(calculated|got|wrote)|"
    r"closer to|more or less|what mistake|"
    r"is (the answer|it) more|simplified|"
    r"equivalent to|who has (more|less)|"
    r"same as|error|mistake|"
    r"\d+/\d+",   # any fraction in question — too complex for regex
    re.IGNORECASE
)

# Only validate this exact simple pattern: "X op Y = ?"
_SIMPLE_ARITH_RE = re.compile(
    r"^\s*(?:what is|find|calculate|solve|work out)?\s*"
    r"(\d+(?:\.\d+)?)\s*([+\-×÷*/])\s*(\d+(?:\.\d+)?)\s*[=?]",
    re.IGNORECASE
)


def check_answer_integrity(q_text: str, answer: str, subject: str) -> list[str]:
    issues: list[str] = []
    if subject != "Maths":
        return issues

    # Skip complex question types the regex cannot handle
    if _SKIP_VALIDATION_RE.search(q_text):
        return []

    # Only validate simple direct-answer questions
    m = _SIMPLE_ARITH_RE.match(q_text.strip())
    if not m:
        return []

    a, op_sym, b = float(m.group(1)), m.group(2), float(m.group(3))
    ops = {"+": operator.add, "-": operator.sub,
           "×": operator.mul, "*": operator.mul,
           "÷": operator.truediv, "/": operator.truediv}
    if op_sym not in ops:
        return []
    if op_sym in ("÷", "/") and b == 0:
        return []

    computed = ops[op_sym](a, b)
    computed = int(computed) if computed == int(computed) else round(computed, 4)

    # Extract answer — must start with digits
    ans_m = re.match(r"[\d.]+", str(answer).strip())
    if ans_m:
        try:
            given = float(ans_m.group())
            if abs(given - computed) > 0.01:
                issues.append(
                    f"WRONG_ANSWER: '{q_text[:60]}' — expected {computed}, got {given}"
                )
        except ValueError:
            pass
    return issues


# ---------------------------------------------------------------------------
# CHECK 4 — Duplicate detection
# ---------------------------------------------------------------------------

_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]")


def _normalise(text: str) -> str:
    return _NON_ALNUM_RE.sub("", text.lower())[:80]


def check_duplicates(questions: list[dict]) -> list[str]:
    issues: list[str] = []
    seen: list[str] = []
    for i, q in enumerate(questions):
        key = _normalise(q.get("question") or q.get("text") or "")
        for j, prev in enumerate(seen):
            a_words = set(key.split())
            b_words = set(prev.split())
            if not a_words:
                continue
            overlap = len(a_words & b_words) / len(a_words | b_words)
            if overlap > 0.7:
                issues.append(f"DUPLICATE: Q{j+1} and Q{i+1} are {int(overlap*100)}% similar")
        seen.append(key)
    return issues


# ---------------------------------------------------------------------------
# CHECK 5 — NCERT topic relevance (uses curriculum_canon.json)
# ---------------------------------------------------------------------------

def _load_canon_index(canon_path: Path) -> dict[tuple, set[str]]:
    """
    Returns {(grade_num, subject_name): set_of_keywords}.
    Handles both JSON formats:
      - Flat array: [{subject, grade, subtopics, ...}, ...]
      - Nested:     {grades: [{grade, subjects: [{name, skills}]}]}
    """
    index: dict[tuple, set[str]] = {}
    if not canon_path.exists():
        return index
    with open(canon_path, encoding="utf-8") as fh:
        canon = json.load(fh)

    if isinstance(canon, list):
        # Flat array format
        for entry in canon:
            grade_num = entry.get("grade")
            subj_name = entry.get("subject", "")
            if not grade_num or not subj_name:
                continue
            key = (grade_num, subj_name)
            if key not in index:
                index[key] = set()
            for sub in entry.get("subtopics", []):
                bare = re.sub(r"\s*\(Class \d\)", "", sub, flags=re.IGNORECASE)
                index[key].update(
                    w.lower() for w in re.split(r"[\s,/()]+", bare) if len(w) > 3
                )
            for field in ("display_name", "topic_slug"):
                val = entry.get(field, "")
                bare = re.sub(r"\s*\(Class \d\)", "", val, flags=re.IGNORECASE)
                index[key].update(
                    w.lower() for w in re.split(r"[\s,/_()]+", bare) if len(w) > 3
                )
    else:
        # Nested {grades: [...]} format
        for grade_entry in canon.get("grades", []):
            grade_num = grade_entry["grade"]
            for subj_entry in grade_entry.get("subjects", []):
                subj_name = subj_entry["name"]
                words: set[str] = set()
                for skill in subj_entry.get("skills", []):
                    bare = re.sub(r"\s*\(Class \d\)", "", skill, flags=re.IGNORECASE)
                    words.update(
                        w.lower() for w in re.split(r"[\s,/()]+", bare) if len(w) > 3
                    )
                index[(grade_num, subj_name)] = words
    return index


def _strip_class_suffix(name: str) -> str:
    return re.sub(r"\s*\(Class \d\)", "", name, flags=re.IGNORECASE).strip()


# Subject-level content signals — broad enough to avoid false positives
_SUBJECT_SIGNALS: dict[str, list[str]] = {
    "Maths":         [r"\d", r"[+\-×÷*/=]", "how many", "calculate", "find",
                      "solve", "near", "far", "inside", "outside", "above", "below",
                      "pattern", "shape", "circle", "square", "triangle", "more", "less"],
    "English":       ["word", "sentence", "letter", "write", "read", "meaning",
                      "plural", "verb", "noun", "tense", "fill", "choose",
                      "passage", "paragraph", "answer", "hello", "please", "thank"],
    "EVS":           ["animal", "plant", "food", "body", "family", "water",
                      "weather", "shelter", "season", "living", "nature",
                      "eye", "ear", "nose", "hand", "part"],
    "Science":       ["plant", "animal", "body", "water", "air", "energy",
                      "force", "matter", "system", "change", "living",
                      "machine", "lever", "pulley", "reproduce", "seed", "flower"],
    "Hindi":         [r"[\u0900-\u097F]"],   # any Devanagari = Hindi content
    "Computer":      ["computer", "keyboard", "mouse", "file", "folder",
                      "click", "type", "screen", "program", "internet",
                      "paint", "draw", "colour", "brush", "scratch", "block"],
    "GK":            ["india", "world", "national", "country", "famous",
                      "capital", "symbol", "sport", "scientist", "landmark"],
    "Moral Science": ["honest", "kind", "respect", "help", "share", "team",
                      "care", "empathy", "leader", "right", "wrong", "value"],
    "Health":        ["health", "body", "food", "exercise", "clean", "hygiene",
                      "sleep", "diet", "fitness", "safe", "yoga", "posture"],
}


def check_topic_relevance(
    questions: list[dict],
    topic_entry: dict,
    canon_index: dict[tuple, set[str]],   # kept for signature compatibility
) -> list[str]:
    """
    Checks for subject-level content signals instead of topic-name keywords.
    Eliminates false positives like looking for 'alphabet' in alphabet questions.
    """
    subject = topic_entry["subject"]
    signals = _SUBJECT_SIGNALS.get(subject)
    if not signals:
        return []

    all_text = " ".join(
        (q.get("question") or q.get("text") or "").lower()
        for q in questions
    ).strip()

    if not all_text:
        return [f"OFF_TOPIC: No question text generated at all"]

    import re as _re
    for signal in signals:
        try:
            if _re.search(signal, all_text):
                return []  # found a subject signal — not off-topic
        except Exception:
            if signal in all_text:
                return []

    return [f"OFF_TOPIC: No {subject} content signals found in generated questions"]


# ---------------------------------------------------------------------------
# API call — matches backend WorksheetRequest schema exactly
# ---------------------------------------------------------------------------

def generate_questions(topic_entry: dict, auth_token: str) -> dict:
    """
    Calls the worksheet generation API.
    Payload matches WorksheetRequest pydantic model:
      grade_level (not grade), difficulty lowercase, no board required.
    Falls back from v1 to legacy endpoint automatically.
    On 422 prints the validation detail to help diagnose schema mismatches.
    """
    payload = {
        "board":         "CBSE",
        "grade_level":   topic_entry["grade"],   # "Class 1" .. "Class 5"
        "subject":       topic_entry["subject"],
        "topic":         topic_entry["topic"],
        "difficulty":    "medium",               # lowercase — backend enum
        "num_questions": QUESTIONS_PER_TOPIC,
        "language":      "English",
    }
    headers = {"Authorization": f"Bearer {auth_token}"}

    for endpoint in ["/api/v1/worksheets/generate", "/api/worksheets/generate"]:
        try:
            r = requests.post(
                f"{PROD_API_BASE}{endpoint}",
                json=payload,
                headers=headers,
                timeout=45,
            )
            if r.status_code == 200:
                return {"status": "ok", "data": r.json()}
            if r.status_code == 404:
                continue   # try legacy endpoint
            if r.status_code == 422:
                # Print full validation error so we can fix the payload if needed
                print(f"\n    ⚠️  422 detail: {r.text[:400]}")
                return {"status": "error", "code": 422, "body": r.text[:400]}
            return {"status": "error", "code": r.status_code, "body": r.text[:200]}
        except requests.exceptions.Timeout:
            return {"status": "exception", "error": "timeout after 45s"}
        except Exception as exc:
            return {"status": "exception", "error": str(exc)}

    return {"status": "error", "code": 404, "body": "Both endpoints returned 404"}


def _extract_questions(worksheet: dict) -> list[dict]:
    """Extract questions list from various API response shapes."""
    return (
        worksheet.get("questions")
        or worksheet.get("worksheet", {}).get("questions")
        or []
    )


# ---------------------------------------------------------------------------
# Main audit loop
# ---------------------------------------------------------------------------

def run_audit(auth_token: str, start_from: int = 0) -> dict:
    canon_index = _load_canon_index(CANON_PATH)

    results: list[dict]  = []
    summary: dict        = defaultdict(int)
    issues_by_type: dict = defaultdict(list)

    topics_to_run_count = len(TOPICS) - start_from
    print(f"PracticeCraft Content Audit — {topics_to_run_count} topics × {QUESTIONS_PER_TOPIC} questions (topics {start_from+1}–{len(TOPICS)})")
    print(f"API: {PROD_API_BASE}")
    print(f"Estimated time: ~{int(topics_to_run_count * RATE_LIMIT_SECONDS / 60) + 1} minutes\n")

    topics_to_run = TOPICS[start_from:]
    for i, topic_entry in enumerate(topics_to_run, start=start_from):
        label = (
            f"{topic_entry['subject']} Class {topic_entry['grade_num']} "
            f"— {topic_entry['topic']}"
        )
        print(f"[{i+1:3d}/{len(TOPICS)}] {label}", end=" ... ", flush=True)

        result = generate_questions(topic_entry, auth_token)

        if result["status"] != "ok":
            detail = str(result)[:300]
            print(f"❌ GENERATION FAILED ({result.get('code', result.get('error', '?'))})")
            summary["generation_failures"] += 1
            issues_by_type["GENERATION_FAILURE"].append({**topic_entry, "detail": detail})
            results.append({**topic_entry, "status": "generation_failed", "issues": []})
            time.sleep(RATE_LIMIT_SECONDS)
            continue

        worksheet     = result["data"]
        questions     = _extract_questions(worksheet)
        topic_issues: list[str] = []

        for q in questions:
            q_text   = q.get("question") or q.get("text") or ""
            q_answer = q.get("correct_answer") or q.get("answer") or ""
            topic_issues += check_subject_contamination(q_text, topic_entry["subject"], topic_entry["topic"])
            topic_issues += check_grade_vocabulary(q_text, topic_entry["grade_num"])
            topic_issues += check_answer_integrity(q_text, q_answer, topic_entry["subject"])

        topic_issues += check_duplicates(questions)
        topic_issues += check_topic_relevance(questions, topic_entry, canon_index)

        if topic_issues:
            print(f"⚠️  {len(topic_issues)} issue(s)")
            summary["topics_with_issues"] += 1
            for issue in topic_issues:
                bug_type = issue.split(":")[0]
                summary[bug_type] += 1
                issues_by_type[bug_type].append({
                    "subject": topic_entry["subject"],
                    "grade":   topic_entry["grade_num"],
                    "topic":   topic_entry["topic"],
                    "detail":  issue,
                })
        else:
            print("✅ clean")
            summary["clean_topics"] += 1

        results.append({
            **topic_entry,
            "status":            "ok",
            "questions_checked": len(questions),
            "issues":            topic_issues,
        })
        time.sleep(RATE_LIMIT_SECONDS)

    # Build report
    issue_keys = [
        "SUBJECT_CONTAMINATION", "TOPIC_DRIFT", "HINDI_NO_DEVANAGARI",
        "GRADE_VOCAB", "WRONG_ANSWER", "DUPLICATE", "OFF_TOPIC", "GENERATION_FAILURE",
    ]
    report = {
        "summary": {
            "total_topics":        len(TOPICS),
            "clean_topics":        summary["clean_topics"],
            "topics_with_issues":  summary["topics_with_issues"],
            "generation_failures": summary["generation_failures"],
            **{k: int(summary.get(k, 0)) for k in issue_keys},
        },
        "issues_by_type": dict(issues_by_type),
        "full_results":   results,
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    # Print summary
    print("\n" + "=" * 60)
    print("CONTENT AUDIT COMPLETE")
    print("=" * 60)
    s = report["summary"]
    print(f"Total topics checked  : {s['total_topics']}")
    print(f"✅ Clean              : {s['clean_topics']}")
    print(f"⚠️  Topics with issues : {s['topics_with_issues']}")
    print(f"❌ Generation failed  : {s['generation_failures']}")
    print()
    print("Issues by type:")
    for k in issue_keys:
        v = s.get(k, 0)
        if v:
            print(f"  {k}: {v}")
    if not any(s.get(k, 0) for k in issue_keys):
        print("  (none — all clean!)")
    print()
    print(f"Full report → {REPORT_PATH}")
    return report


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        print("Usage:")
        print("  python scripts/content_audit.py <token>              # full run")
        print("  python scripts/content_audit.py <token> --start 100  # resume from topic 100")
        print()
        print("Get token from browser console:")
        print("  const key = Object.keys(localStorage).find(k => k.startswith(\'sb-\'));")
        print("  console.log(JSON.parse(localStorage[key]).access_token);")
        sys.exit(1)

    auth_token = sys.argv[1]

    # Parse optional --start N argument
    start_from = 0
    if "--start" in sys.argv:
        idx = sys.argv.index("--start")
        if idx + 1 < len(sys.argv):
            start_from = int(sys.argv[idx + 1]) - 1  # convert to 0-based
            print(f"Resuming from topic {start_from + 1}/{len(TOPICS)}")

    run_audit(auth_token, start_from=start_from)
