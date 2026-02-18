# GOLD_CLASS_SPEC.md — What Makes This Product Stand Out

## The Core Insight

Every free CBSE worksheet tool does the same thing:
generate N questions on a topic → export PDF.

Gold class means the worksheet itself is a teaching instrument —
not just a test. A parent or teacher picks it up and immediately thinks:
"This was made FOR my child, not just FOR this topic."

There are 7 dimensions that create that feeling. Each one is buildable on top
of your existing engine. None of them require a new pipeline.

---

## Dimension 1: Tiered Difficulty — "Can Every Child Start AND Be Challenged?"

### What average tools do
All questions at the same difficulty. A struggling child hits Q1 and gives up.
An advanced child finishes in 5 minutes and learns nothing new.

### What gold class does
Every worksheet has 3 visible tiers, labeled clearly:

```
⭐ Foundation (Q1–Q4)      → I can recall and recognise
⭐⭐ Application (Q5–Q8)    → I can use what I know
⭐⭐⭐ Stretch (Q9–Q10)      → I can think and reason
```

The tiers map directly to your existing slot types:
- Foundation = recognition + representation slots
- Application = application slots
- Stretch = error_detection + thinking slots

**What changes in the engine**: Nothing in the pipeline.
Only the PDF renderer and question ordering change.
Questions are sorted by tier, and tier labels are printed above each section.

### Agent Task: Gold-G1
```
Frontend Lead + Backend Lead:
Add tier grouping to worksheet PDF export and screen view.
- Sort questions: recognition/representation first, application middle, ED/thinking last
- Add visual tier headers: ⭐ Foundation / ⭐⭐ Application / ⭐⭐⭐ Stretch
- Add small "difficulty badge" to each question (1/2/3 stars)
- No change to question generation pipeline
Files: PDF export logic, worksheet view component
```

---

## Dimension 2: Personalised to Mastery State — "This Worksheet Knows My Child"

### What average tools do
Every child gets the same worksheet for "Addition".
A child who has mastered basic addition but struggles with carries gets the same sheet
as a child who hasn't even started.

### What gold class does
Your `mastery_state` table already tracks:
- `mastery_level`: unknown → learning → improving → mastered
- `last_error_type`: which specific misconception
- `streak`: how many correct in a row

Gold class uses this to personalise the slot plan:

```python
# If mastery_level == "mastered" for this topic:
#   → Increase thinking slot weight, reduce recognition
#   → Add cross-topic application (e.g., addition in a money context)

# If mastery_level == "learning":
#   → Increase recognition + representation slots
#   → Reduce thinking slot (don't overwhelm)
#   → Use simpler numbers

# If last_error_type == "carry_tens":
#   → Force 3+ questions with carry in tens column specifically
#   → Add a "watch out" hint on those questions
```

This is the single biggest differentiator. No free tool does this.
Vedantu, myCBSEguide, Tiwari Academy — none of them know what the child already knows.

### Agent Task: Gold-G2
```
Backend Lead (Slot Engine Agent):
Add mastery-aware slot plan modifier to run_slot_pipeline().

1. Before get_slot_plan(), check mastery_state for the child + topic
2. If mastery_level == "mastered": boost thinking slots by 1, reduce recognition by 1
3. If mastery_level == "learning": boost recognition by 1, reduce thinking to minimum (1)
4. If last_error_type is set: add targeted constraint to _build_slot_instruction()
   e.g., "FORCE at least 2 questions that specifically test carry in tens column"
5. If no mastery data: use default slot plan (current behaviour)

Files: backend/app/services/slot_engine.py, backend/app/api/worksheets_v1.py
Note: child_id must be passed to run_slot_pipeline() — add as optional param
```

---

## Dimension 3: Indian Context Word Problems — "This Feels Real to My Child"

### What average tools do
"Ram has 5 apples. He gives 3 to Shyam. How many apples does Ram have?"
Same generic context. Feels like it was written by someone who's never been to India.

### What gold class does
Word problems use contexts a Class 3 Indian child actually lives in:

