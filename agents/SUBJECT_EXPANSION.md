# SUBJECT_EXPANSION.md — Extending the Engine Beyond Maths

## Current Engine State (Honest Assessment)

The slot engine is a Maths engine that CAN become a multi-subject engine.
The pipeline architecture (slots, retries, mastery, validation) is universal.
The content layer (formats, instruction builders, answer normalizers) is Maths-only today.

Think of it like this:
- The FACTORY is universal ✅
- The MOULDS are Maths-only ❌ (need new moulds per subject)

---

## What Needs to Change Per New Subject

### Layer 1: New Question Formats (in VALID_FORMATS dict)
Each subject needs its own set of format names per slot type.

**English formats needed:**
```python
# recognition slot
"identify_noun", "identify_verb", "identify_adjective",
"punctuation_mark", "singular_plural", "gender_word",
"rhyming_word", "syllable_count", "word_meaning"

# application slot  
"fill_in_blank", "make_sentence", "rearrange_words",
"match_the_following", "complete_the_story", "answer_in_sentence"

# representation slot
"word_family", "word_ladder", "prefix_suffix", "compound_word"

# error_detection slot
"error_spot"  # same format, but grammar/spelling errors not arithmetic

# thinking slot
"thinking", "multi_step"  # reusable as-is
```

**Science formats needed (Class 3):**
```python
# recognition slot
"identify_organ", "identify_material", "living_nonliving",
"label_diagram", "true_false", "match_function"

# application slot
"explain_why", "what_happens_if", "give_example",
"classify_objects", "compare_two"

# representation slot
"fill_diagram", "sequence_steps", "cause_effect"

# error_detection slot
"error_spot"  # factual errors, not arithmetic

# thinking slot
"thinking", "multi_step"
```

---

### Layer 2: Subject-Aware VALID_FORMATS dict

Currently the dict is flat (one set of formats for all topics).
It needs to become subject-aware:

```python
# CURRENT (Maths-only, flat dict)
VALID_FORMATS = {
    "recognition": {"column_setup", "place_value", ...},
    "application": {"word_problem", "sequence_question", ...},
    ...
}

# NEEDED (subject-aware dict)
VALID_FORMATS_BY_SUBJECT = {
    "Mathematics": {
        "recognition": {"column_setup", "place_value", ...},
        "application": {"word_problem", ...},
        ...
    },
    "English": {
        "recognition": {"identify_noun", "identify_verb", ...},
        "application": {"fill_in_blank", "make_sentence", ...},
        ...
    },
    "Science": {
        "recognition": {"identify_organ", "living_nonliving", ...},
        "application": {"explain_why", "give_example", ...},
        ...
    }
}
```

The pipeline then calls:
```python
valid_formats = VALID_FORMATS_BY_SUBJECT.get(subject, VALID_FORMATS_BY_SUBJECT["Mathematics"])
```

---

### Layer 3: New Topic Profiles Per Subject

Same structure as Maths TOPIC_PROFILES, but per subject.

**English Class 3 topics to add:**
```python
TOPIC_PROFILES_ENGLISH = {
    "Nouns": {
        "allowed_skill_tags": ["identify_noun", "common_proper", "gender"],
        "allowed_slot_types": ["recognition", "application", "representation", "error_detection", "thinking"],
        "disallowed_keywords": ["calculate", "add", "subtract", "multiply"],
        "default_recipe": {"recognition": 2, "application": 4, "representation": 2, "error_detection": 1, "thinking": 1},
    },
    "Verbs": { ... },
    "Adjectives": { ... },
    "Sentences": { ... },
    "Punctuation": { ... },
    "Reading Comprehension": { ... },
    "Rhymes and Poetry": { ... },
    "Tenses (present/past)": { ... },
}
```

**Science Class 3 topics to add:**
```python
TOPIC_PROFILES_SCIENCE = {
    "Plants": {
        "allowed_skill_tags": ["parts_of_plant", "photosynthesis", "types_of_plants"],
        "disallowed_keywords": ["add", "subtract", "multiply", "fraction"],
        "default_recipe": {"recognition": 2, "application": 4, "representation": 2, "error_detection": 1, "thinking": 1},
    },
    "Animals": { ... },
    "Food and Nutrition": { ... },
    "Shelter": { ... },
    "Water": { ... },
    "Air": { ... },
    "Our Body": { ... },
}
```

---

### Layer 4: Answer Normalizers for Text Answers

Currently normalizers assume numeric answers.
English/Science need text answer normalizers:

```python
def normalize_text_answer(answer: str) -> str:
    """Normalize text answers: strip, title-case proper nouns, handle lists."""
    if not answer:
        return ""
    answer = answer.strip()
    # Remove trailing punctuation
    answer = answer.rstrip('.,;:')
    # If answer is a list (comma-separated), sort and rejoin for dedup consistency
    if ',' in answer and len(answer) < 100:
        parts = [p.strip() for p in answer.split(',')]
        answer = ', '.join(sorted(parts))
    return answer

def normalize_error_spot_text(answer: str) -> str:
    """Extract the corrected word/phrase from LLM explanatory text for English error_spot."""
    # Look for "The error is X" or "Correct: X" patterns
    patterns = [
        r"correct(?:ed)?\s+(?:word|answer|form)\s+is\s+['\"]?(\w+)['\"]?",
        r"should be\s+['\"]?(\w+)['\"]?",
        r"correct:\s+['\"]?(.+?)['\"]?$",
    ]
    for pattern in patterns:
        match = re.search(pattern, answer, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return answer.strip()
```

---

### Layer 5: Subject-Aware Validator

