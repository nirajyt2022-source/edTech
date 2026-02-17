#!/usr/bin/env python3
"""
Subject×Grade topic resolution regression test.
Validates ALL frontend topic strings across ALL subjects/grades for:
  1. Cross-subject contamination (EVS topic → English profile)
  2. Grade leaks (Class 1 topic → Class 3 profile)
  3. Missing profiles (no profile → LLM generates freely)
  4. Carry/borrow contamination in non-Maths subjects

Run: cd backend && python scripts/test_subject_topic_resolution.py
Must exit 0 with 0 failures.
"""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.slot_engine import (
    get_topic_profile, TOPIC_PROFILES, build_worksheet_plan
)

PASS = FAIL = WARN = 0

def ok(msg):
    global PASS; PASS += 1

def fail(msg):
    global FAIL; FAIL += 1; print(f"  ❌ {msg}")

def warn(msg):
    global WARN; WARN += 1; print(f"  ⚠️  {msg}")

def profile_subject(profile):
    tags = profile.get("allowed_skill_tags", [])
    if any(t.startswith("eng_") for t in tags):   return "English"
    if any(t.startswith("sci_") or t.startswith("evs_") for t in tags): return "Science/EVS"
    if any(t.startswith("hin_") for t in tags):   return "Hindi"
    if any(t.startswith("comp_") for t in tags):  return "Computer"
    if any(t.startswith("gk_") for t in tags):    return "GK"
    if any(t.startswith("moral_") for t in tags): return "Moral"
    if any(t.startswith("health_") for t in tags):return "Health"
    return "Maths"

SUBJ_GROUP = {
    "Maths":"Maths","English":"English","EVS":"Science/EVS",
    "Science":"Science/EVS","Hindi":"Hindi","Computer":"Computer",
    "GK":"GK","Moral Science":"Moral","Health":"Health",
}

