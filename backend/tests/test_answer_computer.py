"""
Tests for answer_computer.py — every function, every specified case.
"""
import pytest
from app.utils.answer_computer import (
    add, subtract, multiply,
    clock_time, time_after_duration, duration_between,
)


# ── clock_time ────────────────────────────────────────────────────────────────

class TestClockTime:
    def test_12_oclock(self):
        assert clock_time(12, 12) == "12:00"

    def test_half_past_6(self):
        assert clock_time(6, 6) == "6:30"

    def test_4_35(self):
        assert clock_time(4, 7) == "4:35"

    def test_oclock_wraps_correctly(self):
        # minute_hand_pos=12 means "pointing at 12" → 0 minutes (o'clock).
        # Formula: (12 % 12) * 5 = 0. Must NOT produce "12:60".
        assert clock_time(3, 12) == "3:00"
        assert clock_time(9, 12) == "9:00"
        assert clock_time(1, 12) == "1:00"

    def test_half_hour_positions(self):
        # minute_hand_pos=6 → 6*5=30 minutes
        assert clock_time(2, 6) == "2:30"
        assert clock_time(9, 6) == "9:30"

    def test_quarter_past(self):
        # minute_hand_pos=3 → 3*5=15 minutes
        assert clock_time(4, 3) == "4:15"
        assert clock_time(11, 3) == "11:15"

    def test_quarter_to(self):
        # minute_hand_pos=9 → 9*5=45 minutes
        assert clock_time(6, 9) == "6:45"
        assert clock_time(3, 9) == "3:45"

    def test_five_past(self):
        # minute_hand_pos=1 → 1*5=5 minutes
        assert clock_time(6, 1) == "6:05"

    def test_twenty_past(self):
        # minute_hand_pos=4 → 4*5=20 minutes
        assert clock_time(1, 4) == "1:20"

    def test_ten_past(self):
        # minute_hand_pos=2 → 2*5=10 minutes
        assert clock_time(5, 2) == "5:10"

    def test_50_minutes(self):
        # minute_hand_pos=10 → 10*5=50 minutes
        assert clock_time(3, 10) == "3:50"

    def test_25_minutes(self):
        # minute_hand_pos=5 → 5*5=25 minutes
        assert clock_time(12, 5) == "12:25"

    def test_35_minutes(self):
        # minute_hand_pos=7 → 7*5=35 minutes
        assert clock_time(10, 7) == "10:35"

    def test_40_minutes(self):
        # minute_hand_pos=8 → 8*5=40 minutes
        assert clock_time(9, 8) == "9:40"

    def test_55_minutes(self):
        # minute_hand_pos=11 → 11*5=55 minutes
        assert clock_time(2, 11) == "2:55"


# ── time_after_duration ───────────────────────────────────────────────────────

class TestTimeAfterDuration:
    def test_basic(self):
        assert time_after_duration("3:25 PM", 15) == "3:40 PM"

    def test_crosses_noon(self):
        assert time_after_duration("11:45 AM", 30) == "12:15 PM"

    def test_hour_boundary(self):
        # 3:40 PM + 45 min = 4:25 PM
        assert time_after_duration("3:40 PM", 45) == "4:25 PM"

    def test_morning(self):
        # 9:15 AM + 45 min = 10:00 AM
        assert time_after_duration("9:15 AM", 45) == "10:00 AM"

    def test_whole_hour_result(self):
        # 9:00 AM + 60 min = 10:00 AM
        assert time_after_duration("9:00 AM", 60) == "10:00 AM"


# ── duration_between ──────────────────────────────────────────────────────────

class TestDurationBetween:
    def test_45_minutes(self):
        assert duration_between("4:15 PM", "5:00 PM") == "45 minutes"

    def test_1_hour_exact(self):
        assert duration_between("9:00 AM", "10:00 AM") == "1 hour"

    def test_2_hours_exact(self):
        assert duration_between("8:00 AM", "10:00 AM") == "2 hours"

    def test_45_minutes_am(self):
        assert duration_between("10:20 AM", "11:05 AM") == "45 minutes"

    def test_50_minutes(self):
        assert duration_between("2:10 PM", "3:00 PM") == "50 minutes"

    def test_55_minutes(self):
        assert duration_between("1:05 PM", "2:00 PM") == "55 minutes"

    def test_40_minutes(self):
        assert duration_between("3:40 PM", "4:20 PM") == "40 minutes"

    def test_30_minutes(self):
        assert duration_between("3:00 PM", "3:30 PM") == "30 minutes"

    def test_1_hour_15_minutes(self):
        assert duration_between("8:00 AM", "9:15 AM") == "1 hour 15 minutes"


# ── add / subtract / multiply ─────────────────────────────────────────────────

class TestArithmetic:
    def test_add(self):
        assert add(47, 35) == "82"

    def test_subtract(self):
        assert subtract(100, 37) == "63"

    def test_multiply(self):
        assert multiply(6, 7) == "42"

    def test_add_zero(self):
        assert add(0, 99) == "99"

    def test_subtract_zero(self):
        assert subtract(50, 0) == "50"

    def test_multiply_zero(self):
        assert multiply(8, 0) == "0"

    def test_add_carries(self):
        assert add(99, 1) == "100"

    def test_subtract_borrow(self):
        assert subtract(200, 57) == "143"

    def test_multiply_two_digit(self):
        assert multiply(12, 12) == "144"
