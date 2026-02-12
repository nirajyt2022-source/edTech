from dataclasses import dataclass, asdict
from typing import Optional
import time


@dataclass
class MasteryState:
    student_id: str
    skill_tag: str
    streak: int = 0
    total_attempts: int = 0
    correct_attempts: int = 0
    last_error_type: Optional[str] = None
    mastery_level: str = "unknown"   # unknown | learning | improving | mastered
    updated_at: float = 0.0

    def to_dict(self):
        return asdict(self)


class MasteryStore:
    def get(self, student_id: str, skill_tag: str) -> Optional[MasteryState]:
        raise NotImplementedError

    def upsert(self, state: MasteryState) -> MasteryState:
        raise NotImplementedError

    def reset(self, student_id: str, skill_tag: str) -> None:
        raise NotImplementedError

    def list_student(self, student_id: str) -> list[MasteryState]:
        raise NotImplementedError

    def list_student_by_topic(self, student_id: str, topic: str) -> list[MasteryState]:
        raise NotImplementedError


class InMemoryMasteryStore(MasteryStore):
    def __init__(self):
        self._data = {}

    def _key(self, student_id: str, skill_tag: str):
        return f"{student_id}::{skill_tag}"

    def get(self, student_id: str, skill_tag: str) -> Optional[MasteryState]:
        return self._data.get(self._key(student_id, skill_tag))

    def upsert(self, state: MasteryState) -> MasteryState:
        state.updated_at = time.time()
        self._data[self._key(state.student_id, state.skill_tag)] = state
        return state

    def reset(self, student_id: str, skill_tag: str) -> None:
        self._data.pop(self._key(student_id, skill_tag), None)

    def list_student(self, student_id):
        out = []
        prefix = f"{student_id}::"
        for k, v in self._data.items():
            if k.startswith(prefix):
                out.append(v)
        return out

    def list_student_by_topic(self, student_id, topic):
        # topic filter handled at API layer via SKILL->TOPIC map later; for now same as list_student
        return self.list_student(student_id)


class SupabaseMasteryStore(MasteryStore):
    def __init__(self, supabase_client):
        self.sb = supabase_client

    def get(self, student_id: str, skill_tag: str) -> Optional[MasteryState]:
        r = (
            self.sb.table("mastery_state")
            .select("*")
            .eq("student_id", student_id)
            .eq("skill_tag", skill_tag)
            .maybe_single()
            .execute()
        )
        data = getattr(r, "data", None)
        if not data:
            return None
        return MasteryState(
            student_id=data["student_id"],
            skill_tag=data["skill_tag"],
            streak=int(data["streak"]),
            total_attempts=int(data["total_attempts"]),
            correct_attempts=int(data["correct_attempts"]),
            last_error_type=data.get("last_error_type"),
            mastery_level=data.get("mastery_level", "unknown"),
            updated_at=float(time.time()),
        )

    def upsert(self, state: MasteryState) -> MasteryState:
        payload = {
            "student_id": state.student_id,
            "skill_tag": state.skill_tag,
            "streak": state.streak,
            "total_attempts": state.total_attempts,
            "correct_attempts": state.correct_attempts,
            "last_error_type": state.last_error_type,
            "mastery_level": state.mastery_level,
            "updated_at": time.time(),
        }
        (
            self.sb.table("mastery_state")
            .upsert(payload, on_conflict="student_id,skill_tag")
            .execute()
        )
        return state

    def reset(self, student_id: str, skill_tag: str) -> None:
        self.sb.table("mastery_state").delete().eq("student_id", student_id).eq("skill_tag", skill_tag).execute()

    def list_student(self, student_id):
        r = self.sb.table("mastery_state").select("*").eq("student_id", student_id).execute()
        rows = getattr(r, "data", None) or []
        out = []
        for d in rows:
            out.append(MasteryState(
                student_id=d["student_id"],
                skill_tag=d["skill_tag"],
                streak=int(d["streak"]),
                total_attempts=int(d["total_attempts"]),
                correct_attempts=int(d["correct_attempts"]),
                last_error_type=d.get("last_error_type"),
                mastery_level=d.get("mastery_level", "unknown"),
                updated_at=float(time.time()),
            ))
        return out

    def list_student_by_topic(self, student_id, topic):
        # no topic column yet; return list_student and filter at API layer
        return self.list_student(student_id)


MASTERY_STORE = InMemoryMasteryStore()


def get_mastery_store():
    import os
    use_db = os.getenv("PRACTICECRAFT_MASTERY_STORE", "memory").lower()
    if use_db != "supabase":
        return MASTERY_STORE

    # lazy import to avoid dependency/testing issues
    try:
        from app.services.supabase_client import get_supabase_client
    except Exception:
        return MASTERY_STORE

    try:
        sb = get_supabase_client()
        return SupabaseMasteryStore(sb)
    except Exception:
        return MASTERY_STORE


def update_mastery_from_grade(student_id: str, skill_tag: str, grade: dict) -> MasteryState:
    store = get_mastery_store()
    state = store.get(student_id, skill_tag)
    if not state:
        state = MasteryState(student_id=student_id, skill_tag=skill_tag)

    state.total_attempts += 1

    is_correct = grade.get("is_correct") is True
    if is_correct:
        state.correct_attempts += 1
        state.streak += 1
        state.last_error_type = None
    else:
        state.streak = 0
        state.last_error_type = grade.get("error_type")

    # mastery level rules (deterministic, v0)
    if state.streak >= 3:
        state.mastery_level = "mastered"
    else:
        acc = (state.correct_attempts / state.total_attempts) if state.total_attempts else 0.0
        if state.total_attempts >= 5 and acc >= 0.7:
            state.mastery_level = "improving"
        else:
            state.mastery_level = "learning"

    return store.upsert(state)