**Rich context bank per topic:**
```
Money:      auto-rickshaw fares, chai stall change, mela (fair) shopping,
            Diwali gift money, school canteen
Time:       school bell timings, cricket match overs, train departure,
            prayer time, lunch break
Addition:   cricket runs scored, mango picking season, stamps collection,
            marbles game, rangoli dots
Subtraction: bus passengers, remaining rotis, rakhi money spent
Multiplication: rows of diyas in Diwali, legs of animals in a farm,
                packets of biscuits, seating in a cinema
Division:   sharing laddoos equally, splitting fare in an auto,
            distributing sweets on birthday
Fractions:  cutting a paratha, sharing pizza slices (for urban kids),
            portions of a rangoli design
```

These are passed as context seeds to the instruction builder so the LLM
uses them rather than generating generic "Ram and Shyam" problems.

### Agent Task: Gold-G3
```
Topic Builder Agent:
Add CONTEXT_BANK dict to slot_engine.py with 10+ rich Indian contexts per topic.

In _build_slot_instruction(), for application slot (word_problem format):
Add: "Choose ONE context from this list: {CONTEXT_BANK[topic]}
     Make the word problem feel real to an Indian Class 3 child.
     Use Indian names: Priya, Arjun, Meera, Ravi, Kavya, Dadi, Chacha.
     DO NOT use Ram, Shyam, or generic fruit/animal problems."

Verify: Run test_all_topics.py — check that word_problem questions reference
        Indian contexts. Manual spot-check 5 generated worksheets.
Files: backend/app/services/slot_engine.py
```

---

## Dimension 4: Rich Visual Quality — "This Looks Like a Pearson Book"

### What you have today
3 visual types: number_line, base_ten_regrouping, clock
These are good but limited. Most questions fall back to TEXT_ONLY.

### What gold class needs
A visual on every single question where a visual helps comprehension.
The bar should be: if a visual can make this question clearer, it must have one.

**New visual types needed:**
```
pie_fraction      → Fraction questions: circle divided into equal parts, shaded portion shown
grid_symmetry     → Symmetry: dot grid with shape, fold line shown
money_coins       → Money: actual coin/note images (₹1, ₹2, ₹5, ₹10, ₹50, ₹100)
ruler_length      → Measurement: ruler SVG with object to measure
pattern_tiles     → Patterns: coloured tile sequence with blank at end
abacus            → Place value: abacus with beads for H/T/O
number_grid       → Numbers to 10000: 100-square grid with highlighted cells
```

**Print quality standard:**
- All SVGs must render crisply at 300dpi (print-safe)
- Black and white friendly (no colour-only encoding of meaning)
- Consistent visual style across all types (same stroke width, fonts, spacing)
- Every visual has an accessible text description (for screen readers)

### Agent Task: Gold-G4
```
Component Agent (Frontend) + Slot Engine Agent (Backend):

Backend:
- Add new visual types to hydrate_visuals(): pie_fraction, grid_symmetry,
  money_coins, pattern_tiles, abacus
- Update hydration rules:
  fraction_number format → pie_fraction visual
  symmetry_question format → grid_symmetry visual
  money_question format → money_coins visual
  shape_pattern format → pattern_tiles visual
  place_value format → abacus visual

Frontend:
- Build SVG components for each new visual type
- All SVGs: print-safe, B&W friendly, consistent style
- Add @media print CSS to ensure visuals render at correct size

Target: Visual coverage ≥ 95% (up from current 80%)
Files: slot_engine.py hydrate_visuals(), frontend/src/components/
```

---

## Dimension 5: Learning Objective Header — "I Know What My Child Is Practising"

### What average tools do
Title: "Class 3 Maths Worksheet"
Parent has no idea what skill is being tested.

### What gold class does
Every worksheet has a clear, parent-friendly learning objective:

