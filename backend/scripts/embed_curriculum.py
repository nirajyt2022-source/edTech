#!/usr/bin/env python3
"""
One-time script to populate embeddings for existing curriculum content.

Phase 1: Embed curriculum_content rows → UPDATE embedding column
Phase 2: Embed TOPIC_PROFILES + LEARNING_OBJECTIVES → INSERT into curriculum_embeddings

Usage:
    cd backend
    python scripts/embed_curriculum.py          # Skip rows that already have embeddings
    python scripts/embed_curriculum.py --force   # Re-embed everything
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Ensure backend/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def main(force: bool = False) -> None:
    from app.core.deps import get_supabase_client
    from app.services.embedding import get_embedding_service

    sb = get_supabase_client()
    svc = get_embedding_service()

    # ── Phase 1: Embed curriculum_content rows ──────────────────────────
    print("Phase 1: Embedding curriculum_content rows...")
    q = sb.table("curriculum_content").select("*")
    result = q.execute()
    rows = result.data or []
    print(f"  Found {len(rows)} curriculum_content rows")

    texts_to_embed = []
    row_ids = []
    for row in rows:
        if not force and row.get("embedding"):
            continue
        # Concatenate key fields for a rich embedding
        parts = [
            row.get("topic", ""),
            row.get("chapter_name", ""),
            row.get("ncert_summary", ""),
        ]
        if row.get("key_concepts") and isinstance(row["key_concepts"], list):
            parts.append("; ".join(row["key_concepts"]))
        if row.get("learning_outcomes") and isinstance(row["learning_outcomes"], list):
            parts.append("; ".join(row["learning_outcomes"]))
        if row.get("common_mistakes") and isinstance(row["common_mistakes"], list):
            parts.append("; ".join(row["common_mistakes"]))

        text = " | ".join(p for p in parts if p)
        texts_to_embed.append(text)
        row_ids.append(row["id"])

    if not texts_to_embed:
        print("  All rows already have embeddings (use --force to re-embed)")
    else:
        print(f"  Embedding {len(texts_to_embed)} rows...")
        vectors = await svc.embed_batch(texts_to_embed)

        for row_id, vec in zip(row_ids, vectors):
            sb.table("curriculum_content").update({"embedding": vec}).eq("id", row_id).execute()

        print(f"  Updated {len(vectors)} rows with embeddings")

    # ── Phase 2: Embed topic profiles into curriculum_embeddings ────────
    print("\nPhase 2: Embedding topic profiles into curriculum_embeddings...")

    try:
        from app.data.topic_profiles import TOPIC_PROFILES
    except ImportError:
        print("  TOPIC_PROFILES not found, skipping Phase 2")
        return

    try:
        from app.data.learning_objectives import LEARNING_OBJECTIVES
    except ImportError:
        LEARNING_OBJECTIVES = {}

    profiles_to_embed = []
    for key, profile in TOPIC_PROFILES.items():
        grade = profile.get("grade", "")
        subject = profile.get("subject", "")
        topic = profile.get("topic", key)

        # Build text from profile
        parts = [topic]
        if profile.get("description"):
            parts.append(profile["description"])

        # Add learning objectives if available
        obj_key = f"{grade}|{subject}|{topic}".lower()
        objectives = LEARNING_OBJECTIVES.get(obj_key, [])
        if objectives:
            parts.append("; ".join(objectives))

        text = " | ".join(p for p in parts if p)
        profiles_to_embed.append(
            {
                "grade": str(grade),
                "subject": subject,
                "topic": topic,
                "chunk_text": text,
            }
        )

    if not profiles_to_embed:
        print("  No profiles to embed")
        return

    if not force:
        existing = sb.table("curriculum_embeddings").select("topic", count="exact").execute()
        if existing.count and existing.count > 0:
            print(f"  {existing.count} embeddings already exist (use --force to re-embed)")
            return

    print(f"  Embedding {len(profiles_to_embed)} topic profiles...")
    texts = [p["chunk_text"] for p in profiles_to_embed]
    vectors = await svc.embed_batch(texts)

    for profile, vec in zip(profiles_to_embed, vectors):
        sb.table("curriculum_embeddings").insert(
            {
                "source_type": "topic_profile",
                "grade": profile["grade"],
                "subject": profile["subject"],
                "topic": profile["topic"],
                "chunk_text": profile["chunk_text"],
                "chunk_index": 0,
                "embedding": vec,
            }
        ).execute()

    print(f"  Inserted {len(vectors)} topic profile embeddings")
    print("\nDone!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Embed curriculum content for vector search")
    parser.add_argument("--force", action="store_true", help="Re-embed rows that already have embeddings")
    args = parser.parse_args()
    asyncio.run(main(force=args.force))
