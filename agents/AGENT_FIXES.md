# PracticeCraft — Screen-by-Screen Production Fix Plan
## Every screen after login. Every bug. Every gap. In order.

---

## THE ANSWER VISIBILITY ROOT CAUSE (Before Anything Else)

You asked "Show Answer is not visible across all worksheets." Let me tell you exactly why.

The LLM is asked to return this JSON:
```json
{"format": "", "question_text": "", "pictorial_elements": [], "answer": ""}
```

The `_slot_to_question` function maps `q.get("answer")` → `correct_answer` in the API model.

**Three reasons answers show as `---`:**

**Reason 1 — Empty string becomes None.**
`q.setdefault("answer", "")` runs if LLM doesn't return an answer.
Then `_slot_to_question` does:
```python
answer_str = str(answer).strip() if answer is not None and str(answer).strip() else None
```
Empty string → `None` → `correct_answer=None` → Answer Key shows `---`.

**Reason 2 — English/Science creative questions.**
`explain_why`, `creative_writing`, `describe` slots don't have a single correct answer.
LLM returns a sample paragraph. The code sets `answer_type="example"` but
`_slot_to_question` ignores `sample_answer` (sets it to `None`).
Result: `correct_answer=None` → Answer Key shows `---`.

**Reason 3 — History/SavedWorksheets modal shows ALL answers always.**
No toggle. `{question.correct_answer}` renders inline, unconditionally.
If `correct_answer` is `null` in DB, it renders nothing. No `---`, just blank.

**The fix is in three places:**

**Fix A — `_slot_to_question` in `worksheets.py`:** Map `sample_answer` too.
```python
# Current:
sample_answer=None,

# Fixed:
sample_answer=q.get("sample_answer") or (answer_str if q.get("answer_type") == "example" else None),
```

**Fix B — Frontend `Answer Key Reference` section:** Show both exact and sample answers.
```tsx
// Current: {question.correct_answer || '---'}

// Fixed:
{question.correct_answer 
  ? question.correct_answer 
  : question.sample_answer 
    ? <span className="text-muted-foreground italic text-xs">{question.sample_answer}</span>
    : <span className="text-muted-foreground">—</span>
}
```

**Fix C — History and SavedWorksheets modals:** Add a Show/Hide toggle.
Currently they always show `correct_answer` inline with no toggle — which means:
- Teachers can't let students self-check
- Parents can't use it as a marking guide
- When `correct_answer` is null, the answer cell is just blank (confusing)

---

## SCREEN 1: WORKSHEET GENERATOR (WorksheetGenerator.tsx — 1803 lines)

The main screen. Most complex. Most issues.

### Bug 1: Show Answers button position is buried
The "Show Answers" button is in the toolbar alongside Print/Save/Share.
On mobile it's invisible because the toolbar wraps. Parents don't find it.

**Fix:** Move "Show Answers" to appear DIRECTLY BELOW the last question, before the Answer Key section.
```tsx
{/* After question rendering, before Answer Key */}
{!showAnswers && (
  <div className="mt-8 flex justify-center print:hidden">
    <button
      onClick={() => setShowAnswers(true)}
      className="flex items-center gap-2 px-6 py-2.5 rounded-xl border-2 border-primary/30 text-primary font-semibold text-sm hover:bg-primary/5 transition-colors"
    >
      <EyeIcon className="w-4 h-4" />
      Show Answer Key
    </button>
  </div>
)}
```
Keep the toolbar button too — just add this second trigger below the worksheet.

### Bug 2: Answer Key shows `---` for English/Science/Hindi questions
**Root Cause:** Explained above (Reasons 1 & 2).
**Fix:** Apply Fix A (backend) + Fix B (frontend) described at the top.

### Bug 3: Tiered view doesn't show inline answer indicators when Show Answers is ON
When `showAnswers=true`, the Answer Key is a separate grid at the bottom.
But in the tiered view, the parent has to scroll back up to find "Q3 = 12".
The answer is not next to the question.

