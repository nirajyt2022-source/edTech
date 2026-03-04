#!/usr/bin/env python3
"""
Populate curriculum_content table with NCERT-aligned data for all 208 topics.

Uses Gemini API to generate curriculum-accurate data for each topic.
Skips topics that already have enriched data (non-skeleton rows).
Run once, then the curriculum.py RAG service will serve this data to the
worksheet generator.

Usage:
    cd backend
    python scripts/populate_curriculum.py

    # Force re-enrich ALL topics:
    python scripts/populate_curriculum.py --force

Requires:
    SUPABASE_URL and SUPABASE_SERVICE_KEY in environment
    GEMINI_API_KEY (or OPENAI_API_KEY) in environment
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CANON_PATH = Path(__file__).parent.parent / "app" / "data" / "curriculum_canon.json"
with open(CANON_PATH) as f:
    CANON = json.load(f)


def get_supabase():
    """Get Supabase client with service key."""
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    return create_client(url, key)


def get_llm_client():
    """Get the OpenAI-compatible LLM client (same as the worksheet pipeline uses)."""
    from app.services.ai_client import get_openai_compat_client

    return get_openai_compat_client()


def get_existing_objectives():
    """Load existing learning objectives for enrichment."""
    try:
        from app.data.learning_objectives import LEARNING_OBJECTIVES

        return LEARNING_OBJECTIVES
    except ImportError:
        return {}


def generate_curriculum_data(client, grade: int, subject: str, topic: str, existing_objectives: list) -> dict:
    """Use Gemini to generate NCERT-aligned curriculum data for one topic."""

    objectives_context = ""
    if existing_objectives:
        objectives_context = (
            f"\nExisting learning objectives for this topic: "
            f"{json.dumps(existing_objectives, ensure_ascii=False)}"
        )

    prompt = f"""You are an expert on NCERT/CBSE curriculum for Indian primary schools (Class 1-5).

Generate accurate curriculum data for this topic:
- Grade: Class {grade}
- Subject: {subject}
- Topic: {topic}
{objectives_context}

Return ONLY a JSON object (no markdown, no explanation) with these fields:

{{
    "chapter_name": "The NCERT textbook chapter name that covers this topic. Use the actual NCERT book name. For Maths Class 1: 'Math-Magic'. For EVS Class 3-5: 'Looking Around'. For English: 'Marigold'. For Hindi: 'Rimjhim'. Format: 'Book Name — Chapter X: Chapter Title' or just the chapter name if unsure of the number.",

    "ncert_summary": "1-2 sentences describing what this chapter/topic teaches, using age-appropriate language for Class {grade}. Be specific to NCERT content, not generic.",

    "key_concepts": ["List of 4-6 key concepts taught in this topic. Be specific. Example for Class 3 Fractions: 'Half means 2 equal parts', 'Quarter means 4 equal parts', 'Fraction as part of a whole'"],

    "learning_outcomes": ["3-4 NCERT-aligned learning outcomes. Start with action verbs. Example: 'Identify halves and quarters of shapes', 'Write fractions for shaded parts of figures', 'Compare unit fractions using pictures'"],

    "common_mistakes": ["3-4 mistakes students commonly make. Be specific. Example: 'Thinks 1/3 is bigger than 1/2 because 3 > 2', 'Confuses numerator and denominator', 'Forgets that parts must be EQUAL for fractions'"],

    "difficulty_notes": {{
        "foundation": "What a struggling student should focus on first. Example: 'Start with halves of everyday objects (roti, apple) before moving to written fractions'",
        "stretch": "What an advanced student can try. Example: 'Compare fractions with different denominators using paper folding'"
    }},

    "grade_vocabulary": ["10-15 words that Class {grade} students should know for this topic. ONLY age-appropriate vocabulary. For Class 1-2: simple words. For Class 3-4: curriculum terms. NEVER include terms from higher grades."],

    "real_world_contexts": ["5-6 real-world Indian contexts where this topic applies. Example for money: 'Buying vegetables at sabzi mandi', 'Counting coins in a piggy bank', 'Sharing pocket money with siblings'"],

    "question_types": ["4-5 question types suitable for this topic. Example: 'MCQ identification', 'Fill in the blank computation', 'Word problem with story context', 'Error detection (spot the mistake)', 'Draw/shade to represent'"]
}}

