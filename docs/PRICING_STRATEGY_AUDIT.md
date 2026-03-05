# Pricing Strategy Audit — Skolar

**Date:** 2026-03-05
**Target:** Indian middle-class parents (household income ₹5-15 lakh/year)

---

## Current State

| | Landing Page | Backend | Mismatch? |
|---|---|---|---|
| Free limit | "5 worksheets/month" | `FREE_TIER_LIMIT = 10` | YES |
| Paid tier | Scholar ₹199/mo | Binary free/paid | — |
| Annual | ₹1,499/yr (37% off) | N/A | — |

---

## Decisions

| Question | Answer |
|---|---|
| Price point | ₹199/month — below impulse threshold, anchors vs ₹2-5K tutors |
| Free tier limit | 5 worksheets/month — enough to form habit, not enough to avoid paying |
| Tier structure | Two tiers (Free + Scholar), not three. Annual = ₹1,499/yr |
| Annual discount | Keep 37% — show "₹125/month billed yearly" |
| Per-child pricing | No — include up to 5 children in Scholar |
| Paywall strategy | Gate volume + depth. Never gate PDFs or sharing |

---

## Feature Matrix

| Feature | Free | Scholar |
|---|---|---|
| Worksheet generation | 5/month | Unlimited |
| All 9 subjects | Yes | Yes |
| PDF download + answer key | Yes | Yes |
| 3 difficulty levels | Yes | Yes |
| Photo grading | 1 free trial | Unlimited |
| Revision notes | No | Yes |
| Flashcards | No | Yes |
| Progress tracking | Basic (last 5) | Full history + trends |
| Multiple children | 1 child | Up to 5 |
| Ask Skolar (AI tutor) | 3 questions/month | Unlimited |
| Bulk generation | No | Yes |
| WhatsApp sharing | Yes | Yes |

---

## Changes Implemented

- [x] Fix backend `FREE_TIER_LIMIT` from 10 to 5
- [x] Update pricing cards: show "₹125/mo billed yearly" on annual card
- [x] Update pricing card features to match feature matrix
- [x] Update FAQ to say "5 worksheets" consistently
- [x] Add "₹6.6/day" anchoring to Scholar card
- [x] Add "Up to 5 children" to Scholar features

---

## Price Anchoring (for copy)

- ₹199/month = ₹6.6/day (less than a chai)
- ₹1,499/year = ₹125/month = ₹4.1/day
- Tutor costs ₹2,000-5,000/month → Skolar = 4-10% of tuition cost
- BYJU'S = ₹500-1,000/month → Skolar = 20-40% of BYJU'S
