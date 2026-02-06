Perfect 👍 — below is a **revised Phase 2 PRD**, **ONLY Phase 2**, with your requested changes **explicitly added**:

* ✅ UI polish inspired by K5 Learning (principles, not copy)
* ✅ Clear UI requirements (so Claude doesn’t “wing it”)
* ❌ Multi-subject generation still excluded
* ❌ No Phase 1 overlap
* ❌ No Teacher / School (kept for later)

This is **Claude-safe** and **scope-locked**.

---

# 📘 PRACTICECRAFT AI

## **PHASE 2 PRD — PARENTS (TRUST, EFFORT REDUCTION & UI POLISH)**

---

## CONTEXT FOR CLAUDE (IMPORTANT)

* Phase 1 is **already implemented**
* Do NOT refactor Phase 1 logic
* Phase 2 focuses on:

  * reducing parent effort
  * increasing trust
  * improving visual clarity
* UI changes must be **incremental polish**, not redesign
* Do NOT add Teacher, School, or Multi-Subject features

---

## PHASE 2 OBJECTIVE

> Make the product feel **as trustworthy and calm as K5 Learning**,
> while remaining **task-driven and syllabus-aware**.

---

# 2.1 ADVANCED TOPIC SELECTION

### Problem

Parents find repeated manual topic selection tiring.

### Functional Requirements

* ☑ **Select all topics** (default ON)
* ☑ **Chapter-level selection**
* ☑ Individual topic toggles
* Persist selection per child + subject

### Rules

* Default = all topics selected
* No auto-changes without parent action

---

### UI REQUIREMENTS (MANDATORY)

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

**UI principles**

* Clear indentation
* Checkbox hierarchy
* Calm spacing (no dense lists)

---

# 2.2 CBSE SYLLABUS VIEWER (TRUST FEATURE)

### Goal

Increase parent confidence that worksheets match **official CBSE syllabus**.

### Functional Requirements

* Auto-load syllabus by Grade + Subject
* Read-only
* Expand / collapse chapters
* “Generate from CBSE syllabus” CTA

### Rules

* Never overrides uploaded syllabus
* Display only (no editing)

---

### UI REQUIREMENTS (MANDATORY)

```text
CBSE Syllabus – Class 3 Maths

✔ Addition (3–4 digit)
✔ Subtraction (borrowing)
✔ Multiplication (tables)
✔ Fractions (½, ¼)
```

**Design guidance**

* Document-like appearance
* Light borders
* No interactive controls
* Looks “academic”, not “app-like”

---

# 2.3 SUBJECT EXPANSION (PARENTS ONLY)

### Add Support For

* Hindi
* Science (Class 4–5)
* Computer (basic)

### Rules

* Same worksheet engine
* Same difficulty controls
* Same PDF pipeline
* **One subject per worksheet only**

❌ Multi-subject generation explicitly excluded

---

# 2.4 LIGHT STUDENT ENGAGEMENT (NON-GAMIFIED)

### Goal

Encourage completion without turning into a game.

### Functional Requirements

* ⭐ Completion indicator
* 🏅 Simple badges (non-competitive)
* 📅 Practice streak count

### Explicit Exclusions

* No avatars
* No animations
* No leaderboards
* No sounds

---

### UI REQUIREMENTS (MANDATORY)

```text
✅ Worksheet completed
⭐ You earned 1 star today
🔥 3-day practice streak
```

Tone:

* Calm
* Encouraging
* Parent-approved

---

# 2.5 SAVE & REUSE POLISH

### Enhancements

* Group saved worksheets by:

  * Subject
  * Date
* Allow:

  * Regenerate with same settings
  * Regenerate with different difficulty

---

# 2.6 UI POLISH (K5-INSPIRED, NOT COPIED)

⚠️ **This section is new and mandatory**

### Design Goals

* Academic
* Calm
* Print-first
* Trust-oriented

---

## UI PRINCIPLES TO APPLY

### 1️⃣ Visual Hierarchy

* Clear distinction between:

  * Page title
  * Section headers
  * Form labels
* Increase spacing, not borders

---

### 2️⃣ Typography

* Larger headings
* Neutral fonts
* Avoid marketing language

Example:

> “Create a worksheet”
> not
> “Generate AI-powered content”

---

### 3️⃣ Color Usage

* One accent color only
* Soft gray / slate palette
* No gradients
* Buttons feel “utility”, not “CTA hype”

---

### 4️⃣ Trust Micro-copy (Mandatory)

Add visible reassurance text:

```text
✔ CBSE-aligned
✔ Printable worksheets
✔ Built for parents
```

---

### 5️⃣ Card & Layout Polish

* Fewer cards
* More vertical spacing
* Rounded corners
* Subtle shadows only

---

# NON-GOALS (LOCKED)

Phase 2 must NOT include:

* Teacher View
* School accounts
* Multi-subject worksheets
* Payments changes
* LMS features
* Heavy gamification
* SEO content pages

---

# METRICS TO TRACK (PHASE 2)

* “Select all topics” usage
* CBSE syllabus viewer opens
* Repeat worksheet generation
* Weekly active parents
* Completion rate

---

# BUILD ORDER (PHASE 2)

1️⃣ Advanced topic selection
2️⃣ CBSE syllabus viewer
3️⃣ Subject expansion
4️⃣ UI polish pass
5️⃣ Light engagement indicators
6️⃣ Save & reuse polish

---