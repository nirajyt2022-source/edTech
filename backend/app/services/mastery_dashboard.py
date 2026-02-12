from app.services.mastery_store import get_mastery_store
from app.skills.skill_metadata import topic_for_skill


def get_mastery(student_id: str):
    store = get_mastery_store()
    states = store.list_student(student_id)
    out = []
    for s in states:
        d = s.to_dict()
        d["topic"] = topic_for_skill(s.skill_tag)
        out.append(d)
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


def reset_skill(student_id: str, skill_tag: str):
    store = get_mastery_store()
    store.reset(student_id, skill_tag)
    return {"ok": True}