```
┌─────────────────────────────────────────────────────┐
│  📚 Today's Learning Goal                           │
│  After completing this worksheet, [Child's Name]    │
│  will be able to:                                   │
│  ✓ Add 3-digit numbers where carrying is needed     │
│  ✓ Spot common addition mistakes and fix them       │
│  ✓ Solve real-life addition word problems           │
└─────────────────────────────────────────────────────┘
```

Generated deterministically from the topic + slot types present.
No LLM call — hardcoded templates per topic.

### Agent Task: Gold-G5
```
Backend Lead:
Add LEARNING_OBJECTIVES dict to slot_engine.py:

LEARNING_OBJECTIVES = {
    "Addition (carries)": [
        "Add 3-digit numbers where carrying is needed",
        "Spot common addition mistakes and fix them",
        "Solve real-life addition word problems",
    ],
    "Subtraction (borrowing)": [...],
    ... (all 12 topics)
}

Add learning_objectives field to worksheet API response.
Frontend: render as styled header box at top of worksheet and PDF.
Files: slot_engine.py, worksheets_v1.py response schema, worksheet view component
```

---

## Dimension 6: Hint System — "A Nudge, Not an Answer"

### What average tools do
No hints. Child is stuck. Frustration. Parents give up.

### What gold class does
Every thinking and error_detection question has a collapsible hint.
Not the answer — a metacognitive nudge that teaches strategy.

```
Q9. [Thinking question]
    ▶ Hint (tap to reveal): "Think about what happens when the 
      ones column adds up to more than 9. Where does the extra go?"

Q10. [Error detection]
     ▶ Hint (tap to reveal): "Check each column carefully. 
       Is the carry being added in the right place?"
```

The hint is generated by the existing `_fill_role_explanations()` function
(already in your engine, capped at 160 chars) but currently only visible
in the role_explanation field, not surfaced in the UI.

**What changes**: Only the frontend. The data already exists.

### Agent Task: Gold-G6
```
Frontend Lead (UX Flow Agent):
Surface role_explanation as a collapsible hint on worksheet view.

1. For questions where role_explanation is non-empty (thinking + error_detection slots):
   - Show "💡 Hint" button below the question
   - On click/tap: reveal the role_explanation text
   - On PDF export: print hint in a light grey box below the question (collapsed by default)
     with instruction "Hint: [text] (ask a parent if you're stuck)"
2. In print mode: hints are visible but styled subtly (grey, smaller font)

Files: frontend/src/components/ worksheet view, PDF export
No backend changes needed — role_explanation already in API response.
```

---

## Dimension 7: Parent Insight Footer — "Tell Me What to Do Next"

### What average tools do
Worksheet ends. Parent has no idea if child did well or what to do next.

### What gold class does
Every worksheet has a footer (shown after submission/grading):

```
┌─────────────────────────────────────────────────────────┐
│  📊 For Parents: What to Watch For                      │
│                                                         │
│  If your child struggled with Q7–Q9, they may be        │
│  confusing the tens and ones columns when carrying.     │
│                                                         │
│  ➜ Next step: Try the "Addition - Place Value Focus"    │
│    worksheet, or practise carrying with physical        │
│    objects (coins, blocks) before the next session.     │
│                                                         │
│  Mastery so far: ████████░░ Improving (streak: 3 ✓)    │
└─────────────────────────────────────────────────────────┘
```

Generated from the mastery engine — `mastery_level`, `last_error_type`, `streak`.
The "Next step" recommendation comes from the existing `recommend_next()` method
in the skill contract base class (already in your code, not yet surfaced in UI).

### Agent Task: Gold-G7
```
Backend Lead + Frontend Lead:
Surface mastery insights as parent footer after worksheet grading.

Backend (worksheets_v1.py):
- After grading, include in response:
  {
    "insight": {
      "mastery_level": "improving",
      "streak": 3,
      "watch_for": "...",   ← generated from last_error_type lookup table
      "next_step": "...",   ← from recommend_next() in skill contract
    }
  }
- Add WATCH_FOR_MESSAGES dict: maps error_type → parent-friendly explanation
- Add NEXT_STEP_MESSAGES dict: maps topic + mastery_level → next recommendation

Frontend:
- Show insight footer after worksheet is submitted/graded
- Render mastery progress bar (████████░░ style)
- "Next step" links directly to a new worksheet generation with recommended topic

Files: worksheets_v1.py, frontend worksheet submission flow
```