IMPORTANT:
- Use NCERT-specific terminology and examples, not generic educational content.
- For Hindi topics, write key_concepts, vocabulary etc. in Devanagari script.
- For Class 1-2, keep everything very simple — these are 6-7 year olds.
- For Science/EVS, use the vocabulary from the ACTUAL NCERT textbook for that class.
- grade_vocabulary must NOT include terms from higher grades (e.g., don't use "photosynthesis" for Class 3)."""

    response = client.chat.completions.create(
        model="gemini-2.5-flash",
        messages=[
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=2000,
    )

    text = response.choices[0].message.content or ""
    text = text.strip()

    # Strip markdown fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    text = text.strip()

    return json.loads(text)


def _is_skeleton_row(row: dict) -> bool:
    """Check if a row is a skeleton (not enriched)."""
    summary = row.get("ncert_summary", "")
    return "Skeleton row" in summary or not row.get("common_mistakes")


def populate(force: bool = False):
    """Main function: generate and upsert curriculum data for all topics."""
    client = get_llm_client()
    sb = get_supabase()
    existing_objs = get_existing_objectives()

    total = 0
    success = 0
    skipped = 0
    failed = []

    for grade_data in CANON["grades"]:
        grade_num = grade_data["grade"]
        grade_str = f"Class {grade_num}"

        for subject_data in grade_data["subjects"]:
            subject = subject_data["name"]
            topics = subject_data.get("skills", [])

            for topic_entry in topics:
                topic = topic_entry.get("name", topic_entry) if isinstance(topic_entry, dict) else topic_entry
                total += 1

                # Check if already exists and is enriched
                existing = (
                    sb.table("curriculum_content")
                    .select("id,ncert_summary,common_mistakes")
                    .eq("grade", grade_str)
                    .eq("subject", subject)
                    .eq("topic", topic)
                    .maybe_single()
                    .execute()
                )
                if existing.data and not force and not _is_skeleton_row(existing.data):
                    logger.info("[%d] SKIP (enriched): %s %s %s", total, grade_str, subject, topic)
                    skipped += 1
                    success += 1
                    continue

                # Get existing objectives for this topic
                topic_objs = existing_objs.get(topic, [])
                if not topic_objs:
                    topic_objs = existing_objs.get(f"{topic} ({grade_str})", [])

                logger.info("[%d] Generating: %s %s %s", total, grade_str, subject, topic)

                try:
                    data = generate_curriculum_data(client, grade_num, subject, topic, topic_objs)

                    row = {
                        "grade": grade_str,
                        "subject": subject,
                        "topic": topic,
                        "chapter_name": data.get("chapter_name", ""),
                        "ncert_summary": data.get("ncert_summary", ""),
                        "key_concepts": data.get("key_concepts", []),
                        "learning_outcomes": data.get("learning_outcomes", []),
                        "common_mistakes": data.get("common_mistakes", []),
                        "difficulty_notes": data.get("difficulty_notes", {}),
                        "grade_vocabulary": data.get("grade_vocabulary", []),
                        "real_world_contexts": data.get("real_world_contexts", []),
                        "question_types": data.get("question_types", []),
                    }

                    sb.table("curriculum_content").upsert(
                        row,
                        on_conflict="grade,subject,topic",
                    ).execute()

                    success += 1
                    logger.info(
                        "[%d] OK: %s %s %s — chapter: %s",
                        total,
                        grade_str,
                        subject,
                        topic,
                        data.get("chapter_name", "N/A")[:50],
                    )

                    # Rate limit: ~0.5s between requests
                    time.sleep(0.5)

                except json.JSONDecodeError as e:
                    logger.error("[%d] JSON PARSE ERROR: %s %s %s — %s", total, grade_str, subject, topic, e)
                    failed.append(f"{grade_str} {subject} {topic}")
                except Exception as e:
                    logger.error("[%d] ERROR: %s %s %s — %s", total, grade_str, subject, topic, e)
                    failed.append(f"{grade_str} {subject} {topic}")
                    time.sleep(2.0)  # back off on errors

    logger.info("=== DONE ===")
    logger.info("Total: %d, Success: %d, Skipped: %d, Failed: %d", total, success, skipped, len(failed))
    if failed:
        logger.info("Failed topics:\n%s", "\n".join(f"  - {f}" for f in failed))


if __name__ == "__main__":
    force_flag = "--force" in sys.argv
    populate(force=force_flag)