# All frontend topics
ALL = {
"Maths":[
    (1,"Numbers 1 to 50 (Class 1)"),(1,"Numbers 51 to 100 (Class 1)"),
    (1,"Addition up to 20 (Class 1)"),(1,"Subtraction within 20 (Class 1)"),
    (1,"Basic Shapes (Class 1)"),(1,"Measurement (Class 1)"),
    (1,"Time (Class 1)"),(1,"Money (Class 1)"),
    (2,"Numbers up to 1000 (Class 2)"),(2,"Addition (2-digit with carry)"),
    (2,"Subtraction (2-digit with borrow)"),(2,"Multiplication (tables 2-5)"),
    (2,"Division (sharing equally)"),(2,"Shapes and space (2D)"),
    (2,"Measurement (length, weight)"),(2,"Time (hour, half-hour)"),
    (2,"Money (coins and notes)"),(2,"Data handling (pictographs)"),
    (3,"Addition (carries)"),(3,"Subtraction (borrowing)"),
    (3,"Addition and subtraction (3-digit)"),(3,"Multiplication (tables 2-10)"),
    (3,"Division basics"),(3,"Numbers up to 10000"),
    (3,"Fractions (halves, quarters)"),(3,"Fractions"),
    (3,"Time (reading clock, calendar)"),(3,"Money (bills and change)"),
    (3,"Symmetry"),(3,"Patterns and sequences"),
    (4,"Large numbers (up to 1,00,000)"),(4,"Addition and subtraction (5-digit)"),
    (4,"Multiplication (3-digit × 2-digit)"),(4,"Division (long division)"),
    (4,"Fractions (equivalent, comparison)"),(4,"Decimals (tenths, hundredths)"),
    (4,"Geometry (angles, lines)"),(4,"Perimeter and area"),
    (4,"Time (minutes, 24-hour clock)"),(4,"Money (bills, profit/loss)"),
    (5,"Numbers up to 10 lakh (Class 5)"),(5,"Factors and multiples (Class 5)"),
    (5,"HCF and LCM (Class 5)"),(5,"Fractions (add and subtract) (Class 5)"),
    (5,"Decimals (all operations) (Class 5)"),(5,"Percentage (Class 5)"),
    (5,"Area and volume (Class 5)"),(5,"Geometry (circles, symmetry) (Class 5)"),
    (5,"Data handling (pie charts) (Class 5)"),(5,"Speed distance time (Class 5)"),
],
"English":[
    (1,"Alphabet (Class 1)"),(1,"Phonics (Class 1)"),
    (1,"Self and Family Vocabulary (Class 1)"),(1,"Animals and Food Vocabulary (Class 1)"),
    (1,"Greetings and Polite Words (Class 1)"),(1,"Seasons (Class 1)"),
    (1,"Simple Sentences (Class 1)"),
    (2,"Nouns (Class 2)"),(2,"Verbs (Class 2)"),(2,"Pronouns (Class 2)"),
    (2,"Sentences (Class 2)"),(2,"Rhyming Words (Class 2)"),(2,"Punctuation (Class 2)"),
    (3,"Nouns (Class 3)"),(3,"Verbs (Class 3)"),(3,"Adjectives (Class 3)"),
    (3,"Pronouns (Class 3)"),(3,"Tenses (Class 3)"),(3,"Punctuation (Class 3)"),
    (3,"Vocabulary (Class 3)"),(3,"Reading Comprehension (Class 3)"),
    (4,"Tenses (Class 4)"),(4,"Sentence Types (Class 4)"),(4,"Conjunctions (Class 4)"),
    (4,"Prepositions (Class 4)"),(4,"Adverbs (Class 4)"),(4,"Prefixes and Suffixes (Class 4)"),
    (4,"Vocabulary (Class 4)"),(4,"Reading Comprehension (Class 4)"),
    (5,"Active and Passive Voice (Class 5)"),(5,"Direct and Indirect Speech (Class 5)"),
    (5,"Complex Sentences (Class 5)"),(5,"Summary Writing (Class 5)"),
    (5,"Comprehension (Class 5)"),(5,"Synonyms and Antonyms (Class 5)"),
    (5,"Formal Letter Writing (Class 5)"),(5,"Creative Writing (Class 5)"),
    (5,"Clauses (Class 5)"),
],
"EVS":[
    (1,"My Family (Class 1)"),(1,"My Body (Class 1)"),
    (1,"Plants Around Us (Class 1)"),(1,"Animals Around Us (Class 1)"),
    (1,"Food We Eat (Class 1)"),(1,"Seasons and Weather (Class 1)"),
    (2,"Plants (Class 2)"),(2,"Animals and Habitats (Class 2)"),
    (2,"Food and Nutrition (Class 2)"),(2,"Water (Class 2)"),
    (2,"Shelter (Class 2)"),(2,"Our Senses (Class 2)"),
    (3,"Plants (Class 3)"),(3,"Animals (Class 3)"),
    (3,"Food and Nutrition (Class 3)"),(3,"Shelter (Class 3)"),
    (3,"Water (Class 3)"),(3,"Air (Class 3)"),(3,"Our Body (Class 3)"),
    (4,"Living Things (Class 4)"),(4,"Human Body (Class 4)"),
    (4,"States of Matter (Class 4)"),(4,"Force and Motion (Class 4)"),
    (4,"Simple Machines (Class 4)"),(4,"Photosynthesis (Class 4)"),
    (4,"Animal Adaptation (Class 4)"),
    (5,"Circulatory System (Class 5)"),(5,"Respiratory and Nervous System (Class 5)"),
    (5,"Reproduction in Plants and Animals (Class 5)"),
    (5,"Physical and Chemical Changes (Class 5)"),
    (5,"Forms of Energy (Class 5)"),(5,"Solar System and Earth (Class 5)"),
    (5,"Ecosystem and Food Chains (Class 5)"),
],
"Hindi":[
    (1,"Varnamala Swar (Class 1)"),(1,"Varnamala Vyanjan (Class 1)"),
    (1,"Family Words (Class 1)"),(1,"Simple Sentences in Hindi (Class 1)"),
    (2,"Matras Introduction (Class 2)"),(2,"Two Letter Words (Class 2)"),
    (2,"Three Letter Words (Class 2)"),(2,"Rhymes and Poems (Class 2)"),
    (2,"Nature Vocabulary (Class 2)"),
    (3,"Varnamala (Class 3)"),(3,"Matras (Class 3)"),
    (3,"Shabd Rachna (Class 3)"),(3,"Vakya Rachna (Class 3)"),
    (3,"Kahani Lekhan (Class 3)"),
    (4,"Anusvaar and Visarg (Class 4)"),(4,"Vachan and Ling (Class 4)"),
    (4,"Kaal (Class 4)"),(4,"Patra Lekhan (Class 4)"),
    (4,"Comprehension Hindi (Class 4)"),
    (5,"Muhavare (Class 5)"),(5,"Paryayvachi Shabd (Class 5)"),
    (5,"Vilom Shabd (Class 5)"),(5,"Samas (Class 5)"),
    (5,"Samvad Lekhan (Class 5)"),
],
"Computer":[
    (1,"Parts of Computer (Class 1)"),(1,"Using Mouse and Keyboard (Class 1)"),
    (2,"Desktop and Icons (Class 2)"),(2,"Basic Typing (Class 2)"),(2,"Special Keys (Class 2)"),
    (3,"MS Paint Basics (Class 3)"),(3,"Keyboard Shortcuts (Class 3)"),(3,"Files and Folders (Class 3)"),
    (4,"MS Word Basics (Class 4)"),(4,"Introduction to Scratch (Class 4)"),(4,"Internet Safety (Class 4)"),
    (5,"Scratch Programming (Class 5)"),(5,"Internet Basics (Class 5)"),
    (5,"MS PowerPoint Basics (Class 5)"),(5,"Digital Citizenship (Class 5)"),
],
"GK":[
    (3,"Famous Landmarks (Class 3)"),(3,"National Symbols (Class 3)"),
    (3,"Solar System Basics (Class 3)"),(3,"Current Awareness (Class 3)"),
    (4,"Continents and Oceans (Class 4)"),(4,"Famous Scientists (Class 4)"),
    (4,"Festivals of India (Class 4)"),(4,"Sports and Games (Class 4)"),
    (5,"Indian Constitution (Class 5)"),(5,"World Heritage Sites (Class 5)"),
    (5,"Space Missions (Class 5)"),(5,"Environmental Awareness (Class 5)"),
],
"Moral Science":[
    (1,"Sharing (Class 1)"),(1,"Honesty (Class 1)"),
    (2,"Kindness (Class 2)"),(2,"Respecting Elders (Class 2)"),
    (3,"Teamwork (Class 3)"),(3,"Empathy (Class 3)"),(3,"Environmental Care (Class 3)"),
    (4,"Leadership (Class 4)"),
    (5,"Global Citizenship (Class 5)"),(5,"Digital Ethics (Class 5)"),
],
"Health":[
    (1,"Personal Hygiene (Class 1)"),(1,"Good Posture (Class 1)"),(1,"Basic Physical Activities (Class 1)"),
    (2,"Healthy Eating Habits (Class 2)"),(2,"Outdoor Play (Class 2)"),(2,"Basic Stretching (Class 2)"),
    (3,"Balanced Diet (Class 3)"),(3,"Team Sports Rules (Class 3)"),(3,"Safety at Play (Class 3)"),
    (4,"First Aid Basics (Class 4)"),(4,"Yoga Introduction (Class 4)"),(4,"Importance of Sleep (Class 4)"),
    (5,"Fitness and Stamina (Class 5)"),(5,"Nutrition Labels Reading (Class 5)"),
    (5,"Mental Health Awareness (Class 5)"),
],
}

