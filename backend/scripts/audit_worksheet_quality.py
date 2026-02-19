#!/usr/bin/env python3
"""
PracticeCraft AI — Comprehensive Worksheet Quality Audit v1.0

Checks every UI-exposed topic across all subjects × grades for:
  1. MISSING_PROFILE        — topic not resolvable in TOPIC_PROFILES
  2. SUBJECT_CONTAMINATION  — profile resolves but belongs to wrong subject
  3. GRADE_MISMATCH         — profile skill tags indicate a different grade
  4. MISSING_CURRICULUM_ENTRY — topic absent from curriculum_canon.json
  5. ANSWER_VALIDATOR_GAP   — Maths topic cannot be auto-corrected by QualityReviewer
  6. HINDI_ENCODING_ERROR   — Hindi profile has Devanagari encoding issues
  +  ORPHANED_PROFILE       — profile exists but is not exposed in any UI grade

Usage:
    cd backend && python scripts/audit_worksheet_quality.py
"""

import sys
import json
import re
import unicodedata
from pathlib import Path
from typing import Optional

# ── Path setup ────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.services.slot_engine import (
    get_topic_profile,
    TOPIC_PROFILES,
    _SUBJECT_TO_PROFILE_GROUP,   # noqa: F401 (private but needed for audit)
    _profile_subject_group,       # noqa: F401
)

# ── Paths ──────────────────────────────────────────────────────────────────────
CANON_PATH = BACKEND_DIR / "app" / "data" / "curriculum_canon.json"
REPORT_PATH = SCRIPT_DIR / "audit_report.json"

