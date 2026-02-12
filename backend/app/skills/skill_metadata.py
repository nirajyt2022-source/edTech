SKILL_TOPIC_MAP = {
    "column_add_with_carry": "Addition and subtraction (3-digit)",
    "column_sub_with_borrow": "Addition and subtraction (3-digit)",
    "multiplication_table_recall": "Multiplication tables",
    # drill skills can map to same parent topic
    "addition_isolated_ones_carry": "Addition and subtraction (3-digit)",
    "subtraction_isolated_tens_borrow": "Addition and subtraction (3-digit)",
}


def topic_for_skill(skill_tag: str) -> str:
    return SKILL_TOPIC_MAP.get(skill_tag, "Unknown")
