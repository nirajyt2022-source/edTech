#!/usr/bin/env python3
"""
Populate the curriculum_content Supabase table with skeleton rows
from curriculum_canon.json.

Creates one row per grade × subject × topic so that curriculum.py
stops returning None.  Enrichment with actual NCERT summaries can
be done later — this script is instant (no LLM calls).

Usage:
    cd backend
    python scripts/populate_curriculum.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure backend/ is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.deps import get_supabase_client


def _load_canon() -> dict:
    path = Path(__file__).parent.parent / "app" / "data" / "curriculum_canon.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _load_chapter_map() -> dict[str, str]:
    path = Path(__file__).parent.parent / "app" / "data" / "ncert_chapter_map.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_learning_objectives() -> dict[str, list[str]]:
    try:
        from app.data.learning_objectives import LEARNING_OBJECTIVES
        return LEARNING_OBJECTIVES
    except Exception:
        return {}


def main() -> None:
    canon = _load_canon()
    chapter_map = _load_chapter_map()
    objectives = _load_learning_objectives()
    sb = get_supabase_client()
    total_inserted = 0

    print("=" * 60)
    print("  Populate curriculum_content — skeleton rows")
    print("=" * 60)
    print()

    for grade_entry in canon.get("grades", []):
        grade_num = grade_entry["grade"]
        grade_str = f"Class {grade_num}"
        rows: list[dict] = []

        for subject_entry in grade_entry.get("subjects", []):
            subject_name = subject_entry["name"]

            for skill in subject_entry.get("skills", []):
                # Lookup chapter name from ncert_chapter_map
                map_key = f"{grade_str}|{subject_name}|{skill}"
                chapter_name = chapter_map.get(map_key)

                # Lookup curated learning outcomes
                learning_outcomes = objectives.get(skill)

                rows.append({
                    "grade": grade_str,
                    "subject": subject_name,
                    "topic": skill,
                    "chapter_name": chapter_name or f"{subject_name}: {skill}",
                    "ncert_summary": f"NCERT {grade_str} {subject_name} — {skill}. Skeleton row, to be enriched.",
                    "key_concepts": [skill],
                    "learning_outcomes": learning_outcomes or [f"Student can demonstrate understanding of {skill}"],
                    "common_mistakes": [],
                    "difficulty_notes": {},
                    "grade_vocabulary": [],
                    "real_world_contexts": [],
                    "question_types": [],
                })

        if not rows:
            print(f"  {grade_str}: no skills found, skipping")
            continue

        # Upsert in batches of 50
        batch_size = 50
        grade_count = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            result = (
                sb.table("curriculum_content")
                .upsert(batch, on_conflict="grade,subject,topic")
                .execute()
            )
            inserted = len(result.data) if result.data else 0
            grade_count += inserted

        total_inserted += grade_count
        print(f"  Inserted {grade_count} rows for {grade_str}")

    print()
    print(f"Done. Total rows upserted: {total_inserted}")
    print("=" * 60)


if __name__ == "__main__":
    main()