# ── UI Topic Matrix ────────────────────────────────────────────────────────────
# Exact strings from WorksheetGenerator.tsx (lines 51-171).
# These are the topic names the frontend sends to the API.
UI_TOPIC_MATRIX: dict[str, dict[int, list[str]]] = {
    "Maths": {
        1: [
            "Numbers 1 to 50 (Class 1)", "Numbers 51 to 100 (Class 1)",
            "Addition up to 20 (Class 1)", "Subtraction within 20 (Class 1)",
            "Basic Shapes (Class 1)", "Spatial sense (in/out, near/far) (Class 1)", "Measurement (Class 1)",
            "Time (Class 1)", "Money (Class 1)",
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
    },
    "English": {
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
            "Prepositions (Class 4)", "Adverbs (Class 4)", "Prefixes and Suffixes (Class 4)",
            "Vocabulary (Class 4)", "Reading Comprehension (Class 4)",
        ],
        5: [
            "Active and Passive Voice (Class 5)", "Direct and Indirect Speech (Class 5)",
            "Complex Sentences (Class 5)", "Summary Writing (Class 5)",
            "Comprehension (Class 5)", "Synonyms and Antonyms (Class 5)",
            "Formal Letter Writing (Class 5)", "Creative Writing (Class 5)",
            "Clauses (Class 5)",
        ],
    },
    "Science": {
        # Class 1–2 = EVS in canon/backend, Class 3–5 = Science
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
        3: [
            "Plants (Class 3)", "Animals (Class 3)", "Food and Nutrition (Class 3)",
            "Shelter (Class 3)", "Water (Class 3)", "Air (Class 3)", "Our Body (Class 3)",
        ],
        4: [
            "Living Things (Class 4)", "Human Body (Class 4)", "States of Matter (Class 4)",
            "Force and Motion (Class 4)", "Simple Machines (Class 4)",
            "Photosynthesis (Class 4)", "Animal Adaptation (Class 4)",
        ],
        5: [
            "Circulatory System (Class 5)", "Respiratory and Nervous System (Class 5)",
            "Reproduction in Plants and Animals (Class 5)",
            "Physical and Chemical Changes (Class 5)", "Forms of Energy (Class 5)",
            "Solar System and Earth (Class 5)", "Ecosystem and Food Chains (Class 5)",
        ],
    },
    "Hindi": {
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
    },
    "Computer": {
        1: ["Parts of Computer (Class 1)", "Using Mouse and Keyboard (Class 1)"],
        2: ["Desktop and Icons (Class 2)", "Basic Typing (Class 2)", "Special Keys (Class 2)"],
        3: ["MS Paint Basics (Class 3)", "Keyboard Shortcuts (Class 3)", "Files and Folders (Class 3)"],
        4: ["MS Word Basics (Class 4)", "Introduction to Scratch (Class 4)", "Internet Safety (Class 4)"],
        5: [
            "Scratch Programming (Class 5)", "Internet Basics (Class 5)",
            "MS PowerPoint Basics (Class 5)", "Digital Citizenship (Class 5)",
        ],
    },
    "GK": {
        3: [
            "Famous Landmarks (Class 3)", "National Symbols (Class 3)",
            "Solar System Basics (Class 3)", "Current Awareness (Class 3)",
        ],
        4: [
            "Continents and Oceans (Class 4)", "Famous Scientists (Class 4)",
            "Festivals of India (Class 4)", "Sports and Games (Class 4)",
        ],
        5: [
            "Indian Constitution (Class 5)", "World Heritage Sites (Class 5)",
            "Space Missions (Class 5)", "Environmental Awareness (Class 5)",
        ],
    },
    "Moral Science": {
        1: ["Sharing (Class 1)", "Honesty (Class 1)"],
        2: ["Kindness (Class 2)", "Respecting Elders (Class 2)"],
        3: ["Teamwork (Class 3)", "Empathy (Class 3)", "Environmental Care (Class 3)"],
        4: ["Leadership (Class 4)"],
        5: ["Global Citizenship (Class 5)", "Digital Ethics (Class 5)"],
    },
    "Health": {
        1: [
            "Personal Hygiene (Class 1)", "Good Posture (Class 1)",
            "Basic Physical Activities (Class 1)",
        ],
        2: ["Healthy Eating Habits (Class 2)", "Outdoor Play (Class 2)", "Basic Stretching (Class 2)"],
        3: ["Balanced Diet (Class 3)", "Team Sports Rules (Class 3)", "Safety at Play (Class 3)"],
        4: ["First Aid Basics (Class 4)", "Yoga Introduction (Class 4)", "Importance of Sleep (Class 4)"],
        5: [
            "Fitness and Stamina (Class 5)", "Nutrition Labels Reading (Class 5)",
            "Mental Health Awareness (Class 5)",
        ],
    },
}

# ── Helpers ────────────────────────────────────────────────────────────────────

# What subject string to pass to get_topic_profile per UI subject + grade
def api_subject_for(ui_subject: str, grade: int) -> str:
    """Map UI subject + grade to the string expected by get_topic_profile."""
    if ui_subject == "Science":
        return "EVS" if grade <= 2 else "Science"
    if ui_subject == "Moral Science":
        return "Moral Science"
    return ui_subject


# Grade-digit prefix pattern in skill tags (Maths: c1_, c2_… EVS/Sci: sci_c1_…)
_GRADE_TAG_RE = re.compile(r"(?:sci_)?c(\d)_")

def infer_grade_from_tags(tags: list) -> Optional[int]:
    """Return the grade number from skill-tag prefixes, or None if ambiguous."""
    grades_found = set()
    for tag in tags:
        m = _GRADE_TAG_RE.match(tag)
        if m:
            grades_found.add(int(m.group(1)))
    if len(grades_found) == 1:
        return grades_found.pop()
    return None  # Multiple or no grade markers found


def strip_class_suffix(topic: str) -> str:
    """Remove ' (Class N)' suffix for canon lookup."""
    return re.sub(r"\s*\(Class\s*\d+\)\s*$", "", topic, flags=re.IGNORECASE).strip()