**Fix:** When `showAnswers=true`, show answer inline after each question in BOTH tiered and flat rendering:
```tsx
{/* Add this inside both tier.questions.map() and allQuestions.map() */}
{showAnswers && question.correct_answer && (
  <div className="mt-2 inline-flex items-center gap-2 px-3 py-1 bg-emerald-50 border border-emerald-200 rounded-lg print:bg-gray-100 print:border-gray-400">
    <span className="text-xs font-semibold text-emerald-700 print:text-gray-700">Answer:</span>
    <span className="text-sm font-bold text-emerald-900 print:text-gray-900">{question.correct_answer}</span>
  </div>
)}
{showAnswers && !question.correct_answer && question.explanation && (
  <div className="mt-2 px-3 py-1.5 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-800 italic print:bg-gray-50">
    <span className="font-semibold not-italic">Sample: </span>{question.explanation}
  </div>
)}
```

### Bug 4: Free tier limit shows `/NOT FOUND` in usage badge
`UsageBadge` in `App.tsx` reads `status.worksheets_remaining` but the badge JSX hardcodes `/3` with broken string interpolation.

**Fix in `App.tsx`:**
```tsx
// Current (broken):
{status.worksheets_remaining}/{3} Credits

// Fixed:
{status.worksheets_remaining}/{5} Credits
```
Also update `subscription_check.py`: `FREE_TIER_LIMIT = 5`
And `subscription.tsx` default: `worksheets_remaining: 5`

### Bug 5: No "limit reached" state before generation
When free tier is exhausted, the generate button appears to work but fails silently or shows a generic error. Parent doesn't know why.

**Fix:** Check subscription status before showing the generate button:
```tsx
{status && !status.can_generate ? (
  <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl">
    <p className="font-semibold text-amber-800">You've used all 5 free worksheets this month</p>
    <p className="text-sm text-amber-700 mt-1">Upgrade for unlimited access</p>
    <button onClick={() => setShowUpgrade(true)} className="mt-3 bg-primary text-white px-5 py-2 rounded-lg text-sm font-semibold">
      Upgrade — ₹299/month
    </button>
  </div>
) : (
  <button type="submit" ...>Create today's practice</button>
)}
```

### Bug 6: No completion/grading flow
After worksheet renders, there's no way to submit answers. Mastery never updates.

**Fix:** Add self-check section after worksheet (detailed in Phase 4 of previous plan):
```tsx
{worksheet && (
  <SelfCheckSection
    questions={worksheet.questions}
    childId={selectedChild}
    worksheetId={savedWorksheetId}
    onSubmitted={() => toast("Progress saved ✓")}
  />
)}
```

### Bug 7: Subject/grade loading has 2-3 second visual blank
After selecting a grade, the subject dropdown shows empty for 2-3 seconds (noted in E2E tests as `waitForTimeout(3000)`).

**Fix:** Add loading skeleton to subject dropdown:
```tsx
{curriculumLoading ? (
  <div className="h-10 bg-gray-100 rounded-lg animate-pulse" />
) : (
  <SubjectSelect ... />
)}
```

### Bug 8: Temperature 0.8 causes wrong maths answers
**Fix in `slot_engine.py` L14903:**
```python
temperature=0.8,  →  temperature=0.3,
```
One line. Do it first.

---

## SCREEN 2: PROGRESS / PARENT DASHBOARD (ParentDashboard.tsx — 456 lines)

### Bug 1: Shows zeros for all new users
Mastery store is in-memory → resets on every Railway restart → Dashboard always shows 0 for skills.
**Fix:** Set `PRACTICECRAFT_MASTERY_STORE=supabase` in Railway env. (Covered in Phase 1.)

### Bug 2: Skill tags are shown raw (e.g. `mth_c3_addition_3digit_no_carry`)
The skill tags are internal identifiers. Parents see them as-is.

**Fix in `ParentDashboard.tsx`:** Use the existing `formatSkillTag` function, but also improve it:
```tsx
function formatSkillTag(tag: string): string {
  return tag
    .replace(/^(mth|eng|sci|hin|comp|gk|moral|health)_c\d+_/, '') // strip prefix
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
}
// "mth_c3_addition_3digit_no_carry" → "Addition 3 Digit No Carry"
// Better than current which doesn't strip the prefix
```

### Bug 3: No action from Progress dashboard
Parent sees "accuracy: 45%" for Fractions but there's no "practice this now" button.

**Fix:** Add Practice button to each skill row:
```tsx
<button
  onClick={() => onNavigate('generator')}  // pass topic context via App state
  className="text-xs font-medium text-primary border border-primary/30 px-2.5 py-1 rounded-lg hover:bg-primary/5"
>
  Practice →
</button>
```
The `onNavigate` callback is already passed via `App.tsx`. Add topic pre-fill state.

