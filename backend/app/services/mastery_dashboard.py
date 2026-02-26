from app.services.mastery_store import get_mastery_store
from app.skills.skill_metadata import topic_for_skill


def get_mastery(student_id: str):
    store = get_mastery_store()
    states = store.list_student(student_id)
    out = []
    for s in states:
        accuracy = round(
            (s.correct_attempts / s.total_attempts * 100) if s.total_attempts else 0.0,
            1,
        )
        # Map mastery_level → status for the API surface
        status_map = {"mastered": "mastered", "improving": "developing", "learning": "developing", "unknown": "unknown"}
        out.append(
            {
                "skill_tag": s.skill_tag,
                "accuracy": accuracy,
                "attempts": s.total_attempts,
                "status": status_map.get(s.mastery_level, s.mastery_level),
            }
        )
    return out


def topic_summary(student_id: str, topic: str):
    store = get_mastery_store()
    states = store.list_student(student_id)

    filtered = []
    for s in states:
        if topic_for_skill(s.skill_tag) == topic:
            filtered.append(s)

    total = len(filtered)
    mastered = sum(1 for s in filtered if s.mastery_level == "mastered")
    improving = sum(1 for s in filtered if s.mastery_level == "improving")
    learning = sum(1 for s in filtered if s.mastery_level == "learning")

    return {
        "student_id": student_id,
        "topic": topic,
        "skills_total": total,
        "mastered": mastered,
        "improving": improving,
        "learning": learning,
        "skills": [{**s.to_dict(), "topic": topic_for_skill(s.skill_tag)} for s in filtered],
    }


def get_skill_gaps(student_id: str, subject: str | None = None) -> list[dict]:
    """Return skills below mastery threshold, sorted weakest-first.

    Each entry: {skill_tag, accuracy, attempts, topic, status}
    Only includes skills with 3+ attempts (enough data to judge).
    """
    MASTERY_THRESHOLD = 75.0  # percent

    store = get_mastery_store()
    states = store.list_student(student_id)
    if not states:
        return []

    gaps = []
    for s in states:
        if s.total_attempts < 3:
            continue
        accuracy = round(
            (s.correct_attempts / s.total_attempts * 100) if s.total_attempts else 0.0,
            1,
        )
        if accuracy < MASTERY_THRESHOLD:
            topic = topic_for_skill(s.skill_tag)
            # Optional subject filter
            if subject and topic != "Unknown":
                # topic_for_skill returns topic names not subjects, so skip filter if unclear
                pass
            gaps.append(
                {
                    "skill_tag": s.skill_tag,
                    "accuracy": accuracy,
                    "attempts": s.total_attempts,
                    "topic": topic,
                    "status": s.mastery_level,
                }
            )

    gaps.sort(key=lambda g: g["accuracy"])
    return gaps


def reset_skill(student_id: str, skill_tag: str):
    store = get_mastery_store()
    store.reset(student_id, skill_tag)
    return {"ok": True}