The per-question validator currently checks for numeric-specific patterns.
It needs a `subject` parameter:

```python
def validate_question(question: dict, subject: str = "Mathematics") -> list[str]:
    errors = []
    
    # Universal checks (all subjects)
    if len(question.get("question_text", "")) < 10:
        errors.append("question_text too short")
    if not question.get("answer"):
        errors.append("answer is empty")
    
    # Maths-specific checks
    if subject == "Mathematics":
        if question["slot_type"] == "error_detection":
            # Must have 2 numbers and error language
            ...
        if question["slot_type"] == "representation":
            # Must have blank markers
            ...
    
    # English-specific checks
    elif subject == "English":
        if question["slot_type"] == "error_detection":
            # Must reference a word or sentence, not numbers
            text = question.get("question_text", "")
            if not any(w in text.lower() for w in ["sentence", "word", "spelling", "grammar", "punctuation"]):
                errors.append("English error_spot must reference language error")
    
    return errors
```

---

### Layer 6: New Instruction Builders Per Topic

Each English/Science topic needs its own block in `_build_slot_instruction()`.

**English "Nouns" example:**
```python
if topic == "Nouns":
    if slot_type == "recognition":
        return """Generate a recognition question about nouns for CBSE Class 3.
SLOT FORMAT: identify_noun or singular_plural or gender_word
VERIFY: Question must ask student to identify, name, or classify a noun.
DO NOT use: arithmetic, numbers, fractions.
DO NOT repeat the same noun or sentence structure."""

    elif slot_type == "application":
        return """Generate an application question about nouns.
SLOT FORMAT: fill_in_blank or make_sentence or match_the_following  
VERIFY: Question requires student to USE a noun correctly in context.
Example: 'Fill in the blank: The ___ (dog/run/happy) barked loudly.'
DO NOT repeat the same sentence frame."""
```

---

## Implementation Plan (Add to Agents)

### Phase 7: English Language Engine (2 weeks)

**Task 7A — Backend Lead: Refactor VALID_FORMATS to subject-aware dict**
```
Files: backend/app/services/slot_engine.py
Changes:
- Replace flat VALID_FORMATS with VALID_FORMATS_BY_SUBJECT
- Add subject parameter to validate_question()
- Add subject parameter to _build_slot_instruction()
- Pass subject through run_slot_pipeline()
Impact: Zero change to Maths behaviour (Maths is the default)
```

**Task 7B — Topic Builder: Add English Class 3 topic profiles**
```
Files: backend/app/services/slot_engine.py
Add: TOPIC_PROFILES_ENGLISH dict with 8 topics
Add: English topic aliases
Add: English topic constraints
Add: English instruction builder blocks
```

**Task 7C — Backend Lead: Add text answer normalizers**
```
Files: backend/app/services/slot_engine.py
Add: normalize_text_answer()
Add: normalize_error_spot_text()
Wire into validate_question() when subject == "English"
```

**Task 7D — QA Lead: English topic test suite**
```
Files: backend/scripts/test_english_topics.py (new)
Test: 8 English topics × {5,10,15,20} = 32 combinations
All must pass. Script exits 0 on success.
```

**Task 7E — Frontend Lead: Add English to subject selector UI**
```
Files: frontend/src/pages/ (worksheet generation page)
Add: "English" option to subject dropdown
Add: English topic list from /api/cbse-syllabus/ or hardcoded
```

---

### Phase 8: Science Engine (1 week, builds on Phase 7)

**Task 8A — Topic Builder: Add Science Class 3 topic profiles**
```
Same pattern as English but for Science topics:
Plants, Animals, Food and Nutrition, Shelter, Water, Air, Our Body
```

**Task 8B — QA Lead: Science topic test suite**
```
Files: backend/scripts/test_science_topics.py (new)
Test: 7 Science topics × {5,10,15,20} = 28 combinations
```

**Task 8C — Frontend: Add Science to subject selector**

---

## Add These Phases to ORCHESTRATOR.md

When the orchestrator finishes Phase 6, it should pick up Phase 7 next.
Add this block to ORCHESTRATOR.md human checkpoints:

```
BEFORE PHASE 7 — Ask human:
"Ready to add English Language support.
This requires refactoring VALID_FORMATS to be subject-aware.
The Maths engine will NOT be affected — it stays as the default.
Confirm you want to proceed?"
```

---

## Effort Estimate

| Phase | Subject | Topics | Effort |
|---|---|---|---|
| Done | Maths Class 3 | 12 topics | ✅ |
| Phase 3 | Maths Class 2 | 10 topics | ~2 days |
| Phase 3 | Maths Class 4 | 10 topics | ~2 days |
| Phase 7 | English Class 3 | 8 topics | ~1 week (refactor needed) |
| Phase 8 | Science Class 3 | 7 topics | ~3 days (builds on Phase 7) |
| Future | Maths Class 5 | 12 topics | ~2 days |
| Future | English Class 4-5 | 8 topics each | ~2 days each |
| Future | Hindi | — | Separate project (Arabic text complexity) |

**Total to full Class 3 (all 3 subjects): ~2 weeks of agent work after Phase 6**

---

## The Key Insight

Your mastery engine, slot plan, pipeline, DB schema, and API — all of it works for every subject.
You only need to teach the engine the LANGUAGE of each new subject:
- What formats exist
- What valid questions look like
- How to build instructions per topic
- How to normalize answers

Once you've done English, Science takes 3 days because the refactor is already done.
Once you've done Class 3 for all subjects, every additional class takes ~2 days because
the subject patterns are already established.

The engine compounds. The first subject expansion is the hardest.