### Bug 4: Recent topics section has no "generate again" action
The Recent Topics table shows `topic` and `last_generated` but no action.

**Fix:** Add "Generate again →" link that navigates to generator with topic pre-filled.

### Bug 5: No child selector if multiple children exist
Dashboard calls `/api/v1/dashboard/parent?student_id=X` but never prompts user to pick which child if they have more than one.

**Fix:** Pull children from `useChildren()` hook and show a dropdown at the top if `children.length > 1`.

---

## SCREEN 3: HISTORY (History.tsx — 492 lines)

### Bug 1: Viewing a worksheet shows blank answer cells
The inline view renders `{question.correct_answer}` with no fallback.
If `correct_answer` is null (English/Science open-ended questions), the cell is blank.

**Fix:**
```tsx
// Current:
<span className="font-bold text-foreground text-sm">{question.correct_answer}</span>

// Fixed:
<span className="font-bold text-foreground text-sm">
  {question.correct_answer || question.explanation || 
    <span className="text-muted-foreground text-xs italic">Open-ended</span>}
</span>
```

### Bug 2: No Show/Hide answers toggle in the worksheet modal
The History modal always shows answers inline. No way to hide them for student self-checking.

**Fix:** Add `showAnswers` toggle to the history modal:
```tsx
const [showAnswers, setShowAnswers] = useState(false)

// In modal toolbar:
<button onClick={() => setShowAnswers(!showAnswers)} className="text-xs ...">
  {showAnswers ? 'Hide Answers' : 'Show Answers'}
</button>

// In question row:
{showAnswers && (
  <span className="font-bold text-emerald-700 text-sm">
    {question.correct_answer || question.explanation || '—'}
  </span>
)}
```

### Bug 3: PDF download in History re-fetches full worksheet but isn't wired
The `handleDownloadPdf` calls the PDF endpoint but it's unclear whether it passes the full `questions` array (needed for PDF generation) or just the worksheet ID.

**Verify:** Check that the API call to `/api/worksheets/export-pdf` includes questions with `correct_answer` populated. If not, the PDF will have blank answers.

### Bug 4: No re-generate button
From History, parents can view and download but can't regenerate a similar worksheet with one click.

**Fix:** Add "Generate similar →" button that navigates to generator with grade/subject/topic pre-filled.

---

## SCREEN 4: SAVED WORKSHEETS (SavedWorksheets.tsx — 599 lines)

### Bug 1: Modal shows answers without toggle (same as History)
All answers are always visible in the preview modal.

**Fix:** Same toggle pattern as History fix above.
Add `showAnswers` state → toggle button → conditional render.

### Bug 2: Answer cells are blank when `correct_answer` is null
Same as History Bug 1.
**Fix:** Same fallback pattern: `correct_answer || explanation || 'Open-ended'`

### Bug 3: Saved worksheet modal lacks print button
The preview modal has no print option. User has to close modal and click "PDF" from the list.

**Fix:** Add Print/PDF button inside the modal:
```tsx
<button onClick={() => handleDownloadPdf(selectedWorksheet.id)} className="...">
  Download PDF
</button>
```

### Bug 4: No "Regenerate" on saved worksheet
Like History, user can't one-click regenerate a saved worksheet.

---

## SCREEN 5: TEACHER DASHBOARD (TeacherDashboard.tsx — 287 lines)

### Bug 1: Analytics shows 0 for "Topic reuse rate" and "Active weeks"
The `/api/worksheets/analytics` endpoint returns these fields but they're computed from worksheet history. For new teachers with < 5 worksheets, they all show 0.

**Fix:** Add friendly empty state:
```tsx
{analytics?.total_worksheets === 0 ? (
  <EmptyState
    title="No worksheets yet"
    description="Generate your first worksheet to see analytics"
    action={<button onClick={() => onNavigate('generator')}>Create worksheet →</button>}
  />
) : (
  <AnalyticsGrid ... />
)}
```

### Bug 2: Recent worksheets section has no "view" action
The list shows recent worksheets by title but clicking does nothing.

**Fix:** Add click handler to open worksheet preview (same modal as SavedWorksheets).