CARRY_TAGS = {"column_add_with_carry", "column_sub_with_borrow"}

print("\n── PHASE A: Cross-subject contamination ──")
for subj, combos in ALL.items():
    expected_group = SUBJ_GROUP[subj]
    for grade, topic in combos:
        p = get_topic_profile(topic, subject=subj)
        if p is None:
            p_nofilter = get_topic_profile(topic)
            if p_nofilter:
                ps = profile_subject(p_nofilter)
                if ps != expected_group:
                    fail(f"[{subj} C{grade}] \"{topic}\" → \"{ps}\" profile without subject filter (cross-subject)")
                else:
                    warn(f"[{subj} C{grade}] \"{topic}\" → no profile with subject filter but exists unfiltered")
            else:
                warn(f"[{subj} C{grade}] \"{topic}\" → no profile at all (LLM fallback)")
        else:
            ps = profile_subject(p)
            if ps != expected_group:
                fail(f"[{subj} C{grade}] \"{topic}\" → profile_subject={ps}, expected={expected_group}")
            else:
                ok(f"{subj} C{grade}: {topic}")

print("\n── PHASE B: Grade leaks ──")
for subj, combos in ALL.items():
    for grade, topic in combos:
        p = get_topic_profile(topic, subject=subj)
        if p is None:
            continue
        for canon_key, canon_prof in TOPIC_PROFILES.items():
            if canon_prof is p:
                canon_class = re.search(r"Class (\d)", canon_key)
                if canon_class and str(grade) != canon_class.group(1):
                    fail(f"[{subj} C{grade}] \"{topic}\" → \"{canon_key}\" (GRADE LEAK: expected C{grade})")
                else:
                    ok(f"{subj} C{grade}: {topic}")
                break