---

## Gold Class PDF Design Standard

The PDF itself must look premium. Reference: Pearson/Oxford primary workbooks.

**Layout rules:**
- Clean white background, generous margins (2cm all sides)
- Child's name field at top: "Name: _____________ Date: ___________ Score: ___/10"
- School name field (if teacher account): "School: _____________________"
- Topic + learning objective header (Dimension 5)
- Tier section headers (Dimension 1)
- Questions: clear numbering, adequate answer space (ruled lines, not just a blank)
- Hints in light grey below thinking/ED questions (Dimension 6)
- Visual elements: crisp SVG at 300dpi equivalent
- Footer: page number, website URL (branding)
- Font: Use a clean, child-friendly sans-serif (Nunito or Poppins via Google Fonts)

### Agent Task: Gold-G8
```
Frontend Lead (Component Agent):
Redesign PDF export to match premium layout standard.

1. Add Name/Date/Score header fields
2. Add school name field (shown for teacher accounts only)
3. Implement tier section headers (from Gold-G1)
4. Add adequate answer space: 3 ruled lines for text answers, box for numeric
5. Implement Nunito/Poppins font (load via @import in print CSS)
6. Add footer with page number + branding
7. Test print output at A4 size

Files: frontend PDF export component, print CSS
```

---

## Gold Class Rollout — Add to ORCHESTRATOR.md as Phase 9

These 8 tasks are interdependent in this order:
```
Gold-G5 (learning objective) → can ship independently, quick win
Gold-G6 (hints)              → can ship independently, data already exists
Gold-G1 (tiered layout)      → requires Gold-G8 (PDF redesign)
Gold-G8 (PDF redesign)       → foundational, do first
Gold-G3 (Indian contexts)    → independent, high visual impact
Gold-G2 (mastery-aware)      → requires mastery data to be flowing (Phase 4 first)
Gold-G4 (rich visuals)       → most effort, do after Gold-G8
Gold-G7 (parent insight)     → requires Gold-G2 + grading flow working
```

**Recommended sequence:**
1. Gold-G8 (PDF redesign) — changes how everything looks
2. Gold-G5 (learning objective header) — quick win, huge perceived value
3. Gold-G6 (hint system) — data exists, just surface it
4. Gold-G1 (tiered layout) — builds on G8
5. Gold-G3 (Indian contexts) — pure prompt change, zero risk
6. Gold-G4 (rich visuals) — biggest effort, highest wow factor
7. Gold-G2 (mastery-aware slots) — requires Phase 4 mastery data flowing
8. Gold-G7 (parent insight footer) — capstone feature, requires G2

---

## Competitive Positioning After Gold Class

| Feature | Vedantu/myCBSEguide | Your product (today) | Your product (Gold Class) |
|---|---|---|---|
| CBSE-aligned questions | ✅ | ✅ | ✅ |
| Slot-typed question mix | ❌ | ✅ | ✅ |
| Tiered difficulty per sheet | ❌ | ❌ | ✅ |
| Mastery-personalised | ❌ | partial | ✅ |
| Indian context word problems | ❌ | ❌ | ✅ |
| Rich SVG visuals (7+ types) | ❌ | 3 types | ✅ |
| Learning objective on sheet | ❌ | ❌ | ✅ |
| Hint system | ❌ | data exists | ✅ |
| Parent insight after grading | ❌ | ❌ | ✅ |
| Premium PDF design | ❌ | average | ✅ |

At Gold Class completion, there is no comparable free tool.
The closest paid competitor is Cuemath (₹2,000+/month for live tutoring).
Your product at ₹299/month with Gold Class worksheets is an obvious upgrade
for any parent who wants quality without the tutoring cost.
