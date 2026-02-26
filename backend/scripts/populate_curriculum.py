"""
One-time script to populate the curriculum_content table.

Usage:
    cd backend
    python scripts/populate_curriculum.py

Takes ~30-60 minutes (198 topics x ~10 seconds each).
Costs approximately Rs 50-100 in Gemini API credits.
"""
import json
import os
import sys
import time

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
from app.core.deps import get_supabase_client
from app.data.learning_objectives import LEARNING_OBJECTIVES
from app.data.topic_profiles import TOPIC_PROFILES

settings = get_settings()


POPULATION_PROMPT = """You are a CBSE curriculum expert. Generate comprehensive curriculum content for the following topic.

Grade: {grade}
Subject: {subject}
Topic: {topic}
Existing learning objectives: {learning_objectives}

Generate a JSON object with these fields:

{{
    "chapter_name": "Chapter X: [chapter name as it appears in NCERT textbook]",
    "ncert_summary": "[2-3 paragraphs describing what this chapter teaches in the NCERT textbook. Be specific about concepts, methods, and skills covered. Reference NCERT Class {grade_num} {subject} textbook.]",
    "key_concepts": ["concept1", "concept2", ...],
    "learning_outcomes": ["Student can...", "Student can...", ...],
    "common_mistakes": ["Mistake 1: description", "Mistake 2: description", ...],
    "difficulty_notes": {{
        "foundation": "What a foundation-level question looks like for this topic",
        "application": "What an application-level question looks like",
        "stretch": "What a stretch/challenge question looks like"
    }},
    "grade_vocabulary": ["word1", "word2", ...],
    "question_types": ["mcq", "fill_blank", "word_problem", "true_false", "short_answer"],
    "real_world_contexts": ["context1 using Indian names and settings", "context2", ...]
}}

IMPORTANT:
- Content must be appropriate for CBSE {grade} level
- Use Indian contexts (names like Aarav, Priya, Meera; Rs for money; Indian festivals, places)
- Be specific to NCERT textbook content, not generic
- Learning outcomes should be measurable ("can add unlike fractions", not "understands fractions")
- Common mistakes should be specific to this grade level
- Real world contexts should be relatable to Indian students of this age
"""

# Subject inference keywords
ENGLISH_KEYWORDS = [
    "grammar", "noun", "verb", "adjective", "pronoun", "tense",
    "sentence", "paragraph", "comprehension", "vocabulary", "writing",
    "poem", "story", "letter", "essay", "punctuation", "preposition",
    "conjunction", "article", "composition",
]
HINDI_KEYWORDS = [
    "hindi", "vyakaran", "matra", "shabd", "vakya", "varnamala",
]
EVS_KEYWORDS = [
    "plant", "animal", "body", "food", "water", "shelter", "weather",
    "earth", "environment", "family", "transport", "festival",
    "health", "hygiene", "air", "soil", "habitat",
]
SCIENCE_KEYWORDS = [
    "science", "force", "energy", "material", "magnet", "light",
    "sound", "electricity", "simple machine",
]
GK_KEYWORDS = ["general knowledge", "gk", "landmark", "symbol", "famous"]
COMPUTER_KEYWORDS = ["computer", "keyboard", "mouse", "software", "hardware"]
MORAL_KEYWORDS = ["moral", "value", "honesty", "kindness", "respect"]
HEALTH_KEYWORDS = ["health", "hygiene", "nutrition", "exercise", "safety"]


def infer_subject(topic: str) -> str:
    """Infer subject from topic name."""
    t_lower = topic.lower()
    if any(k in t_lower for k in ENGLISH_KEYWORDS):
        return "English"
    if any(k in t_lower for k in HINDI_KEYWORDS):
        return "Hindi"
    if any(k in t_lower for k in SCIENCE_KEYWORDS):
        return "Science"
    if any(k in t_lower for k in EVS_KEYWORDS):
        return "EVS"
    if any(k in t_lower for k in GK_KEYWORDS):
        return "GK"
    if any(k in t_lower for k in COMPUTER_KEYWORDS):
        return "Computer"
    if any(k in t_lower for k in MORAL_KEYWORDS):
        return "Moral Science"
    if any(k in t_lower for k in HEALTH_KEYWORDS):
        return "Health"
    return "Maths"


def populate_topic(sb, ai_client, grade: str, subject: str, topic: str, lo: list[str]) -> bool:
    """Generate and store curriculum content for one topic."""
    grade_num = grade.replace("Class ", "")

    prompt = POPULATION_PROMPT.format(
        grade=grade,
        grade_num=grade_num,
        subject=subject,
        topic=topic,
        learning_objectives=json.dumps(lo),
    )

    try:
        result = ai_client.generate_json(
            prompt=prompt,
            temperature=0.3,
            max_tokens=4096,
        )

        # Upsert into Supabase
        sb.table("curriculum_content").upsert({
            "grade": grade,
            "subject": subject,
            "topic": topic,
            "chapter_name": result.get("chapter_name", ""),
            "ncert_summary": result.get("ncert_summary", ""),
            "key_concepts": result.get("key_concepts", []),
            "learning_outcomes": result.get("learning_outcomes", []),
            "common_mistakes": result.get("common_mistakes", []),
            "difficulty_notes": result.get("difficulty_notes", {}),
            "grade_vocabulary": result.get("grade_vocabulary", []),
            "question_types": result.get("question_types", []),
            "real_world_contexts": result.get("real_world_contexts", []),
        }, on_conflict="grade,subject,topic").execute()

        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def main():
    from app.services.ai_client import get_ai_client

    sb = get_supabase_client()
    ai = get_ai_client()

    topics = list(TOPIC_PROFILES.keys())
    total = 0
    success = 0
    failed = 0

    print(f"Populating curriculum content for {len(topics)} topics...")
    print(f"Estimated time: ~{len(topics) * 10 / 60:.0f} minutes")
    print()

    for i, topic in enumerate(topics):
        subject = infer_subject(topic)
        lo = LEARNING_OBJECTIVES.get(topic, [])

        # Generate for Class 3 as the baseline
        grade = "Class 3"
        total += 1

        print(f"[{i+1}/{len(topics)}] {grade} | {subject} | {topic}...", end=" ", flush=True)

        ok = populate_topic(sb, ai, grade, subject, topic, lo)
        if ok:
            success += 1
            print("OK")
        else:
            failed += 1

        # Rate limit
        time.sleep(1)

    print(f"\n{'='*60}")
    print(f"Done! {success}/{total} topics populated ({failed} failed)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