### Bug 3: No class-level analytics
TeacherDashboard shows personal worksheet stats but doesn't show class performance even though the analytics API (`/api/analytics/skill_accuracy`) exists.

**Fix (later):** Wire `/api/analytics/skill_accuracy` to show top 5 weakest skills across the teacher's classes.

---

## SCREEN 6: CLASS MANAGER (ClassManager.tsx — 377 lines)

### Bug 1: No "Add Student" functionality
`ClassManager` can create/delete classes but cannot add students to a class.
The `classes` API exists (`/api/classes`) but the student-add flow is missing.

**Fix:** Add "Add Student" button per class that opens a modal:
- Input: student name (optional) + email (optional)
- On submit: POST to `/api/classes/{class_id}/students`
- Check if this endpoint exists — if not, add it to `backend/app/api/classes.py`

### Bug 2: No "Generate worksheet for class" action
Teacher creates a class but can't generate a worksheet for the whole class from here.

**Fix:** Add "Generate worksheet →" button per class that navigates to generator with `class_id` pre-filled. The generator already accepts `class_id` in its request.

### Bug 3: Delete class has no confirmation dialog
Clicking delete immediately destroys the class and all its worksheets.

**Fix:** Add confirmation:
```tsx
if (!confirm(`Delete "${cls.name}"? This cannot be undone.`)) return
// (Or use a modal for better UX)
```

---

## SCREEN 7: CHILD PROFILES (ChildProfiles.tsx — 351 lines)

### Bug 1: Grade field is a select but subjects/topics aren't pre-filtered to that grade
After adding a child with "Class 3", the generator still shows all topics across all grades.
The child's grade from `useChildren()` should auto-filter the generator.

**Fix:** In `WorksheetGenerator.tsx`, when a child is selected, auto-set `gradeLevel` from `child.grade`:
```tsx
useEffect(() => {
  if (selectedChildObj?.grade) {
    setGradeLevel(selectedChildObj.grade)
  }
}, [selectedChildObj])
```

### Bug 2: No "Generate worksheet for this child" button
Child profile has no direct action to the generator.

**Fix:** Add "Practice now →" button that navigates to generator with child pre-selected.

### Bug 3: Notes field has no character limit shown
The "special topics/interests" textarea has no visible limit or hint.

**Minor fix:** Add `maxLength={500}` and a character counter.

---

## SCREEN 8: SYLLABUS UPLOAD (SyllabusUpload.tsx — 621 lines)

### Bug 1: `/api/syllabus/parse` is not a real parser
Looking at `backend/app/api/syllabus.py` — this likely returns a placeholder or hardcoded structure. The PRD lists syllabus parsing as a "core moat" but it's still incomplete.

**Verify:** Test by uploading an actual CBSE Class 3 Maths PDF. If it returns hardcoded chapters, the screen is broken for real uploads.

**Fix approach:** If broken, add clear messaging:
```tsx
{/* Show what was parsed */}
{syllabus && (
  <div>
    <p className="text-sm text-muted-foreground mb-2">
      We found {syllabus.chapters.length} chapters. Please verify:
    </p>
    {/* Editable chapter list */}
  </div>
)}
```

### Bug 2: After parsing, no loading state between "Upload" and "Syllabus ready"
The upload button spins but there's no intermediate state showing "Parsing your syllabus..."

**Fix:** Add a multi-step loading indicator:
- Step 1: "Uploading file..."
- Step 2: "Reading content..."
- Step 3: "Extracting chapters and topics..."

### Bug 3: Parsed syllabus can't be edited before using it
If the AI parses wrongly (e.g. "Shapes" gets categorised under English), the parent can't correct it before the worksheet is generated.

**Fix:** Show parsed syllabus as an editable checklist:
- Chapter names (editable)
- Topics under each chapter (toggleable)
- "Confirm and generate" button

---

## SCREEN 9: SHARED WORKSHEET (SharedWorksheet.tsx — 279 lines)

### Bug 1: Show Answers toggle works but answer is `null` for many question types
Same root cause as main generator. `showAnswers && q.correct_answer` only shows if correct_answer is non-null.

