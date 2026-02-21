"""
answer_computer.py — deterministic arithmetic and time computation.

Python computes all answers for Maths/Time questions.
The LLM only writes question wording — never the answer.
"""
from datetime import datetime, timedelta


def add(a: int, b: int) -> str:
    return str(a + b)


def subtract(a: int, b: int) -> str:
    return str(a - b)


def multiply(a: int, b: int) -> str:
    return str(a * b)


def clock_time(hour: int, minute_hand_pos: int) -> str:
    """
    minute_hand_pos is the number on the clock face (1-12).
    Converts to actual minutes: (pos % 12) * 5, so pos=12 → 0 min (o'clock).
    Examples:
        hour=4, minute_hand_pos=7  → "4:35"   (7*5=35)
        hour=3, minute_hand_pos=12 → "3:00"   (12%12=0, 0*5=0)
        hour=6, minute_hand_pos=6  → "6:30"   (6*5=30)
    """
    minutes = (minute_hand_pos % 12) * 5
    return f"{hour}:{minutes:02d}"


def time_after_duration(start_str: str, duration_minutes: int) -> str:
    """start_str format: "3:25 PM" or "9:15 AM". Returns: "3:40 PM" """
    for fmt in ("%I:%M %p", "%I:%M%p"):
        try:
            t = datetime.strptime(start_str.strip().upper(), fmt)
            break
        except ValueError:
            continue
    t2 = t + timedelta(minutes=duration_minutes)
    return t2.strftime("%-I:%M %p")


def duration_between(start_str: str, end_str: str) -> str:
    """Returns "45 minutes" or "1 hour 15 minutes" """
    for fmt in ("%I:%M %p", "%I:%M%p"):
        try:
            t1 = datetime.strptime(start_str.strip().upper(), fmt)
            t2 = datetime.strptime(end_str.strip().upper(), fmt)
            break
        except ValueError:
            continue
    diff = int((t2 - t1).total_seconds() / 60)
    if diff >= 60 and diff % 60 == 0:
        return f"{diff // 60} hour{'s' if diff//60 > 1 else ''}"
    elif diff >= 60:
        return f"{diff // 60} hour{'s' if diff//60 > 1 else ''} {diff % 60} minutes"
    else:
        return f"{diff} minutes"
