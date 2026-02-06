🚀 PRACTICECRAFT AI
ANTI-GRAVITY PRODUCT REQUIREMENTS DOCUMENT (AG-PRD v1.0)
1. PRODUCT IDENTITY

Product Name: PracticeCraft AI
Category: Parent-First Practice Generation Platform
Primary Market: India & UAE
Target Grades: Class 1–5 (Phase 1)
Primary Board: CBSE
Secondary: Custom School Syllabus

2. CORE PRODUCT PRINCIPLE (NON-NEGOTIABLE)

The child’s school syllabus is the single source of truth.
AI must NEVER introduce concepts, difficulty, or language outside the defined syllabus and grade.

3. PROBLEM STATEMENT

Parents lack:

Syllabus-aligned daily practice

Regional language support

Printable, on-demand worksheets

Control over difficulty and coverage

Existing ed-tech focuses on videos, not practice.

4. SOLUTION OVERVIEW

PracticeCraft AI converts:

CBSE or uploaded school syllabus
into

Daily, printable, grade-safe practice worksheets
in

English or regional languages

5. TARGET USERS
Primary

Parents of children in Class 1–5

CBSE / Indian curriculum schools (India & UAE)

Secondary

Home tutors

Small private schools

6. SUPPORTED REGIONS & LANGUAGES
🇮🇳 India

English

Hindi

Marathi

Tamil

Telugu

Kannada

🇦🇪 UAE

English

Arabic

Hindi / Urdu

Language Scope Rule:
Language affects instructions & explanations only.
Mathematical logic and symbols remain unchanged.

7. CORE FEATURES
7.1 Manual Worksheet Generator

Board selection

Grade selection

Subject selection

Topic selection

Difficulty (Easy / Medium / Hard)

Question count

Output language

Printable PDF output

7.2 Syllabus Upload & Parsing (CORE MOAT)
Inputs

PDF syllabus

Image (photo/scan)

Text / Doc

AI Responsibilities

Extract:

Grade

Subject

Chapters

Topics

Normalize topics to grade-appropriate depth

Flag ambiguity or over-advanced topics

Parent Control

Edit topics

Select chapters

Confirm syllabus before generation

7.3 Practice Generation Engine

Section-wise worksheets

Progressive difficulty

Indian / UAE contextual examples

No repetition

Printable formatting

7.4 Answer Key & Explanations

Optional

Step-by-step

Child-friendly language

Matches worksheet language

8. SUBJECT COVERAGE (PHASE 1)
Maths

Addition

Subtraction

Multiplication

Division

Fractions

Word problems

English

Grammar

Vocabulary

Reading comprehension

EVS

Environment

Family & community

Daily life

9. UX PRINCIPLES (ANTI-GRAVITY)

Parent-first, not teacher-first

No educational jargon

One-click worksheet generation

Print-first design

Mobile-friendly

10. NON-FUNCTIONAL REQUIREMENTS

Worksheet generation < 5 seconds

Deterministic formatting

Zero syllabus hallucination

Child-safe language

PDF-ready output

11. MONETIZATION
Free Tier

3 worksheets/month

English only

No syllabus upload

Paid Tier

Unlimited worksheets

Syllabus upload

Regional languages

Answer explanations

Multi-child profiles

12. SUCCESS METRICS

Worksheets generated per user

Syllabus uploads

Repeat usage

Conversion to paid

Parent satisfaction

13. AI SYSTEM — ANTI-GRAVITY PROMPT (MANDATORY)
🔒 SYSTEM ROLE

You are a CBSE curriculum expert, Indian primary school teacher, child psychologist, and bilingual education specialist.

You generate practice worksheets for school children.

The uploaded syllabus is the single source of truth.

📥 INPUT SCHEMA
Case A — Manual
Board:
Grade:
Subject:
Topics:
Difficulty:
Question Count:
Output Language:
Include Answer Key:

Case B — Syllabus Upload
Uploaded Syllabus Content:
<<<TEXT>>>

Grade (if known):
Subject:
Difficulty:
Output Language:
Worksheet Type:

🧠 PROCESSING RULES (STRICT)

Parse syllabus into chapters and topics

Normalize to grade-safe depth

Do NOT add new concepts

Use simple child-friendly language

Translate only instructions & explanations

Maintain print-friendly layout

🧾 OUTPUT STRUCTURE (NON-NEGOTIABLE)
Title
Class | Subject | Language

Instructions

Section-wise Questions

Bonus (if enabled)

Answer Key (if enabled)

🧪 QUALITY SELF-CHECK (FAIL-SAFE)

✔ Matches syllabus

✔ Grade-appropriate

✔ Correct language

✔ Clear formatting

✔ Printable layout

If ANY fail → regenerate output.

14. DEFENSIBILITY

Syllabus-as-truth logic

Pedagogy-safe AI prompting

Regional language execution

Practice-first philosophy

Parent-centric UX

15. POSITIONING STATEMENT

“Turn your child’s school syllabus into daily practice — in your language.”