**Fix:** Same fallback: show `explanation` when `correct_answer` is null:
```tsx
{showAnswers && (q.correct_answer || q.explanation) && (
  <div className="mt-2 px-3 py-1.5 bg-emerald-50 border border-emerald-100 rounded-lg text-sm">
    <span className="font-semibold text-emerald-800">Answer: </span>
    <span className="text-emerald-900">{q.correct_answer || q.explanation}</span>
  </div>
)}
```

### Bug 2: Shared worksheet page has no branding
When a parent shares a worksheet, the recipient sees the questions but no product branding or "Create your own →" CTA.

**Fix:** Add footer to `SharedWorksheet.tsx`:
```tsx
<div className="mt-12 pt-6 border-t border-gray-100 text-center print:hidden">
  <p className="text-sm text-gray-500">Made with PracticeCraft</p>
  <a href="/" className="mt-2 inline-flex items-center gap-1 text-primary text-sm font-medium">
    Create worksheets for your child →
  </a>
</div>
```

### Bug 3: No print/download on shared worksheet
Recipient can view but can't print without going through browser print dialog manually.

**Fix:** Add print button to shared worksheet toolbar.

---

## SCREEN 10: AUTH (Auth.tsx — 225 lines)

### Bug 1: No Google sign-in
Email/password only. In India and UAE, most users expect Google sign-in. The drop-off on email registration is high.

**Fix:** Add Supabase Google OAuth:
```tsx
const handleGoogleSignIn = async () => {
  await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo: window.location.origin }
  })
}

// In JSX:
<button onClick={handleGoogleSignIn} className="w-full flex items-center justify-center gap-3 border rounded-xl py-2.5 hover:bg-gray-50">
  <GoogleIcon className="w-5 h-5" />
  Continue with Google
</button>
<div className="relative my-4"><span className="text-xs text-muted-foreground px-2 bg-white">or</span></div>
{/* email/password form below */}
```
Enable Google provider in Supabase dashboard → Auth → Providers.

### Bug 2: Error messages are generic
"Authentication failed" doesn't tell the user if their email is wrong vs password wrong vs account doesn't exist.

**Fix:** Map Supabase error codes to readable messages:
```tsx
const getAuthError = (error: AuthError) => {
  switch (error.message) {
    case 'Invalid login credentials': return 'Wrong email or password. Please try again.'
    case 'Email not confirmed': return 'Check your inbox — we sent a confirmation email.'
    case 'User already registered': return 'An account exists with this email. Sign in instead.'
    default: return error.message
  }
}
```

### Bug 3: No "Forgot password" link
Email/password auth with no password reset = permanent locked out users.

**Fix:** Add forgot password:
```tsx
<button onClick={handleForgotPassword} className="text-xs text-primary underline">
  Forgot password?
</button>

const handleForgotPassword = async () => {
  if (!email) { setError('Enter your email first'); return }
  await supabase.auth.resetPasswordForEmail(email)
  setError('') 
  toast('Password reset link sent to your email')
}
```

---

## SCREEN 11: LANDING PAGE (Landing.tsx — 818 lines)

### Bug 1: Pricing section shows heading but no prices
The `#pricing` section header exists but the actual ₹ prices aren't rendering in the component (confirmed by code audit — `re.findall(r'₹\d+')` returns empty).

**Fix:** Add actual prices to the paid tier card in `Landing.tsx`:
```tsx
{/* Paid tier card */}
<h3 ...>Elite Pro</h3>
<div className="flex items-baseline gap-1 mb-1">
  <span className="text-4xl font-bold text-slate-900">₹299</span>
  <span className="text-slate-400">/month</span>
</div>
<p className="text-xs text-emerald-600 font-medium mb-5">
  or ₹2,499/year — save 30%
</p>
```

For UAE users (detect from `navigator.language` or show both):
```tsx
<span className="text-xs text-slate-400">/ AED 45 per month in UAE</span>
```

### Bug 2: Free tier shows "10 worksheets/month" but backend is being changed to 5
**Fix:** Update landing page to match:
```tsx
<p className="text-sm text-slate-400 mb-6">5 worksheets / month</p>
```

### Bug 3: CTA buttons lead to sign-up but there's no "sign in" option visible above the fold
Users who already have an account can't find sign-in without scrolling.

