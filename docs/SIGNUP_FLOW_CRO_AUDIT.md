# Signup & Onboarding Flow CRO Audit — Skolar

**Date:** 2026-03-05
**Target audience:** Indian parents (mothers primarily) of CBSE Class 1-5 children
**Device split:** 70% mobile

---

## Current Flow (7 steps to "aha moment")

| Step | Screen | Fields / Actions | Drop-off Risk |
|------|--------|-----------------|---------------|
| 1 | Landing | Click "Start free" | Low |
| 2 | Auth page | Name + Email + Password (or Google) | HIGH |
| 3 | Email confirmation | Check inbox, click link | VERY HIGH |
| 4 | Onboarding Step 1 | Child name + Grade + Board | Medium |
| 5 | Onboarding Step 2 | Pick a subject | Low |
| 6 | Onboarding Step 3 | Confirm & generate | Unnecessary |
| 7 | Worksheet generator | See first worksheet | AHA MOMENT |

---

## Optimized Flow (4 steps, under 60 seconds)

| Step | Screen | What Happens | Time |
|------|--------|-------------|------|
| 1 | Landing | Click "Generate a free worksheet" | 2s |
| 2 | Auth | Google one-tap (primary) or Email + Password | 5-10s |
| 3 | Quick setup (modal) | Child name + Grade (2 fields only) | 10s |
| 4 | Generator | Auto-navigates to Maths worksheet for selected grade | 30s |

---

## Changes Implemented

### Quick Wins
- [x] 1. Remove onboarding Step 3 (confirmation screen) — auto-generate on subject pick
- [x] 2. Remove Board field from onboarding Step 1
- [x] 3. Reduce onboarding from 3 steps to 2 (child info → subject pick → auto-generate)
- [x] 4. Update Auth page left panel tagline to match new hero copy
- [x] 5. Add password visibility toggle to Auth page

### High-Impact Changes
- [x] 6. Make Google sign-in visually primary (larger, colored)
- [x] 7. Update Auth page signup CTA copy for clarity
- [ ] 8. Disable email confirmation in Supabase (requires dashboard change, not code)

### Future / Requires Architecture Change
- [ ] 9. Try-before-signup flow (generate preview without account)
- [ ] 10. Phone/OTP signup via Supabase
- [ ] 11. Magic link passwordless auth
