"""Phrasing templates per skill tag — inject into prompts for natural variation.

Each key maps to 8-10 example phrasings. The LLM samples from these to avoid
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
        "Help {name} add {a} and {b}. Write the steps.",
        "How much is {a} plus {b}? Use carrying to find out.",
        "Can you add {a} + {b}? Show each step clearly.",
        "Write {a} and {b} one below the other and add them.",
        "{name} collects {a} stamps, then gets {b} more. What is the total?",
    ],
    "column_sub_with_borrow": [
        "Subtract {b} from {a} using column method.",
        "Find the difference: {a} − {b}. Regroup if needed.",
        "{name} had {a} stickers and gave away {b}. How many are left?",
        "Use borrowing to solve: {a} − {b} = ______",
        "Set up in columns and subtract: {a} − {b}",
        "Help {name} work out {a} minus {b}.",
        "Take away {b} from {a}. Show your borrowing steps.",
        "How many remain if you remove {b} from {a}?",
        "{name} has ₹{a} and spends ₹{b}. How much money is left?",
        "Can you solve {a} − {b}? Write each step.",
    ],
    "missing_number": [
        "{a} + ______ = {result}. What is the missing number?",
        "Complete: ______ − {b} = {result}",
        "Find the number that makes this true: {a} ○ ______ = {result}",
        "What goes in the box? {a} + □ = {result}",
        "Help {name} find the hidden number: {a} + ? = {result}",
        "If {a} plus something equals {result}, what is the something?",
        "Fill in the gap: ______ + {b} = {result}",
        "What number is missing? {a} − ______ = {result}",
    ],
    "estimation": [
        "Without calculating, estimate {a} + {b}. Is it closer to {low} or {high}?",
        "Round {a} and {b} to the nearest ten, then add.",
        "{name} estimates {a} + {b} ≈ {estimate}. Is this a good estimate? Why?",
        "Roughly how much is {a} + {b}? Do not calculate exactly.",
        "Which is the best estimate for {a} + {b}: {low}, {estimate}, or {high}?",
        "First guess the answer, then check: {a} + {b}",
        "Round to the nearest hundred and add: {a} + {b}",
        "{name} thinks {a} − {b} is about {estimate}. Is that reasonable?",
    ],
    "thinking": [
        "Explain step-by-step how you would solve {expression}.",
        "{name} says the answer is {wrong}. Do you agree? Explain your reasoning.",
        "Can you find two different ways to solve {expression}?",
        "What strategy would you use to check your answer for {expression}?",
        "Describe your thinking as you work through {expression}.",
        "If you had to teach a friend how to solve {expression}, what would you say?",
        "Which method works best for {expression} — and why?",
        "Solve {expression} and explain each step in your own words.",
    ],
    "clock_reading": [
        "What time does this clock show?",
        "Look at the clock. Write the time in numbers.",
        "The short hand points to {h} and the long hand points to {m}. What time is it?",
        "Read the time shown on this clock face.",
        "Write this clock time using numbers and a colon.",
        "Help {name} read the time on this clock.",
        "What time will it be in 30 minutes?",
        "Is it morning or afternoon? Write the exact time.",
    ],
}

PHRASING_TEMPLATES_BY_SUFFIX: dict[str, list[str]] = {
    "_word_problem": [
        "{name} goes to the {context} and buys {a} items at ₹{b} each. How much does {name} pay?",
        "At the {context}, {name} has {a} {objects}. {name} gets {b} more. How many now?",
        "{name} had {a} {objects}. After giving some away, {name} has {b} left. How many were given away?",
        "A {context} has {a} {objects} in the morning and {b} more arrive. Find the total.",
        "If {name} reads {a} pages on Monday and {b} pages on Tuesday, how many pages in all?",
        "Help {name} figure out: there are {a} {objects} and {b} more are added. How many altogether?",
        "{name}'s class collected {a} {objects}. Another class collected {b}. Who has more and by how much?",
        "On a trip to the {context}, {name} counted {a} {objects}. {b} flew away. How many stayed?",
        "Can you solve this? {name} shared {a} {objects} equally among {b} friends.",
        "{name} packed {a} {objects} in a bag. Then put in {b} more. What is the total?",
    ],
    "_error_spot": [
        "{name} solved this problem but made a mistake. Find and correct the error.",
        "Is this solution correct? If not, explain what went wrong.",
        "Check {name}'s work below. What mistake did {name} make?",
        "This answer is wrong. Spot the error and write the correct answer.",
        "Oh no — {name} got the wrong answer! Can you find where things went wrong?",
        "Look at this working carefully. Something is not right. What is it?",
        "Help {name} by finding and fixing the mistake in this solution.",
        "True or false: this answer is correct. If false, show the correct working.",
    ],
    "_fill_blank": [
        "Complete the sentence: ______",
        "Fill in the missing word or number: ______",
        "What belongs in the blank? ______",
        "Write the correct answer in the space: ______",
        "Can you complete this? ______",
        "Think carefully and fill in: ______",
        "What word or number fits here? ______",
        "Help {name} complete this: ______",
    ],
    "_match": [
        "Match each item in Column A with the correct item in Column B.",
        "Draw lines to connect the matching pairs.",
        "Which items go together? Match them.",
        "Pair up each item on the left with its match on the right.",
        "Can you find which ones belong together?",
        "Connect each item to its correct partner.",
        "Look at both columns and match the pairs.",
        "Help {name} match these correctly.",
    ],
    "_identify": [
        "Look at the following and identify: ______",
        "Which of these is a ______? Circle your answer.",
        "Name the type of ______ shown below.",
        "Can you spot the ______ in this group?",
        "Point out which one is a ______.",
        "Pick out all the ______ from the list.",
        "Help {name} identify the ______ here.",
        "How many ______ can you find?",
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
