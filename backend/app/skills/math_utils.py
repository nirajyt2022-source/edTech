"""
Math utilities for arithmetic skill generators.
"""

import random


def compute_wrong(a: int, b: int, tag: str) -> int:
    """Deterministically compute a wrong answer based on carry error tag."""
    a_o, a_t, a_h = a % 10, (a // 10) % 10, a // 100
    b_o, b_t, b_h = b % 10, (b // 10) % 10, b // 100

    ones_sum = a_o + b_o
    carry_ones = 1 if ones_sum >= 10 else 0

    if tag == "lost_carry_ones":
        r_o = ones_sum % 10
        tens_raw = a_t + b_t  # no carry from ones
        r_t = tens_raw % 10
        carry_t = 1 if tens_raw >= 10 else 0
        r_h = a_h + b_h + carry_t

    elif tag == "lost_carry_tens":
        r_o = ones_sum % 10
        tens_with_carry = a_t + b_t + carry_ones
        r_t = tens_with_carry % 10
        r_h = a_h + b_h  # no carry from tens

    elif tag == "double_carry":
        r_o = ones_sum % 10
        tens_double = a_t + b_t + carry_ones * 2
        r_t = tens_double % 10
        carry_t_d = 1 if tens_double >= 10 else 0
        r_h = a_h + b_h + carry_t_d

    elif tag == "carry_to_wrong_col":
        r_o = ones_sum % 10
        tens_no_carry = a_t + b_t  # ones carry didn't come here
        r_t = tens_no_carry % 10
        carry_from_tens = 1 if tens_no_carry >= 10 else 0
        r_h = a_h + b_h + carry_ones + carry_from_tens  # ones carry to hundreds

    elif tag == "no_carry_digitwise":
        r_o = (a_o + b_o) % 10
        r_t = (a_t + b_t) % 10
        r_h = (a_h + b_h) % 10

    else:
        return a + b

    return r_h * 100 + r_t * 10 + r_o


def has_carry(a: int, b: int) -> bool:
    """Check if a + b requires carrying in ones or tens column."""
    return (a % 10) + (b % 10) >= 10 or ((a // 10) % 10) + ((b // 10) % 10) >= 10


def has_borrow(a: int, b: int) -> bool:
    """Check if a - b requires borrowing in ones or tens column (a > b assumed)."""
    if a < b:
        a, b = b, a
    return (a % 10) < (b % 10) or ((a // 10) % 10) < ((b // 10) % 10)


def make_carry_pair(rng: random.Random, operation: str = "addition") -> tuple[int, int]:
    """Generate a 3-digit pair requiring carry (addition) or borrow (subtraction)."""
    if operation == "subtraction":
        for _ in range(50):
            a = rng.randint(200, 999)
            b = rng.randint(100, a - 1)
            if has_borrow(a, b):
                return a, b
        return 502, 178  # guaranteed borrow fallback

    for _ in range(50):
        a = rng.randint(100, 899)
        b = rng.randint(100, 899)
        if has_carry(a, b) and a + b <= 999:
            return a, b
    return 345, 278  # guaranteed carry fallback
