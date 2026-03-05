# Landing Page CRO Audit — Skolar (Landing.tsx)

**Page type:** Landing page / Homepage
**Primary conversion goal:** Free sign-up (worksheet generation)
**Target audience:** Indian parents (CBSE Classes 1-5), secondary: teachers

---

## 1. Hero Section & Value Proposition

**Current:** "From syllabus to *mastery.*" with subtitle "Worksheets, revision notes, flashcards, and AI grading — all built for the CBSE syllabus your child actually follows."

**Issues:**
- **Headline is vague.** "From syllabus to mastery" doesn't tell a parent *what this is* in 5 seconds. A parent landing from Google needs to immediately see: "This generates worksheets for my kid."
- **"Mastery" is ed-tech jargon** — parents think in terms of "better marks", "exam prep", "practice".
- The subtitle does the heavy lifting but is too dense — 4 products listed in one sentence.
- **No emotional hook.** Parents feel guilt about not doing enough, frustration with boring worksheets, or anxiety about exams. None addressed.

**Copy alternatives:**

| Option | Headline | Rationale |
|--------|----------|-----------|
| A | "CBSE worksheets your child will actually finish" | Addresses the real pain (kids abandon boring worksheets). Specific. |
| B | "Practice every CBSE topic — worksheets in 30 seconds" | Speed + coverage. Matches what the product does. |
| C | "Your child's CBSE syllabus, turned into daily practice" | Connects syllabus ownership with action. |

---

## 2. Social Proof & Trust Signals

**Issues:**
- "Trusted by parents across India" — unverifiable claim with no number
- "5 cognitive roles per worksheet" means nothing to parents → change to "3 difficulty levels per sheet"
- Testimonials marked as "representative feedback from beta users" — honest but quotes read as fabricated

**Recommendations:**
- Replace "Trusted by parents across India" with a real metric
- Change "5 cognitive roles" → "3 difficulty levels per sheet"
- Add school names if any teachers are using it

---

## 3. CTA Clarity & Hierarchy

**Issues:**
- 6 different CTA labels for the same action — pick one and repeat it
- Floating CTA overlaps back-to-top button on some viewports
- No secondary CTA for "not ready yet" visitors (e.g., "See a sample PDF")

**Recommended primary CTA:** "Generate a free worksheet" — use everywhere.

---

## 4. Pricing Section

**Issues:**
- No "Cancel anytime" language — reduces friction
- CTA buttons don't reinforce value ("Start Scholar plan" → "Go unlimited — ₹199/mo")
- "Lock in price forever" on annual plan — verify this is true

---

## 5. Mobile Experience

**Issues:**
- Hero mobile worksheet card too small to read
- Comparison table needs horizontal scroll — convert to stacked cards
- Subject browser 10 tabs wrap messily — use horizontal scroll
- Back-to-top button overlaps mobile bottom bar

---

## 6. Trust Signals Deep-Dive

**Missing:**
- No privacy/data safety statement
- No "Made in India" or founder story
- No NCERT alignment badge visual

---

## 7. Objection Handling

| Objection | Addressed? |
|-----------|------------|
| "Is it really free?" | Partially |
| "Is it CBSE-aligned?" | Yes |
| "Will my child find it boring?" | No |
| "Is it safe / private?" | No |
| "How is this better than Toppr/Byju's?" | Partially |

---

## Quick Wins (Implement Now)

- [x] 1. Fix CTA consistency — use "Generate a free worksheet" everywhere
- [x] 2. Change "5 cognitive roles" → "3 difficulty levels per sheet" in trust badges
- [x] 3. Add "Cancel anytime" under Scholar pricing
- [x] 4. Add "No app needed" chip in hero
- [x] 5. Fix floating button overlap — hide back-to-top when floating CTA is showing

## High-Impact Changes (Prioritize)

- [x] 6. Rewrite hero headline to be benefit-specific
- [x] 7. Add a one-liner privacy statement near bottom CTA
- [x] 8. Replace comparison heading "Free Tools" → "Generic Worksheet Sites"
- [ ] 9. Add "Download sample PDF" secondary CTA in hero (needs pre-built PDF asset)
- [ ] 10. Convert comparison table to cards on mobile (larger change)

## Section Reorder

- [ ] 11. Move "More than worksheets" and "Dashboard preview" below pricing

## Test Ideas (Future A/B)

- Hero headline variations
- Hero CTA color: Orange vs Emerald
- Testimonials: cards vs WhatsApp screenshot style
- Pricing: Show "₹6.6/day" anchoring
- Social proof: real number vs generic claim