def load_canon_index() -> dict:
    """
    Load curriculum_canon.json and build a lookup:
        {grade: {subject_name: set_of_bare_topic_names}}
    Canon stores bare names (no '(Class N)' suffix).
    """
    if not CANON_PATH.exists():
        print(f"  WARNING: curriculum_canon.json not found at {CANON_PATH}")
        return {}
    with open(CANON_PATH, encoding="utf-8") as f:
        canon = json.load(f)
    index: dict[int, dict[str, set]] = {}
    for grade_entry in canon.get("grades", []):
        grade = grade_entry["grade"]
        index[grade] = {}
        for subj in grade_entry.get("subjects", []):
            name = subj["name"]
            # Normalise to lower for comparison
            index[grade][name.lower()] = {
                strip_class_suffix(s).lower() for s in subj.get("skills", [])
            }
    return index


def topic_in_canon(topic: str, ui_subject: str, grade: int, canon_index: dict) -> bool:
    """
    Return True if the topic (bare name) appears in the canon for this grade/subject.
    Handles EVS vs Science naming.
    """
    bare = strip_class_suffix(topic).lower()
    grade_map = canon_index.get(grade, {})

    # Determine which subject names to search
    subjects_to_check = [ui_subject.lower()]
    if ui_subject == "Science":
        subjects_to_check = ["evs"] if grade <= 2 else ["science", "evs"]
    if ui_subject == "Moral Science":
        subjects_to_check = ["moral science", "moral"]

    for subj_name in subjects_to_check:
        canon_skills = grade_map.get(subj_name, set())
        if bare in canon_skills:
            return True
        # Fuzzy: bare is a substring of a canon skill or vice versa
        for cs in canon_skills:
            if bare in cs or cs in bare:
                return True
    return False


# Arithmetic keywords that make a Maths topic validatable by QualityReviewer
_ARITHMETIC_KEYWORDS = frozenset([
    "addition", "subtraction", "multiplication", "division",
    "number", "fraction", "decimal", "percentage", "hcf", "lcm",
    "factor", "multiple", "money", "time", "measurement", "perimeter",
    "area", "volume", "speed", "distance", "profit", "loss",
])

def is_arithmetic_topic(topic: str) -> bool:
    """Return True if the topic is expected to contain auto-correctable arithmetic."""
    t = topic.lower()
    return any(kw in t for kw in _ARITHMETIC_KEYWORDS)


def check_answer_validator(topic: str, profile: dict) -> Optional[str]:
    """
    For Maths topics expected to have arithmetic: verify the profile allows
    'application' or 'recognition' slot types (the types QualityReviewer audits).
    Returns an issue string or None if OK.
    """
    if not is_arithmetic_topic(topic):
        return None  # Geometry/data topics don't need arithmetic validation
    allowed_slots = set(profile.get("allowed_slot_types", []))
    if not allowed_slots:
        return "Profile has no allowed_slot_types — quality reviewer cannot validate answers"
    if "application" not in allowed_slots and "recognition" not in allowed_slots:
        return (
            f"Arithmetic topic but only allows slots {sorted(allowed_slots)!r}; "
            "application/recognition slots needed for answer auto-correction"
        )
    return None


def check_hindi_encoding(topic: str, profile: dict) -> Optional[str]:
    """
    Check Devanagari content in a Hindi profile.
    Returns an issue description string, or None if OK.
    """
    profile_json = json.dumps(profile, ensure_ascii=False)
    deva_chars = [c for c in profile_json if "\u0900" <= c <= "\u097F"]

    if not deva_chars:
        return (
            "Profile contains no Devanagari (Unicode U+0900–U+097F) sample text — "
            "Hindi generation has no script anchor in the profile"
        )
    # Verify UTF-8 round-trip
    try:
        encoded = profile_json.encode("utf-8")
        decoded = encoded.decode("utf-8")
        assert decoded == profile_json
    except Exception as exc:
        return f"UTF-8 round-trip failed: {exc}"

    # Check NFC normalisation
    for char in deva_chars:
        if unicodedata.normalize("NFC", char) != char:
            return (
                f"Devanagari char U+{ord(char):04X} ('{char}') is not NFC-normalized — "
                "may display incorrectly in PDF"
            )
    return None