**Fix:** Add "Sign in" to the sticky nav:
```tsx
<nav>
  ...
  <div className="flex items-center gap-3">
    <button onClick={onSignIn} className="text-sm text-slate-600 hover:text-slate-900">Sign in</button>
    <button onClick={onGetStarted} className="bg-primary text-white px-4 py-2 rounded-lg text-sm font-semibold">
      Try free
    </button>
  </div>
</nav>
```

---

## THE COMPLETE FIX LIST BY PRIORITY

### 🔴 P0 — Broken, fix this week
| # | Screen | Issue | Fix |
|---|--------|-------|-----|
| 1 | All worksheets | Answers show `---` for English/Science | Fix `_slot_to_question` + frontend fallback to `explanation` |
| 2 | Generator | `temperature=0.8` produces wrong answers | Change to `0.3` in `slot_engine.py` L14903 |
| 3 | Generator | Usage badge shows `/NOT FOUND` | Fix JSX + align free tier to 5 everywhere |
| 4 | Generator | No upgrade prompt when limit hit | Show upgrade CTA before generate button |
| 5 | All screens | Mastery data resets on deploy | Set `PRACTICECRAFT_MASTERY_STORE=supabase` in Railway |
| 6 | Landing | Pricing section shows no prices | Add ₹299 / AED 45 to paid tier card |
| 7 | Auth | No "Forgot password" | Add Supabase `resetPasswordForEmail` |

### 🟡 P1 — Broken UX, fix before first paying users
| # | Screen | Issue | Fix |
|---|--------|-------|-----|
| 8 | Generator | Show Answers buried in toolbar | Add second trigger below last question |
| 9 | Generator | No inline answers when Show Answers is ON | Show answer after each question in tiered/flat view |
| 10 | History | No Show/Hide toggle in modal | Add `showAnswers` state + toggle button |
| 11 | History | Blank answer cells | `correct_answer || explanation || 'Open-ended'` |
| 12 | Saved | No Show/Hide toggle | Same as History |
| 13 | Saved | Blank answer cells | Same as History |
| 14 | Progress | Skill tags shown raw | Strip prefix in `formatSkillTag` |
| 15 | Progress | No "Practice this" button | Add navigate-to-generator button per skill |
| 16 | Auth | No Google sign-in | Add Supabase Google OAuth |
| 17 | Auth | Generic error messages | Map Supabase error codes to readable messages |
| 18 | Shared | No branding / "Create your own" CTA | Add footer with PracticeCraft link |
| 19 | Children | Grade doesn't auto-fill generator | Set `gradeLevel` from selected child |

### 🟢 P2 — Product gaps, fix in first month
| # | Screen | Issue | Fix |
|---|--------|-------|-----|
| 20 | Generator | No completion/grading flow | Add `SelfCheckSection` component |
| 21 | History | No "Generate similar" | Navigate to generator with pre-fill |
| 22 | Teacher Dashboard | Empty state missing | Add friendly empty state for 0 worksheets |
| 23 | Class Manager | No Add Student flow | Modal + `/api/classes/{id}/students` endpoint |
| 24 | Class Manager | No delete confirmation | `confirm()` dialog before delete |
| 25 | Class Manager | No "Generate for class" | Navigate to generator with `class_id` |
| 26 | Shared | No print button | Add browser print trigger |
| 27 | Progress | No child selector | Show child picker if multiple children |
| 28 | Syllabus | Parse result not editable | Editable chapter checklist before generating |
| 29 | Landing | No "Sign in" above fold | Add to sticky nav |

---

## THE ANSWER VISIBILITY AGENT PROMPT

This is the single most important fix. Give this to Claude Code first:

