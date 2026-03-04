"""
Gold Standard Regression Fixtures — 15 representative worksheets.

Each fixture is a complete worksheet dict designed to produce a known quality
outcome when run through OutputValidator, quality_scorer, and release_gate.
No LLM calls needed — all content is deterministic.

Fixture naming: gold_{class}_{subject}_{profile}
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Question builders
# ---------------------------------------------------------------------------


def _q(
    idx: int,
    text: str,
    answer: str,
    qtype: str = "short_answer",
    role: str = "application",
    skill_tag: str = "addition",
    hint: str = "Think step by step",
    **extra,
) -> dict:
    d = {
        "id": f"q{idx}",
        "type": qtype,
        "text": text,
        "question_text": text,
        "correct_answer": answer,
        "answer": answer,
        "format": qtype,
        "role": role,
        "skill_tag": skill_tag,
        "hint": hint,
    }
    d.update(extra)
    return d


def _mcq(idx: int, text: str, answer: str, options: list[str], **kw) -> dict:
    return _q(idx, text, answer, qtype="mcq", options=options, **kw)


# ---------------------------------------------------------------------------
# Worksheet wrapper
# ---------------------------------------------------------------------------


def _ws(
    grade: str,
    subject: str,
    topic: str,
    questions: list[dict],
    skill_focus: str = "",
    common_mistake: str = "",
    parent_tip: str = "",
    learning_objectives: list[str] | None = None,
    chapter_ref: str = "",
    **extra,
) -> dict:
    base = {
        "title": f"{subject} Worksheet — {topic}",
        "grade": grade,
        "subject": subject,
        "topic": topic,
        "difficulty": "Medium",
        "language": "English",
        "questions": questions,
        "learning_objectives": learning_objectives or [],
        "chapter_ref": chapter_ref,
        "skill_focus": skill_focus,
        "common_mistake": common_mistake,
        "parent_tip": parent_tip,
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# GOLD FIXTURES
# ---------------------------------------------------------------------------


def _gold_c1_maths_clean() -> dict:
    """Class 1 Maths, 5Q, diverse, all fields populated. Expected: score>=80, released."""
    return _ws(
        grade="Class 1",
        subject="Maths",
        topic="Addition (single digit)",
        skill_focus="Adding single-digit numbers up to 9",
        common_mistake="Counting on fingers incorrectly and skipping the starting number",
        parent_tip="Use real objects like crayons to practice adding small groups",
        learning_objectives=["Add two single-digit numbers", "Use objects to represent addition"],
        chapter_ref="NCERT Ch 3 - Addition",
        questions=[
            _mcq(1, "What is 3 + 2?", "5", ["3", "4", "5", "6"], role="recognition", skill_tag="add_single"),
            _q(2, "Find the total: 4 + 1 = ___", "5", qtype="fill_blank", role="application", skill_tag="add_single"),
            _q(3, "If Priya has 2 balls and gets 3 more, how many balls does she have?", "5",
               qtype="word_problem", role="application", skill_tag="add_word"),
            _q(4, "Can you spot the mistake? 2 + 5 = 6", "2 + 5 = 7",
               qtype="error_detection", role="error_detection", skill_tag="add_error"),
            _q(5, "Draw groups: show 1 + 4 using circles.", "5",
               role="representation", skill_tag="add_represent"),
        ],
    )


def _gold_c1_english_clean() -> dict:
    """Class 1 English, 5Q, fill_blank+mcq. Expected: score>=75, released."""
    return _ws(
        grade="Class 1",
        subject="English",
        topic="Naming Words (Nouns)",
        skill_focus="Identifying naming words for people, animals, and things",
        common_mistake="Confusing action words with naming words",
        parent_tip="Point to objects at home and ask your child to name them",
        learning_objectives=["Identify nouns in simple sentences"],
        chapter_ref="NCERT Ch 2 - Naming Words",
        questions=[
            _mcq(1, "Which word is a naming word?", "cat",
                 ["run", "cat", "big", "fast"], role="recognition", skill_tag="eng_noun"),
            _q(2, "Fill in the blank: The ___ is on the table.", "book",
               qtype="fill_blank", role="application", skill_tag="eng_noun"),
            _q(3, "Write a naming word for an animal.", "dog",
               role="representation", skill_tag="eng_noun"),
            _q(4, "Is 'jump' a naming word? Write True or False.", "False",
               qtype="true_false", role="error_detection", skill_tag="eng_noun"),
            _mcq(5, "How many naming words are in: The boy ate an apple?", "2",
                 ["1", "2", "3", "4"], role="thinking", skill_tag="eng_noun"),
        ],
    )


def _gold_c1_maths_degraded() -> dict:
    """Class 1 Maths, 5Q, missing parent blocks. Expected: score 50-79, best_effort."""
    return _ws(
        grade="Class 1",
        subject="Maths",
        topic="Addition (single digit)",
        skill_focus="",  # missing
        common_mistake="",  # missing
        parent_tip="",
        learning_objectives=[],  # missing
        chapter_ref="",
        questions=[
            _mcq(1, "What is 1 + 3?", "4", ["2", "3", "4", "5"], role="recognition", skill_tag="add_single"),
            _q(2, "Solve: 2 + 2 = ___", "4", qtype="fill_blank", role="application", skill_tag="add_single"),
            _q(3, "If Arjun has 3 toys and finds 1 more, how many toys?", "4",
               qtype="word_problem", role="application", skill_tag="add_word"),
            _q(4, "Can you find what is wrong? 4 + 1 = 6", "4 + 1 = 5",
               qtype="error_detection", role="error_detection", skill_tag="add_error"),
            _q(5, "Show 3 + 2 using a picture.", "5",
               role="representation", skill_tag="add_represent"),
        ],
    )


def _gold_c2_maths_clean() -> dict:
    """Class 2 Maths, 10Q, carry/borrow. Expected: score>=75, released."""
    return _ws(
        grade="Class 2",
        subject="Maths",
        topic="Addition with carrying",
        skill_focus="Two-digit addition requiring carry from ones to tens",
        common_mistake="Forgetting to add the carried 1 to the tens column",
        parent_tip="Write problems vertically and circle the carry digit in a different color",
        learning_objectives=["Add two-digit numbers with carrying", "Place value understanding"],
        chapter_ref="NCERT Ch 5 - Addition",
        questions=[
            _mcq(1, "What is 18 + 15?", "33", ["31", "32", "33", "34"],
                 role="recognition", skill_tag="carry_add"),
            _q(2, "Find the sum: 27 + 14 = ___", "41",
               qtype="fill_blank", role="application", skill_tag="carry_add"),
            _q(3, "Solve: 36 + 28 = ?", "64", role="application", skill_tag="carry_add"),
            _q(4, "Help Meera count: she has 19 beads and gets 13 more.", "32",
               qtype="word_problem", role="application", skill_tag="carry_word"),
            _q(5, "Calculate 45 + 37.", "82", role="application", skill_tag="carry_add"),
            _q(6, "What number goes in the box? 2_ + 16 = 43", "27",
               qtype="fill_blank", role="representation", skill_tag="carry_missing"),
            _q(7, "Is this correct? 29 + 14 = 33. Write the right answer.", "29 + 14 = 43",
               qtype="error_detection", role="error_detection", skill_tag="carry_error"),
            _q(8, "If the school has 38 girls and 25 boys, how many students total?", "63",
               qtype="word_problem", role="application", skill_tag="carry_word"),
            _mcq(9, "Which sum needs carrying?", "17 + 15",
                 ["12 + 13", "17 + 15", "21 + 14", "30 + 20"],
                 role="thinking", skill_tag="carry_identify"),
            _q(10, "Write the place value of 4 in the answer of 26 + 18.", "tens place",
               role="representation", skill_tag="carry_pv"),
        ],
    )


def _gold_c2_hindi_clean() -> dict:
    """Class 2 Hindi, 5Q, Devanagari. Expected: score>=70, released."""
    return _ws(
        grade="Class 2",
        subject="Hindi",
        topic="संज्ञा (Sangya - Nouns)",
        skill_focus="व्यक्तिवाचक और जातिवाचक संज्ञा की पहचान",
        common_mistake="व्यक्तिवाचक और जातिवाचक संज्ञा में भ्रम",
        parent_tip="घर की वस्तुओं के नाम पूछें और उन्हें वर्गीकृत करें",
        learning_objectives=["संज्ञा शब्दों को पहचानना"],
        chapter_ref="NCERT पाठ 2",
        questions=[
            _mcq(1, "कौन सा शब्द संज्ञा है?", "किताब",
                 ["दौड़ना", "किताब", "सुंदर", "तेज़"], role="recognition", skill_tag="hindi_noun"),
            _q(2, "खाली जगह भरो: ___ मेज़ पर है।", "पुस्तक",
               qtype="fill_blank", role="application", skill_tag="hindi_noun"),
            _q(3, "किसी जानवर का नाम लिखो।", "बिल्ली",
               role="representation", skill_tag="hindi_noun"),
            _q(4, "क्या 'खेलना' संज्ञा है? सही या गलत लिखो।", "False",
               qtype="true_false", role="error_detection", skill_tag="hindi_noun"),
            _mcq(5, "इस वाक्य में कितनी संज्ञा हैं: राम ने सेब खाया?", "2",
                 ["1", "2", "3", "4"], role="thinking", skill_tag="hindi_noun"),
        ],
    )


def _gold_c2_maths_blocked() -> dict:
    """Class 2 Maths, 5Q, phantom visual + empty answer. Expected: score<40, blocked."""
    return _ws(
        grade="Class 2",
        subject="Maths",
        topic="Addition with carrying",
        skill_focus="Two-digit addition",
        common_mistake="Carry errors",
        parent_tip="Practice daily",
        learning_objectives=["Addition with carry"],
        chapter_ref="NCERT Ch 5",
        questions=[
            _q(1, "Look at the picture below and add the numbers.", "",  # empty answer
               role="recognition", skill_tag="carry_add",
               _phantom_visual_ref=True),
            _q(2, "Look at the picture below and add the numbers.", "",  # empty answer + duplicate
               role="application", skill_tag="carry_add",
               _phantom_visual_ref=True),
            _q(3, "", "15",  # empty text
               role="application", skill_tag="carry_add"),
            _q(4, "Solve: 12 + 13 = ?", "25",
               role="application", skill_tag="carry_add"),
            _q(5, "What is 14 + 11?", "25",
               role="application", skill_tag="carry_add"),
        ],
    )


def _gold_c3_maths_clean() -> dict:
    """Class 3 Maths, 10Q, full diversity. Expected: score>=80, released."""
    return _ws(
        grade="Class 3",
        subject="Maths",
        topic="Multiplication tables",
        skill_focus="Memorizing and applying multiplication tables 2-5",
        common_mistake="Confusing 3x4 with 3+4 or swapping factors",
        parent_tip="Practice skip counting aloud: 3, 6, 9, 12...",
        learning_objectives=["Recall multiplication facts", "Apply multiplication in word problems"],
        chapter_ref="NCERT Ch 6 - Multiplication",
        questions=[
            _mcq(1, "What is 3 x 4?", "12", ["9", "12", "15", "7"],
                 role="recognition", skill_tag="mult_recall"),
            _q(2, "Find the product: 5 x 3 = ___", "15",
               qtype="fill_blank", role="application", skill_tag="mult_apply"),
            _q(3, "Solve: 4 x 5 = ?", "20", role="application", skill_tag="mult_apply"),
            _q(4, "Help Ravi figure out: if each bag has 4 mangoes and there are 3 bags, how many mangoes?", "12",
               qtype="word_problem", role="application", skill_tag="mult_word"),
            _q(5, "Calculate the total: 2 groups of 7 pencils.", "14",
               role="application", skill_tag="mult_apply"),
            _q(6, "What number completes: ___ x 3 = 15?", "5",
               qtype="fill_blank", role="representation", skill_tag="mult_missing"),
            _q(7, "Can you spot the error? 4 x 3 = 15", "4 x 3 = 12",
               qtype="error_detection", role="error_detection", skill_tag="mult_error"),
            _q(8, "If Ananya plants 5 rows of 4 flowers, how many flowers in total?", "20",
               qtype="word_problem", role="application", skill_tag="mult_word"),
            _mcq(9, "Which gives the largest product?", "5 x 5",
                 ["3 x 4", "5 x 5", "2 x 5", "4 x 3"],
                 role="thinking", skill_tag="mult_compare"),
            _q(10, "Write the skip-counting pattern for 4: 4, 8, ___, ___.", "12, 16",
               role="representation", skill_tag="mult_pattern"),
        ],
    )


def _gold_c3_science_clean() -> dict:
    """Class 3 Science/EVS, 10Q. Expected: score>=75, released."""
    return _ws(
        grade="Class 3",
        subject="Science",
        topic="Plants and Trees",
        skill_focus="Parts of a plant and their functions",
        common_mistake="Thinking roots grow above ground or confusing stem with trunk",
        parent_tip="Grow a bean sprout in a glass to observe root and stem growth",
        learning_objectives=["Name the main parts of a plant", "Describe functions of roots, stem, leaves"],
        chapter_ref="NCERT EVS Ch 2 - Plant Life",
        questions=[
            _mcq(1, "Which part of a plant takes in water from the soil?", "Roots",
                 ["Leaves", "Roots", "Flowers", "Stem"], role="recognition", skill_tag="sci_plant_parts"),
            _q(2, "Fill in: The ___ carries water from roots to leaves.", "stem",
               qtype="fill_blank", role="application", skill_tag="sci_plant_fn"),
            _q(3, "What do leaves use to make food?", "Sunlight",
               role="application", skill_tag="sci_photosyn"),
            _q(4, "If a plant has no roots, can it survive? Explain.", "No, roots absorb water and minerals",
               role="thinking", skill_tag="sci_reasoning"),
            _mcq(5, "Which of these is NOT a part of a plant?", "Wheel",
                 ["Root", "Leaf", "Wheel", "Stem"], role="recognition", skill_tag="sci_plant_parts"),
            _q(6, "Name two things that plants need to grow.", "Water and sunlight",
               role="application", skill_tag="sci_needs"),
            _q(7, "Write True or False: Flowers help in making seeds.", "True",
               qtype="true_false", role="application", skill_tag="sci_reproduction"),
            _q(8, "Can you find what is wrong? 'Roots make food for the plant.'", "Leaves make food, not roots",
               qtype="error_detection", role="error_detection", skill_tag="sci_plant_fn"),
            _q(9, "Describe how water travels in a plant from soil to leaf.", "Roots absorb water, stem carries it up to leaves",
               role="representation", skill_tag="sci_transport"),
            _q(10, "Imagine a plant in a dark room for a week. What happens?", "It cannot make food and wilts",
                role="thinking", skill_tag="sci_reasoning"),
        ],
    )


def _gold_c3_maths_warnings() -> dict:
    """Class 3 Maths, 10Q, round numbers, low diversity. Expected: score 50-79, best_effort."""
    return _ws(
        grade="Class 3",
        subject="Maths",
        topic="Addition (3-digit)",
        skill_focus="Three-digit addition without carrying",
        common_mistake="Place value alignment errors",
        parent_tip="Use graph paper to keep digits in columns",
        learning_objectives=["Add three-digit numbers"],
        chapter_ref="NCERT Ch 4",
        questions=[
            # Low diversity: mostly same structure, many round numbers — triggers DEGRADE rules
            _q(1, "Find the sum: 100 + 200 = ?", "300", role="recognition", skill_tag="add_3d"),
            _q(2, "Solve: 150 + 250 = ?", "400", role="application", skill_tag="add_3d"),
            _q(3, "What is 300 + 100?", "400", role="application", skill_tag="add_3d"),
            _q(4, "Calculate 200 + 350.", "550", role="application", skill_tag="add_3d"),
            _q(5, "If Ravi collects 400 stamps and finds 100 more, how many?", "500",
               qtype="word_problem", role="application", skill_tag="add_3d"),
            _q(6, "Complete: 250 + ___ = 400", "150",
               qtype="fill_blank", role="representation", skill_tag="add_3d"),
            _q(7, "Can you spot the mistake? 500 + 200 = 600", "500 + 200 = 700",
               qtype="error_detection", role="error_detection", skill_tag="add_3d"),
            _q(8, "Solve: 350 + 150 = ?", "500", role="application", skill_tag="add_3d"),
            _q(9, "Solve: 100 + 450 = ?", "550", role="application", skill_tag="add_3d"),
            _q(10, "Solve: 200 + 300 = ?", "500", role="application", skill_tag="add_3d"),
        ],
    )


def _gold_c4_maths_clean() -> dict:
    """Class 4 Maths, 10Q, fractions. Expected: score>=75, released."""
    return _ws(
        grade="Class 4",
        subject="Maths",
        topic="Fractions",
        skill_focus="Understanding and comparing simple fractions",
        common_mistake="Adding numerators AND denominators instead of finding common denominator",
        parent_tip="Cut a chapati into equal parts to show fractions physically",
        learning_objectives=["Read and write fractions", "Compare fractions with same denominator"],
        chapter_ref="NCERT Ch 7 - Fractions",
        questions=[
            _mcq(1, "What fraction is shaded if 2 out of 4 parts are coloured?", "1/2",
                 ["1/4", "1/2", "3/4", "2/3"], role="recognition", skill_tag="frac_identify"),
            _q(2, "Write the fraction: three-fourths.", "3/4",
               role="application", skill_tag="frac_write"),
            _q(3, "Find: 1/4 + 2/4 = ?", "3/4",
               role="application", skill_tag="frac_add"),
            _q(4, "Help Kabir share a pizza: if there are 8 slices and he eats 3, what fraction is left?", "5/8",
               qtype="word_problem", role="application", skill_tag="frac_word"),
            _q(5, "Calculate: 5/6 - 2/6 = ?", "3/6",
               role="application", skill_tag="frac_sub"),
            _q(6, "Fill in: 2/5 + ___/5 = 4/5", "2",
               qtype="fill_blank", role="representation", skill_tag="frac_missing"),
            _q(7, "Is this right? 1/3 + 1/3 = 2/6. Find the correct answer.", "1/3 + 1/3 = 2/3",
               qtype="error_detection", role="error_detection", skill_tag="frac_error"),
            _q(8, "If Sana reads 3/7 of a book on Monday and 2/7 on Tuesday, how much has she read?", "5/7",
               qtype="word_problem", role="application", skill_tag="frac_word"),
            _mcq(9, "Which fraction is larger: 2/5 or 4/5?", "4/5",
                 ["2/5", "4/5", "They are equal", "Cannot tell"],
                 role="thinking", skill_tag="frac_compare"),
            _q(10, "Represent 3/8 on a number line: between which two whole numbers?", "0 and 1",
               role="representation", skill_tag="frac_numline"),
        ],
    )


def _gold_c4_english_clean() -> dict:
    """Class 4 English, 10Q, grammar. Expected: score>=75, released."""
    return _ws(
        grade="Class 4",
        subject="English",
        topic="Tenses (Simple Present and Past)",
        skill_focus="Distinguishing between simple present and simple past tense",
        common_mistake="Using present tense form with past tense markers (e.g., 'Yesterday I go')",
        parent_tip="Read stories together and highlight verbs in past tense",
        learning_objectives=["Use simple present tense correctly", "Convert present to past tense"],
        chapter_ref="NCERT Ch 4 - Grammar",
        questions=[
            _mcq(1, "Which sentence is in simple past tense?", "She played yesterday.",
                 ["She plays daily.", "She played yesterday.", "She is playing.", "She will play."],
                 role="recognition", skill_tag="eng_tense"),
            _q(2, "Fill in: He ___ (go) to school every day.", "goes",
               qtype="fill_blank", role="application", skill_tag="eng_present"),
            _q(3, "Change to past tense: I walk to the park.", "I walked to the park.",
               role="application", skill_tag="eng_past"),
            _q(4, "Help Neha correct: 'Yesterday, she eat a mango.' Write correctly.", "Yesterday, she ate a mango.",
               qtype="word_problem", role="application", skill_tag="eng_correction"),
            _q(5, "Write the past tense of 'run'.", "ran",
               role="application", skill_tag="eng_irregular"),
            _q(6, "Complete: They ___ (sing) a song last night.", "sang",
               qtype="fill_blank", role="representation", skill_tag="eng_past"),
            _q(7, "Find the error: 'He goed to the market.'", "He went to the market.",
               qtype="error_detection", role="error_detection", skill_tag="eng_past"),
            _q(8, "If Rahul 'writes' stories every day, what did he do yesterday?", "He wrote a story yesterday.",
               qtype="word_problem", role="application", skill_tag="eng_past"),
            _mcq(9, "Which verb is irregular in past tense?", "go",
                 ["play", "walk", "go", "jump"],
                 role="thinking", skill_tag="eng_irregular"),
            _q(10, "Imagine you visited a zoo. Write one sentence using past tense.", "I visited the zoo and saw many animals.",
                role="representation", skill_tag="eng_past"),
        ],
    )


def _gold_c4_maths_degraded() -> dict:
    """Class 4 Maths, 10Q, missing parent blocks. Expected: score 40-79, best_effort."""
    return _ws(
        grade="Class 4",
        subject="Maths",
        topic="Fractions",
        skill_focus="",  # missing — triggers R21 DEGRADE
        common_mistake="",  # missing
        parent_tip="",
        learning_objectives=[],  # missing — triggers R21 DEGRADE
        chapter_ref="",  # missing
        questions=[
            _mcq(1, "What is 1/4 + 2/4?", "3/4", ["1/4", "2/4", "3/4", "4/4"],
                 role="recognition", skill_tag="frac_add"),
            _q(2, "Find: 2/5 + 1/5 = ?", "3/5", role="application", skill_tag="frac_add"),
            _q(3, "Solve: 3/8 + 2/8 = ?", "5/8", role="application", skill_tag="frac_add",
               _format_corrected=True),  # format was normalized
            _q(4, "Help Asha add: 1/6 + 4/6 = ?", "5/6",
               qtype="word_problem", role="application", skill_tag="frac_word"),
            _q(5, "Calculate: 2/7 + 3/7 = ?", "5/7", role="application", skill_tag="frac_add",
               _format_corrected=True),  # format was normalized
            _q(6, "Complete: 1/3 + ___/3 = 2/3", "1",
               qtype="fill_blank", role="representation", skill_tag="frac_missing"),
            _q(7, "Is this correct? 2/5 + 2/5 = 4/10", "2/5 + 2/5 = 4/5",
               qtype="error_detection", role="error_detection", skill_tag="frac_error"),
            _q(8, "If Rohan eats 2/6 of cake and Priya eats 3/6, how much is eaten?", "5/6",
               qtype="word_problem", role="application", skill_tag="frac_word"),
            _mcq(9, "Which sum equals 1?", "3/3", ["1/3", "2/3", "3/3", "4/3"],
                 role="thinking", skill_tag="frac_whole"),
            _q(10, "Draw and shade 4/8 of a rectangle.", "4 out of 8 parts shaded",
               role="representation", skill_tag="frac_represent"),
        ],
    )


def _gold_c5_maths_clean() -> dict:
    """Class 5 Maths, 15Q, multi-step. Expected: score>=75, released."""
    return _ws(
        grade="Class 5",
        subject="Maths",
        topic="Decimals",
        skill_focus="Adding and subtracting decimals up to hundredths",
        common_mistake="Not aligning decimal points when adding vertically",
        parent_tip="Use money (rupees and paise) as a real-world decimal example",
        learning_objectives=["Add decimals", "Subtract decimals", "Convert fractions to decimals"],
        chapter_ref="NCERT Ch 10 - Decimals",
        questions=[
            _mcq(1, "What is 0.3 + 0.4?", "0.7", ["0.7", "0.07", "7.0", "0.34"],
                 role="recognition", skill_tag="dec_add"),
            _q(2, "Find: 2.5 + 1.3 = ___", "3.8",
               qtype="fill_blank", role="application", skill_tag="dec_add"),
            _q(3, "Solve: 4.75 - 2.30 = ?", "2.45", role="application", skill_tag="dec_sub"),
            _q(4, "Help Kavya calculate: she bought a pen for Rs 12.50 and a notebook for Rs 35.75. Total cost?", "48.25",
               qtype="word_problem", role="application", skill_tag="dec_word"),
            _q(5, "Calculate 8.6 + 3.14.", "11.74", role="application", skill_tag="dec_add"),
            _q(6, "What goes in the blank? 5._2 + 1.48 = 7.00", "5",
               qtype="fill_blank", role="representation", skill_tag="dec_missing"),
            _q(7, "Is this correct? 3.2 + 1.5 = 4.7", "Yes, 3.2 + 1.5 = 4.7 is correct",
               qtype="error_detection", role="error_detection", skill_tag="dec_verify"),
            _q(8, "If a ribbon is 5.25 m and another is 3.50 m, what is the total length?", "8.75 m",
               qtype="word_problem", role="application", skill_tag="dec_word"),
            _mcq(9, "Which is greater: 0.5 or 0.50?", "They are equal",
                 ["0.5", "0.50", "They are equal", "Cannot tell"],
                 role="thinking", skill_tag="dec_compare"),
            _q(10, "Convert 3/10 to a decimal.", "0.3",
               role="representation", skill_tag="dec_convert"),
            _q(11, "Solve: 10.00 - 6.35 = ?", "3.65", role="application", skill_tag="dec_sub"),
            _q(12, "If you have Rs 50.00 and spend Rs 23.75, how much change?", "26.25",
                qtype="word_problem", role="application", skill_tag="dec_word"),
            _mcq(13, "Arrange in order: 0.8, 0.08, 0.80", "0.08, 0.8, 0.80",
                 ["0.08, 0.8, 0.80", "0.80, 0.8, 0.08", "0.8, 0.80, 0.08", "0.08, 0.80, 0.8"],
                 role="recognition", skill_tag="dec_order"),
            _q(14, "Given that 1 kg = 1000 g, write 250 g as a decimal in kg.", "0.250",
                role="application", skill_tag="dec_convert"),
            _q(15, "Imagine you have 3 coins of Rs 0.50 and 2 coins of Rs 0.25. How much money total?", "2.00",
                role="thinking", skill_tag="dec_word"),
        ],
    )


def _gold_c5_science_clean() -> dict:
    """Class 5 Science, 10Q, body systems. Expected: score>=70, released."""
    return _ws(
        grade="Class 5",
        subject="Science",
        topic="Human Body (Digestive System)",
        skill_focus="Understanding the journey of food through the digestive system",
        common_mistake="Thinking digestion only happens in the stomach",
        parent_tip="Trace the path of food on a diagram poster together",
        learning_objectives=["Name organs of the digestive system", "Describe the digestion process"],
        chapter_ref="NCERT Ch 3 - Body Systems",
        questions=[
            _mcq(1, "Where does digestion begin?", "Mouth",
                 ["Stomach", "Mouth", "Intestine", "Liver"], role="recognition", skill_tag="sci_digest"),
            _q(2, "Fill in: The ___ produces acid to break down food.", "stomach",
               qtype="fill_blank", role="application", skill_tag="sci_digest"),
            _q(3, "What is the role of saliva in digestion?", "Saliva breaks down starch into simpler sugars",
               role="application", skill_tag="sci_digest"),
            _q(4, "If someone cannot chew food properly, how does it affect digestion?",
               "Larger food pieces are harder to digest in the stomach",
               role="thinking", skill_tag="sci_reasoning"),
            _mcq(5, "Which organ absorbs nutrients from digested food?", "Small intestine",
                 ["Stomach", "Large intestine", "Small intestine", "Liver"],
                 role="recognition", skill_tag="sci_absorb"),
            _q(6, "Name the tube that connects the mouth to the stomach.", "Oesophagus (food pipe)",
               role="application", skill_tag="sci_anatomy"),
            _q(7, "Write True or False: The liver is part of the digestive system.", "True",
               qtype="true_false", role="application", skill_tag="sci_digest"),
            _q(8, "Can you spot the mistake? 'Food is digested only in the stomach.'",
               "Digestion begins in the mouth and continues in the intestines",
               qtype="error_detection", role="error_detection", skill_tag="sci_error"),
            _q(9, "Describe the path of an apple from mouth to intestine in 3 steps.",
               "1. Chewed in mouth 2. Broken down in stomach 3. Nutrients absorbed in small intestine",
               role="representation", skill_tag="sci_sequence"),
            _q(10, "Suppose you eat only junk food for a week. What might happen to your digestion?",
                "Stomach upset, poor nutrient absorption, constipation",
                role="thinking", skill_tag="sci_reasoning"),
        ],
    )


def _gold_c5_maths_blocked() -> dict:
    """Class 5 Maths, 10Q, duplicate questions + empty texts. Expected: score<30, blocked."""
    return _ws(
        grade="Class 5",
        subject="Maths",
        topic="Decimals",
        skill_focus="Decimal addition",
        common_mistake="Alignment errors",
        parent_tip="Use lined paper",
        learning_objectives=["Add decimals"],
        chapter_ref="NCERT Ch 10",
        questions=[
            _q(1, "Solve: 1.5 + 2.3 = ?", "3.8", role="application", skill_tag="dec_add"),
            _q(2, "Solve: 1.5 + 2.3 = ?", "3.8", role="application", skill_tag="dec_add"),  # exact duplicate
            _q(3, "", "5.0", role="application", skill_tag="dec_add"),  # empty text
            _q(4, "", "", role="application", skill_tag="dec_add"),  # empty text + empty answer
            _q(5, "Solve: 1.5 + 2.3 = ?", "3.8", role="application", skill_tag="dec_add"),  # triple duplicate
            _q(6, "Solve: 3.0 + 1.0 = ?", "4.0", role="application", skill_tag="dec_add"),
            _q(7, "Solve: 2.0 + 2.0 = ?", "4.0", role="application", skill_tag="dec_add"),
            _q(8, "Solve: 5.0 + 5.0 = ?", "10.0", role="application", skill_tag="dec_add"),
            _q(9, "", "7.0", role="application", skill_tag="dec_add"),  # empty text
            _q(10, "Solve: 4.0 + 3.0 = ?", "7.0", role="application", skill_tag="dec_add"),
        ],
    )


# ---------------------------------------------------------------------------
# Registry — maps fixture ID to (builder_fn, expected_outcomes)
# ---------------------------------------------------------------------------


GOLD_FIXTURES: dict[str, dict] = {
    "gold_c1_maths_clean": {
        "builder": _gold_c1_maths_clean,
        "min_score": 70, "max_score": 100,
        "expected_verdict": "released",
        "max_critical": 0,
    },
    "gold_c1_english_clean": {
        "builder": _gold_c1_english_clean,
        "min_score": 65, "max_score": 100,
        "expected_verdict": "released",
        "max_critical": 0,
    },
    "gold_c1_maths_degraded": {
        "builder": _gold_c1_maths_degraded,
        "min_score": 30, "max_score": 79,
        "expected_verdict": "best_effort",
        "max_critical": None,  # may have critical failures from missing fields
    },
    "gold_c2_maths_clean": {
        "builder": _gold_c2_maths_clean,
        "min_score": 65, "max_score": 100,
        "expected_verdict": "released",
        "max_critical": 0,
    },
    "gold_c2_hindi_clean": {
        "builder": _gold_c2_hindi_clean,
        "min_score": 60, "max_score": 100,
        "expected_verdict": "released",
        "max_critical": 0,
    },
    "gold_c2_maths_blocked": {
        "builder": _gold_c2_maths_blocked,
        "min_score": 0, "max_score": 40,
        "expected_verdict": "blocked",
        "max_critical": None,
    },
    "gold_c3_maths_clean": {
        "builder": _gold_c3_maths_clean,
        "min_score": 70, "max_score": 100,
        "expected_verdict": "released",
        "max_critical": 0,
    },
    "gold_c3_science_clean": {
        "builder": _gold_c3_science_clean,
        "min_score": 65, "max_score": 100,
        "expected_verdict": "released",
        "max_critical": 0,
    },
    "gold_c3_maths_warnings": {
        "builder": _gold_c3_maths_warnings,
        "min_score": 0, "max_score": 79,
        "expected_verdict": "best_effort",
        "max_critical": None,
    },
    "gold_c4_maths_clean": {
        "builder": _gold_c4_maths_clean,
        "min_score": 65, "max_score": 100,
        "expected_verdict": "released",
        "max_critical": 0,
    },
    "gold_c4_english_clean": {
        "builder": _gold_c4_english_clean,
        "min_score": 65, "max_score": 100,
        "expected_verdict": "released",
        "max_critical": 0,
    },
    "gold_c4_maths_degraded": {
        "builder": _gold_c4_maths_degraded,
        "min_score": 0, "max_score": 79,
        "expected_verdict": "best_effort",
        "max_critical": None,
    },
    "gold_c5_maths_clean": {
        "builder": _gold_c5_maths_clean,
        "min_score": 60, "max_score": 100,
        "expected_verdict": "released",
        "max_critical": 0,
    },
    "gold_c5_science_clean": {
        "builder": _gold_c5_science_clean,
        "min_score": 60, "max_score": 100,
        "expected_verdict": "released",
        "max_critical": 0,
    },
    "gold_c5_maths_blocked": {
        "builder": _gold_c5_maths_blocked,
        "min_score": 0, "max_score": 30,
        "expected_verdict": "blocked",
        "max_critical": None,
    },
}
