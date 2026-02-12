from app.services.supabase_client import get_supabase_client
from app.services.mastery_store import classify_mastery


def get_parent_dashboard(student_id: str):
    sb = get_supabase_client()

    # Skill accuracy
    skill_rows = (
        sb.table("v_student_skill_progress")
        .select("*")
        .eq("student_id", student_id)
        .execute()
        .data
    )

    if not skill_rows:
        return {
            "student_id": student_id,
            "overall_accuracy": 0,
            "total_attempts": 0,
            "skills": [],
        }

    skills = []
    total_attempts = 0
    total_correct = 0

    for row in skill_rows:
        attempts = row["attempts"]
        correct = row["correct_attempts"]
        accuracy = round(100.0 * correct / attempts, 2)

        total_attempts += attempts
        total_correct += correct

        trend = get_skill_trend(student_id, row["skill_tag"])

        skills.append({
            "skill_tag": row["skill_tag"],
            "accuracy": accuracy,
            "attempts": attempts,
            "status": classify_mastery(accuracy, attempts),
            "trend_7d": trend,
        })

    overall_accuracy = round(100.0 * total_correct / total_attempts, 2)

    return {
        "student_id": student_id,
        "overall_accuracy": overall_accuracy,
        "total_attempts": total_attempts,
        "skills": skills,
        "heatmap": build_heatmap(student_id),
    }


def get_skill_trend(student_id: str, skill_tag: str):
    from datetime import date, timedelta

    sb = get_supabase_client()

    today = date.today()
    start = today - timedelta(days=6)

    rows = (
        sb.table("v_student_skill_daily")
        .select("*")
        .eq("student_id", student_id)
        .eq("skill_tag", skill_tag)
        .gte("day", start.isoformat())
        .execute()
        .data
    )

    trend = []
    for i in range(7):
        d = start + timedelta(days=i)
        day_rows = [r for r in rows if r["day"] == d.isoformat()]
        if not day_rows:
            trend.append({"day": d.isoformat(), "accuracy": None})
        else:
            r = day_rows[0]
            acc = round(100.0 * r["correct_attempts"] / r["attempts"], 2)
            trend.append({"day": d.isoformat(), "accuracy": acc})

    return trend


def build_heatmap(student_id: str):
    sb = get_supabase_client()

    rows = (
        sb.table("v_student_skill_daily")
        .select("*")
        .eq("student_id", student_id)
        .execute()
        .data
    )

    matrix = {}

    for r in rows:
        skill = r["skill_tag"]
        day = r["day"]
        acc = round(100.0 * r["correct_attempts"] / r["attempts"], 2)

        if skill not in matrix:
            matrix[skill] = {}

        matrix[skill][day] = acc

    return matrix