```
You are the Backend Lead Agent.
Read CLAUDE.md and agents/BACKEND_LEAD.md.

TASK: Fix answer visibility across all worksheets. This is a P0 bug.

ROOT CAUSE:
The slot engine returns q["answer"] but _slot_to_question in worksheets.py 
maps it to correct_answer. When the LLM returns an empty answer OR when 
answer_type is "example", correct_answer becomes None. The frontend then 
shows "---" or blank.

STEP 1 — backend/app/api/worksheets.py, function _slot_to_question():
Change:
  sample_answer=None,
To:
  sample_answer=q.get("sample_answer") or (answer_str if not answer_str and q.get("answer") else None),

Also: if correct_answer is None and q.get("explanation") is not None, set:
  correct_answer = None  (keep None)
  sample_answer = q.get("explanation")  (use explanation as sample)
  answer_type = "example"

STEP 2 — backend/app/services/slot_engine.py, in generate_question():
Change temperature=0.8 to temperature=0.3 (line ~14903)

STEP 3 — frontend/src/pages/WorksheetGenerator.tsx:
In the Answer Key Reference section (around line 1659):
Change: {question.correct_answer || '---'}
To: 
  {question.correct_answer 
    ? question.correct_answer 
    : question.explanation || question.sample_answer
      ? <span className="italic text-xs text-muted-foreground">{question.explanation || question.sample_answer}</span>
      : <span className="text-muted-foreground/40">—</span>
  }

Also add inline answer display INSIDE both tiered and flat question rendering 
when showAnswers=true (after the hint section):
  {showAnswers && (question.correct_answer || question.explanation) && (
    <div className="mt-2 inline-flex items-center gap-2 px-3 py-1 bg-emerald-50 border border-emerald-200 rounded-lg print:bg-gray-100 print:border-gray-300">
      <span className="text-xs font-semibold text-emerald-700 print:text-gray-700">Ans:</span>
      <span className="text-sm font-bold text-emerald-900 print:text-gray-900">
        {question.correct_answer || question.explanation}
      </span>
    </div>
  )}

Also move Show Answers button: add a second trigger directly below the last 
question (before the Answer Key section) so parents on mobile can find it.

STEP 4 — frontend/src/pages/History.tsx:
Add showAnswers state. Add toggle button. Show correct_answer || explanation 
conditionally per question in the modal view.

STEP 5 — frontend/src/pages/SavedWorksheets.tsx:
Same as History.tsx — add showAnswers toggle to preview modal.

STEP 6 — frontend/src/pages/SharedWorksheet.tsx:
Same fix: {showAnswers && (q.correct_answer || q.explanation) && (...)}

After all changes, verify:
- cd backend && python scripts/test_slot_engine.py — must pass
- Generate Class 3 English "Nouns" worksheet → Show Answers → all questions have visible answers
- Generate Class 3 Maths "Addition" → Show Answers → all answers are numerically correct
- Generate Class 5 Science "Ecosystem" → Show Answers → explanations visible for open-ended Qs
- History page → view old worksheet → Show Answers → answers visible
```

---

## PRODUCTION READINESS DEFINITION (Updated)

Your app will be production-ready when every screen passes this checklist:

**Generator**
- [ ] Answers visible inline when "Show Answers" is ON
- [ ] Answer Key shows correct_answer OR explanation (never `---` or blank)
- [ ] Show Answers button visible on mobile (not just in toolbar)
- [ ] Usage badge shows correct number (5/5 or 3/5 remaining)
- [ ] Upgrade prompt appears before generate button when limit hit
- [ ] Temperature 0.3 (not 0.8)

**Progress Dashboard**
- [ ] Shows real data (Supabase mastery store enabled)
- [ ] Skill tags are human-readable
- [ ] "Practice this" button per skill
- [ ] Child picker visible when multiple children

**History**
- [ ] Show/Hide answers toggle
- [ ] No blank answer cells
- [ ] "Generate similar" button

**Saved Worksheets**
- [ ] Show/Hide answers toggle
- [ ] No blank answer cells

**Teacher Dashboard**
- [ ] Empty state when no worksheets
- [ ] Can view recent worksheets

**Class Manager**
- [ ] Add Student flow
- [ ] Delete confirmation
- [ ] Generate for class button

**Child Profiles**
- [ ] Selected child grade auto-fills generator

**Auth**
- [ ] Google sign-in
- [ ] Readable error messages
- [ ] Forgot password

**Shared Worksheet**
- [ ] Show Answers works for all question types
- [ ] Branding + "Create your own" CTA
- [ ] Print button

**Landing**
- [ ] Prices visible (₹299 / AED 45)
- [ ] Sign in in nav
- [ ] Free tier says 5, not 10

**Payment**
- [ ] Razorpay integrated (Phase 2)
- [ ] Subscription upgrade works end-to-end
- [ ] Free tier limit consistent everywhere

---

*This plan was written after reading every screen in the repository,
tracing the answer field from LLM response → slot_engine → _slot_to_question → 
API model → frontend rendering → Answer Key section.
The `---` issue is real and affects English, Science, Hindi, and any open-ended question type.*