# ── Main audit ─────────────────────────────────────────────────────────────────

def run_audit() -> dict:
    print("  Loading curriculum_canon.json …")
    canon_index = load_canon_index()
    print(f"  Canon loaded: {len(canon_index)} grades")

    issues: list[dict] = []
    all_ui_topics: set[str] = set()  # bare topic names in UI (for orphan check)

    # ── Per-topic checks ────────────────────────────────────────────────────────
    print("  Checking UI topics …\n")
    for subject, grade_map in sorted(UI_TOPIC_MATRIX.items()):
        for grade in sorted(grade_map.keys()):
            topics = grade_map[grade]
            api_subj = api_subject_for(subject, grade)

            for topic in topics:
                all_ui_topics.add(topic)

                def add_issue(bug_type: str, detail: str, fix: str) -> None:
                    issues.append({
                        "subject": subject,
                        "grade": grade,
                        "topic": topic,
                        "bug_type": bug_type,
                        "detail": detail,
                        "fix_required": fix,
                    })

                # ── CHECK 1: Profile exists (with subject filter) ─────────────
                profile = get_topic_profile(topic, subject=api_subj)
                if profile is None:
                    profile_unfiltered = get_topic_profile(topic)  # no subject guard

                    if profile_unfiltered is None:
                        add_issue(
                            "MISSING_PROFILE",
                            f"get_topic_profile('{topic}', subject='{api_subj}') "
                            f"and without subject filter both returned None — "
                            "topic does not exist in TOPIC_PROFILES at all.",
                            f"Add a profile for '{topic}' in slot_engine.py TOPIC_PROFILES "
                            f"under {subject} Class {grade}.",
                        )
                        continue  # no profile → skip remaining checks

                    # Profile exists but wrong subject → SUBJECT_CONTAMINATION
                    actual_group = _profile_subject_group(profile_unfiltered)
                    expected_group = _SUBJECT_TO_PROFILE_GROUP.get(api_subj.lower(), "?")
                    sample_tags = profile_unfiltered.get("allowed_skill_tags", [])[:4]
                    add_issue(
                        "SUBJECT_CONTAMINATION",
                        f"Profile exists but subject filter rejects it. "
                        f"Expected group '{expected_group}', "
                        f"profile group is '{actual_group}'. "
                        f"Sample tags: {sample_tags}",
                        f"Fix allowed_skill_tags in '{topic}' profile to use "
                        f"{subject}-appropriate prefixes, OR rename the profile "
                        f"and create a correct {subject} Class {grade} entry.",
                    )
                    # Skip checks 3–6; the wrong profile would give misleading results
                    continue

                tags = profile.get("allowed_skill_tags", [])

                # ── CHECK 2: Subject tag alignment ───────────────────────────
                actual_group = _profile_subject_group(profile)
                expected_group = _SUBJECT_TO_PROFILE_GROUP.get(api_subj.lower(), "?")
                if expected_group and actual_group != expected_group:
                    add_issue(
                        "SUBJECT_CONTAMINATION",
                        f"Profile passed subject filter but skill tags report group "
                        f"'{actual_group}' (expected '{expected_group}'). "
                        f"Sample tags: {tags[:4]}",
                        f"Correct allowed_skill_tags in '{topic}' profile to use "
                        f"{subject}-appropriate prefixes.",
                    )
                    # Don't skip — tag group mismatch is noteworthy but profile may still be usable

                # ── CHECK 3: Grade tag alignment ─────────────────────────────
                inferred_grade = infer_grade_from_tags(tags)
                if inferred_grade is not None and inferred_grade != grade:
                    add_issue(
                        "GRADE_MISMATCH",
                        f"Skill tags infer Class {inferred_grade} "
                        f"but topic is in Class {grade} UI list. "
                        f"Sample tags: {tags[:4]}",
                        f"Fix allowed_skill_tags in '{topic}' profile to use "
                        f"Class {grade} grade prefix (e.g. c{grade}_ or sci_c{grade}_).",
                    )

                # ── CHECK 4: Curriculum canon coverage ───────────────────────
                if not topic_in_canon(topic, subject, grade, canon_index):
                    add_issue(
                        "MISSING_CURRICULUM_ENTRY",
                        f"'{strip_class_suffix(topic)}' not found in curriculum_canon.json "
                        f"for Grade {grade} {subject} (or EVS). "
                        f"Topic Intelligence Agent cannot ground prompts for this topic.",
                        f"Run `python backend/scripts/sync_curriculum.py` "
                        f"or manually add '{strip_class_suffix(topic)}' to "
                        f"curriculum_canon.json Grade {grade} {subject}.",
                    )

                # ── CHECK 5: Maths answer validator ──────────────────────────
                if subject == "Maths":
                    validator_issue = check_answer_validator(topic, profile)
                    if validator_issue:
                        add_issue(
                            "ANSWER_VALIDATOR_GAP",
                            validator_issue,
                            f"Ensure '{topic}' profile includes 'application' or "
                            "'recognition' in allowed_slot_types so QualityReviewer "
                            "can auto-correct arithmetic answers.",
                        )

                # ── CHECK 6: Hindi encoding ──────────────────────────────────
                if subject == "Hindi":
                    enc_issue = check_hindi_encoding(topic, profile)
                    if enc_issue:
                        add_issue(
                            "HINDI_ENCODING_ERROR",
                            enc_issue,
                            f"Add Devanagari script sample text to the '{topic}' profile "
                            "in TOPIC_PROFILES, or fix the UTF-8/NFC encoding issue.",
                        )

    # ── Orphaned profiles ───────────────────────────────────────────────────────
    print("  Checking for orphaned profiles (in TOPIC_PROFILES but not in UI) …")
    for profile_key in sorted(TOPIC_PROFILES.keys()):
        if profile_key in all_ui_topics:
            continue
        # Fuzzy: check if key is a substring match with any UI topic
        bare_key = strip_class_suffix(profile_key).lower()
        fuzzy_match = any(
            bare_key in strip_class_suffix(t).lower()
            or strip_class_suffix(t).lower() in bare_key
            for t in all_ui_topics
        )
        if not fuzzy_match:
            p = TOPIC_PROFILES[profile_key]
            actual_group = _profile_subject_group(p)
            inferred_grade = infer_grade_from_tags(p.get("allowed_skill_tags", []))
            issues.append({
                "subject": actual_group or "Unknown",
                "grade": inferred_grade or 0,
                "topic": profile_key,
                "bug_type": "ORPHANED_PROFILE",
                "detail": (
                    f"Profile exists in TOPIC_PROFILES (group='{actual_group}', "
                    f"inferred grade={inferred_grade}) "
                    "but is not exposed in any UI grade list."
                ),
                "fix_required": (
                    f"Either add '{profile_key}' to the appropriate "
                    "WorksheetGenerator.tsx grade list, or remove the orphaned profile."
                ),
            })

    # ── Tally ───────────────────────────────────────────────────────────────────
    total_topics = sum(
        len(topics)
        for grade_map in UI_TOPIC_MATRIX.values()
        for topics in grade_map.values()
    )
    total_profiles = len(TOPIC_PROFILES)

    bug_keys = {
        "MISSING_PROFILE": "missing_profiles",
        "SUBJECT_CONTAMINATION": "subject_contaminations",
        "GRADE_MISMATCH": "grade_mismatches",
        "MISSING_CURRICULUM_ENTRY": "missing_curriculum_entries",
        "ANSWER_VALIDATOR_GAP": "answer_validator_gaps",
        "HINDI_ENCODING_ERROR": "hindi_encoding_errors",
        "ORPHANED_PROFILE": "orphaned_profiles",
    }
    counts: dict[str, int] = {v: 0 for v in bug_keys.values()}
    for issue in issues:
        key = bug_keys.get(issue["bug_type"])
        if key:
            counts[key] += 1

    topics_with_issues = len(set(
        (i["subject"], i["grade"], i["topic"])
        for i in issues
        if i["bug_type"] != "ORPHANED_PROFILE"
    ))
    clean_topics = total_topics - topics_with_issues

    report = {
        "summary": {
            "total_ui_topics_checked": total_topics,
            "total_profile_keys_in_slot_engine": total_profiles,
            "clean_topics": clean_topics,
            **counts,
        },
        "issues": issues,
    }
    return report


