Great questions — this is **exactly the right moment** to tighten scope and process.
I’ll answer in **three parts**, then give you a **clean Phase 2–only PRD (Claude-ready)** with **UI changes explicitly included** and **multi-subject excluded**.

---

## 1️⃣ Did I include UI changes earlier?

**Partially, but not explicitly enough.**
You’re right to call this out.

Earlier:

* UI wireframes were **illustrative**
* But Phase 2 UI changes were **not clearly marked as “must implement”**

👉 For Claude, that’s risky.

**Fix:**
In the PRD below, I will:

* Explicitly list **UI changes as requirements**
* Tie each UI change to a Phase 2 feature
* Keep them minimal and incremental (no redesign)

---

## 2️⃣ Should Phase 2 & Phase 3 be consolidated or separate?

**Strong recommendation:**
👉 **Keep them separate. Do NOT consolidate.**

### Why (founder-level reasoning)

* Phase 2 = **Parent value & retention**
* Phase 3 = **Teacher + revenue expansion**
* Different users, different UX, different risks

If you consolidate:

* Claude will overbuild
* Scope creep will happen
* You’ll slow down shipping

**Correct approach (what you’re doing now):**

* Lock Phase 2
* Build it fully
* Ship
* Then define Phase 3 fresh (based on learnings)

You’re doing this the *right* way.

---

## 3️⃣ How to handle changes in Phase 2 later?

You **don’t rewrite Phase 2 PRD**.

You do this instead:

### Change Management Rule (simple & effective)

* Phase 2 PRD = **baseline**
* Any change = **Phase 2.x Addendum**

Example:

* Phase 2.1 (original)
* Phase 2.2 (minor enhancement)
* Phase 2.3 (UX polish)

This keeps Claude (and you) sane.

---

# ✅ PRACTICECRAFT AI

## **PHASE 2 PRD — PARENTS ONLY (CLAUDE-READY)**

**(Explicit UI changes included | Multi-subject excluded)**

---

## CONTEXT FOR CLAUDE (READ FIRST)

* Phase 1 is **complete and should NOT be modified**
* This document defines **only Phase 2**
* Phase 2 is **parent-focused only**
* Do NOT add Teacher, School, or Multi-Subject features
* UI changes must be **incremental**, not redesigns

---

## PHASE 2 GOAL

> Reduce parent effort, increase trust, and increase daily/weekly usage
> **without increasing cognitive load or complexity**

---

## 2.1 Advanced Topic Selection (CORE PHASE 2 FEATURE)

### Problem

Parents don’t want to manually select topics every time.

### Functional Requirements

* Add **“Select all topics”** checkbox (default ON)
* Allow **chapter-level selection**
* Allow individual topic deselection
* Persist selection per:

  * child
  * subject

### Rules

* Default state = all topics selected
* Parent can deselect any topic
* No auto-selection changes without parent action

---

### UI Changes (MANDATORY)

#### Topic Selector UI

```text
Topics
☑ Select all topics

Chapter 1: Addition
☑ 2-digit addition
☑ 3-digit addition

Chapter 2: Subtraction
☑ With borrowing
☑ Without borrowing
```

* “Select all” toggles everything
* Chapter checkbox toggles only that chapter
* Clear visual nesting (indentation)

---

## 2.2 CBSE Syllabus Viewer (READ-ONLY, TRUST FEATURE)

### Goal

Build confidence that the app understands **official CBSE syllabus**.

### Functional Requirements

* Show CBSE syllabus based on:

  * Selected Grade
  * Selected Subject
* Read-only
* Expand / collapse chapters
* Cannot be edited

### Rules

* Used as baseline if no custom syllabus uploaded
* Never overrides uploaded syllabus
* Display only — no generation side effects

---

### UI Changes (MANDATORY)

#### Syllabus Panel (Side or Expandable)

```text
CBSE Syllabus – Class 3 Maths

✔ Addition (3–4 digit)
✔ Subtraction (borrowing)
✔ Multiplication (tables)
✔ Fractions (½, ¼)

[ Generate worksheet from this syllabus ]
```

* Calm, document-like styling
* No checkboxes (read-only)
* Reinforces trust, not control

---

## 2.3 Expanded Subject Coverage (Parents)

### Add Subjects

* Hindi
* Science (Class 4–5 only)
* Computer (basic)

### Rules

* Same worksheet engine
* Same difficulty controls
* Same PDF pipeline
* No subject mixing in a single worksheet

⚠️ **Explicitly exclude multi-subject generation**

---

## 2.4 Light Student Engagement (NO GAMIFICATION)

### Goal

Encourage completion, not addiction.

### Functional Requirements

* ⭐ Completion indicator after worksheet generation
* 🏅 Simple badges (non-competitive)
* 📅 Practice streak count (per child)

### Rules

* No animations
* No sounds
* No avatars
* No leaderboards

---

### UI Changes (MANDATORY)

#### Completion Feedback

```text
✅ Worksheet completed
⭐ You earned 1 star today
🔥 3-day practice streak
```

* Text-first
* Calm tone
* Parent-approved

---

## 2.5 Save & Reuse Improvements (Parent)

### Enhancements

* Saved worksheets grouped by:

  * subject
  * date
* Ability to regenerate with:

  * same settings
  * different difficulty

---

## NON-GOALS (STRICT)

Phase 2 must NOT include:

* Multi-subject generation
* Teacher view
* School accounts
* Payments logic changes
* LMS features
* Heavy gamification

---

## METRICS TO TRACK (PHASE 2)

* Topic selector usage
* “Select all” vs manual selection
* CBSE syllabus viewer opens
* Repeat worksheet generation per week
* Completion rate

---

## BUILD ORDER FOR PHASE 2 (IMPORTANT)

1️⃣ Advanced topic selection (UI + logic)
2️⃣ CBSE syllabus viewer
3️⃣ Subject expansion
4️⃣ Light engagement indicators
5️⃣ Save & reuse polish

---

## CHANGE MANAGEMENT RULE (IMPORTANT)

* This document = **Phase 2 baseline**
* Any new idea = **Phase 2.x Addendum**
* Do NOT rewrite this PRD unless Phase 2 is complete

---

## FINAL ADVICE (FOUNDER POV)

You’re doing the **right thing by locking Phase 2**.

* Phase 2 = **parents + trust + retention**
* Phase 3 = **teachers + money**

Keep them separate.
Ship Phase 2 cleanly.
Then we design Phase 3 with real usage data.
