"""Phrasing templates per skill tag — inject into prompts for natural variation.

Each key maps to 3-5 example phrasings. The LLM samples from these to avoid
robotic repetition ("Solve: X + Y" ten times).

Lookup order:
    1. Exact match on skill_tag
    2. Suffix fallback (e.g. tag ending in "_word_problem")
    3. Empty list (no match)
"""

from __future__ import annotations

import random

PHRASING_TEMPLATES: dict[str, list[str]] = {
    "column_add_with_carry": [
        "Add {a} and {b} using column method. Show your working.",
        "Find the sum: {a} + {b}. Remember to regroup.",
        "{name} scored {a} runs on Saturday and {b} runs on Sunday. What is the total?",
        "Use regrouping to calculate {a} + {b}.",
        "Set up in columns and add: {a} + {b} = ______",
    ],
    "column_sub_with_borrow": [
        "Subtract {b} from {a} using column method.",
        "Find the difference: {a} − {b}. Regroup if needed.",
        "{name} had {a} stickers and gave away {b}. How many are left?",
        "Use borrowing to solve: {a} − {b} = ______",
        "Set up in columns and subtract: {a} − {b}",
    ],
    "missing_number": [
        "{a} + ______ = {result}. What is the missing number?",
        "Complete: ______ − {b} = {result}",
        "Find the number that makes this true: {a} ○ ______ = {result}",
        "What goes in the box? {a} + □ = {result}",
    ],
    "estimation": [
        "Without calculating, estimate {a} + {b}. Is it closer to {low} or {high}?",
        "Round {a} and {b} to the nearest ten, then add.",
        "{name} estimates {a} + {b} ≈ {estimate}. Is this a good estimate? Why?",
    ],
    "thinking": [
        "Explain step-by-step how you would solve {expression}.",
        "{name} says the answer is {wrong}. Do you agree? Explain your reasoning.",
        "Can you find two different ways to solve {expression}?",
        "What strategy would you use to check your answer for {expression}?",
    ],
    "clock_reading": [
        "What time does this clock show?",
        "Look at the clock. Write the time in numbers.",
        "The short hand points to {h} and the long hand points to {m}. What time is it?",
        "Read the time shown on this clock face.",
    ],
}

PHRASING_TEMPLATES_BY_SUFFIX: dict[str, list[str]] = {
    "_word_problem": [
        "{name} goes to the {context} and buys {a} items at ₹{b} each. How much does {name} pay?",
        "At the {context}, {name} has {a} {objects}. {name} gets {b} more. How many now?",
        "{name} had {a} {objects}. After giving some away, {name} has {b} left. How many were given away?",
        "A {context} has {a} {objects} in the morning and {b} more arrive. Find the total.",
        "If {name} reads {a} pages on Monday and {b} pages on Tuesday, how many pages in all?",
    ],
    "_error_spot": [
        "{name} solved this problem but made a mistake. Find and correct the error.",
        "Is this solution correct? If not, explain what went wrong.",
        "Check {name}'s work below. What mistake did {name} make?",
        "This answer is wrong. Spot the error and write the correct answer.",
    ],
    "_fill_blank": [
        "Complete the sentence: ______",
        "Fill in the missing word or number: ______",
        "What belongs in the blank? ______",
    ],
    "_match": [
        "Match each item in Column A with the correct item in Column B.",
        "Draw lines to connect the matching pairs.",
        "Which items go together? Match them.",
    ],
    "_identify": [
        "Look at the following and identify: ______",
        "Which of these is a ______? Circle your answer.",
        "Name the type of ______ shown below.",
    ],
}


def get_phrasing_samples(skill_tag: str, count: int = 2) -> list[str]:
    """Return ``count`` randomly sampled phrasing templates for a skill tag.

    Lookup order: exact match → suffix fallback → empty list.
    """
    # 1. Exact match
    templates = PHRASING_TEMPLATES.get(skill_tag)
    if templates:
        return random.sample(templates, min(count, len(templates)))

    # 2. Suffix fallback
    for suffix, tmpls in PHRASING_TEMPLATES_BY_SUFFIX.items():
        if skill_tag.endswith(suffix):
            return random.sample(tmpls, min(count, len(tmpls)))

    return []