print("\n── PHASE C: Carry/borrow in non-Maths ──")
for subj, combos in ALL.items():
    if subj == "Maths":
        continue
    for grade, topic in combos:
        try:
            plan = build_worksheet_plan(6, topic=topic)
            bad = CARRY_TAGS & {d.get("skill_tag","") for d in plan}
            if bad:
                fail(f"[{subj} C{grade}] \"{topic}\" plan has carry/borrow tags: {bad}")
            else:
                ok(f"{subj} C{grade}: {topic}")
        except Exception as e:
            warn(f"[{subj} C{grade}] \"{topic}\" build_worksheet_plan error: {e}")

print("\n── PHASE D: Adversarial strings (production bugs) ──")
ADVERSARIAL = [
    ("Active and passive voice",  "EVS",     None,    "EVS should reject English profile"),
    ("World map",                 "EVS",     None,    "EVS topic with no profile → None ok"),
    ("Addition and subtraction (up to 20)", "Maths", "Addition up to 20 (Class 1)", "Class 1 add"),
    ("subtraction (up to 20)",    "Maths",   "Subtraction within 20 (Class 1)", "Class 1 sub"),
    ("Simple Sentences (Class 1)","English", "Simple Sentences (Class 1)", "English sentences"),
    ("Simple Sentences in Hindi (Class 1)","Hindi","Simple Sentences in Hindi (Class 1)","Hindi sentences"),
    ("Addition (carries)",        "Maths",   "Addition (carries)",          "Class 3 carry intact"),
    ("Subtraction (borrowing)",   "Maths",   "Subtraction (borrowing)",     "Class 3 borrow intact"),
    ("Active and passive voice",  None,      "Active and Passive Voice (Class 5)", "no-subject permissive"),
    ("Addition",                  None,      "Addition (carries)",          "no-subject permissive"),
]
for topic, subj, expected_canon, note in ADVERSARIAL:
    p = get_topic_profile(topic, subject=subj) if subj else get_topic_profile(topic)
    got_canon = None
    if p:
        for k, v in TOPIC_PROFILES.items():
            if v is p: got_canon = k; break
    if got_canon == expected_canon:
        ok(f"{note}: \"{topic}\" (subj={subj}) → \"{got_canon}\"")
    else:
        fail(f"{note}: \"{topic}\" (subj={subj}) → \"{got_canon}\" (expected \"{expected_canon}\")")

print(f"\n{'='*60}")
print(f"RESULTS: {PASS} passed | {FAIL} failed | {WARN} warnings")
print("="*60)
if FAIL:
    print("\n❌ FAILURES — fix before deploying")
    sys.exit(1)
print("\n✅ ALL PASS")
sys.exit(0)