def print_report(report: dict) -> None:
    s = report["summary"]
    issues = report["issues"]

    SEP = "=" * 60
    print(f"\n{SEP}")
    print("=== PRACTICECRAFT QUALITY AUDIT ===")
    print(SEP)
    print(f"Total UI topics checked              : {s['total_ui_topics_checked']}")
    print(f"Total TOPIC_PROFILES keys            : {s['total_profile_keys_in_slot_engine']}")
    print(f"✅ Clean (no issues)                 : {s['clean_topics']}")
    print(f"❌ Missing profiles                  : {s['missing_profiles']}")
    print(f"❌ Subject contamination             : {s['subject_contaminations']}")
    print(f"❌ Grade mismatches                  : {s['grade_mismatches']}")
    print(f"❌ Missing curriculum entries        : {s['missing_curriculum_entries']}")
    print(f"❌ Answer validator gaps             : {s['answer_validator_gaps']}")
    print(f"❌ Hindi encoding errors             : {s['hindi_encoding_errors']}")
    print(f"⚠️  Orphaned profiles (not in UI)    : {s['orphaned_profiles']}")

    # Priority order for display
    priority = {
        "MISSING_PROFILE": 1,
        "SUBJECT_CONTAMINATION": 2,
        "GRADE_MISMATCH": 3,
        "ANSWER_VALIDATOR_GAP": 4,
        "HINDI_ENCODING_ERROR": 5,
        "MISSING_CURRICULUM_ENTRY": 6,
        "ORPHANED_PROFILE": 7,
    }

    # Top non-orphan issues
    top = [i for i in issues if i["bug_type"] != "ORPHANED_PROFILE"]
    top.sort(key=lambda x: (priority.get(x["bug_type"], 9), x["subject"], x["grade"], x["topic"]))

    if top:
        print(f"\nTOP ISSUES TO FIX ({len(top)} total):")
        for idx, issue in enumerate(top[:30], 1):
            print(
                f"\n{idx:2d}. [{issue['bug_type']}] "
                f"{issue['subject']} Class {issue['grade']} — '{issue['topic']}'"
            )
            print(f"    DETAIL : {issue['detail']}")
            print(f"    FIX    : {issue['fix_required']}")
        if len(top) > 30:
            print(f"\n    … and {len(top) - 30} more issues (see audit_report.json)")
    else:
        print("\n✅ No critical issues found!")

    # Orphaned profiles section
    orphans = [i for i in issues if i["bug_type"] == "ORPHANED_PROFILE"]
    if orphans:
        print(f"\n{'─'*60}")
        print(f"⚠️  ORPHANED PROFILES — in TOPIC_PROFILES but NOT in UI ({len(orphans)}):")
        for o in orphans:
            g = f"Class {o['grade']}" if o["grade"] else "unknown grade"
            print(f"   • '{o['topic']}' — {o['subject']}, {g}")


def main() -> None:
    print("PracticeCraft AI — Quality Audit v1.0")
    print("=" * 60)
    report = run_audit()

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n  Full JSON report saved → {REPORT_PATH}")

    print_report(report)


if __name__ == "__main__":
    main()
