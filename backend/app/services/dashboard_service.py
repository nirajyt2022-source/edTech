import logging
from app.services.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


def get_parent_dashboard(student_id: str):
    """
    Build parent dashboard from actual DB tables:
    - mastery_state: skill-level progress
    - child_engagement: streaks and stars
    - worksheets: recent worksheet history
    """
    sb = get_supabase_client()

    # --- Overall stats from child_engagement ---
    overall_stats = {
        "total_worksheets": 0,
        "total_stars": 0,
        "current_streak": 0,
        "longest_streak": 0,
    }
    try:
        eng_resp = (
            sb.table("child_engagement")
            .select("total_stars, current_streak, longest_streak, total_worksheets_completed")
            .eq("child_id", student_id)
            .execute()
        )
        if eng_resp.data and len(eng_resp.data) > 0:
            row = eng_resp.data[0]
            overall_stats["total_stars"] = row.get("total_stars", 0) or 0
            overall_stats["current_streak"] = row.get("current_streak", 0) or 0
            overall_stats["longest_streak"] = row.get("longest_streak", 0) or 0
            overall_stats["total_worksheets"] = row.get("total_worksheets_completed", 0) or 0
    except Exception as e:
        logger.warning("Failed to fetch child_engagement for %s: %s", student_id, e)

    # --- Skills from mastery_state ---
    skills = []
    try:
        mastery_resp = (
            sb.table("mastery_state")
            .select("skill_tag, streak, total_attempts, correct_attempts, mastery_level")
            .eq("student_id", student_id)
            .execute()
        )
        if mastery_resp.data:
            for row in mastery_resp.data:
                total = row.get("total_attempts", 0) or 0
                correct = row.get("correct_attempts", 0) or 0
                accuracy = round(100.0 * correct / total, 1) if total > 0 else 0.0
                skills.append({
                    "skill_tag": row.get("skill_tag", ""),
                    "mastery_level": row.get("mastery_level", "unknown"),
                    "streak": row.get("streak", 0) or 0,
                    "total_attempts": total,
                    "correct_attempts": correct,
                    "accuracy": accuracy,
                })
    except Exception as e:
        logger.warning("Failed to fetch mastery_state for %s: %s", student_id, e)

    # --- Recent topics from worksheets ---
    recent_topics = []
    try:
        ws_resp = (
            sb.table("worksheets")
            .select("topic, created_at")
            .eq("child_id", student_id)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
        if ws_resp.data:
            # Also update total_worksheets from worksheets table if engagement was empty
            if overall_stats["total_worksheets"] == 0:
                overall_stats["total_worksheets"] = len(ws_resp.data)

            # Aggregate by topic
            topic_map: dict[str, dict] = {}
            for row in ws_resp.data:
                topic = row.get("topic", "Unknown") or "Unknown"
                if topic not in topic_map:
                    topic_map[topic] = {
                        "topic": topic,
                        "count": 0,
                        "last_generated": row.get("created_at", ""),
                    }
                topic_map[topic]["count"] += 1

            recent_topics = sorted(
                topic_map.values(),
                key=lambda x: x["last_generated"],
                reverse=True,
            )
    except Exception as e:
        logger.warning("Failed to fetch worksheets for %s: %s", student_id, e)

    return {
        "student_id": student_id,
        "overall_stats": overall_stats,
        "skills": skills,
        "recent_topics": recent_topics,
    }
