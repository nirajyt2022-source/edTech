# PracticeCraft — Complete Unified Production Plan
## Design, UX, Bugs, and Experience — Everything in One Place

---

## THE BRUTAL HONEST AUDIT

Before telling you what to fix, here's what I found reading every single file:

### The Big Problem Nobody Mentioned: Two Different Apps

Your **Landing page** and your **app** are visually unrelated products.

| | Landing Page | App Screens |
|---|---|---|
| Font | `Playfair Display` | `Fraunces` (serif) + `Plus Jakarta Sans` |
| Primary color | `indigo-600` (`#4f46e5`) | Forest green `hsl(160 45% 22%)` |
| Background | `bg-white` / `text-slate-*` | `gradient-bg` / CSS design tokens |
| Cards | `rounded-2xl border border-slate-100 shadow-[0_2px_8px]` | `rounded-lg bg-secondary/20 border border-border/50` |
| Buttons | `bg-indigo-600 rounded-lg` | `bg-primary rounded-md` (shadcn Button) |
| Component system | Raw HTML + Tailwind classes | shadcn/ui components |

A parent clicks "Try Free" on the landing page (indigo, clean white, Playfair Display), enters the app, and lands in a different visual world (forest green gradient, Fraunces serif, muted tones). This breaks trust.

**Decision to make:** Which system wins? My recommendation: **the app's design system wins**. The CSS tokens are cleaner, shadcn/ui components are consistent, and the green/warm palette is more trustworthy for an education product. The Landing page needs to be ported to match.

**This means:** Replace `indigo-600` → `primary` everywhere in Landing. Replace `Playfair Display` → `Fraunces`. Replace raw `slate-*` → CSS tokens. Use shadcn `Button` components.

---

### Other Major Findings

1. **Mobile nav overlap** — Fixed bottom nav (`h-12`) exists in App.tsx but `<main>` has zero padding-bottom. Every screen's content is hidden behind the mobile nav on phone screens. No page adds `pb-16` or `pb-20`.

2. **No toast system** — Zero screens use toast notifications. Success actions (save worksheet, copy link, submit grades) happen silently. Users have no feedback.

3. **13 form fields on generator at once** — Parents see Board, Grade, Subject, Chapter, Topic, Difficulty, Questions count, Language, Generate for (child/class), Child selector, Visual mode, Mix recipe — all simultaneously. Overwhelming on mobile.

4. **ClassManager uses `indigo-500`** — Mixed in with the forest green theme. Leftover from an old design.

5. **No page greeting on Parent Dashboard** — Teacher dashboard has `getGreeting()` with "Good Morning". Parent dashboard has none. Inconsistent.

6. **History and Saved have no search** — Both are paginated lists with no way to find "the fractions worksheet I did last Tuesday."

7. **No avatar/initials on Child Profiles** — Each child is shown as a name in a card with no visual identifier. Multi-child families can't quickly scan.

8. **No toast on any action** — Saving a worksheet, sharing, copying link — all happen silently.

9. **Auth doesn't collect full name** — The placeholder says "Your name" but only email/password are required. After signup, the user's display name is their email prefix. Jarring.

10. **`<main>` has no top padding on mobile** — Content starts directly under the sticky nav. First card is partially hidden behind nav on mobile.

---

## THE UNIFIED DESIGN SYSTEM

### One Source of Truth

The app already has a clean design system in `index.css`. Everything should use it.
The Landing page needs to be ported to match.

**The token-to-class mapping:**
```
Forest green primary  → bg-primary / text-primary / border-primary
Body text             → text-foreground
Muted text            → text-muted-foreground  
Card background       → bg-card / bg-white
Page background       → bg-background
Borders               → border-border
Amber accent          → text-accent / bg-accent
```

**The component hierarchy:**
```
Page wrapper:     max-w-7xl mx-auto px-4 sm:px-6 pb-20 pt-6
Section heading:  font-fraunces (Fraunces) text-2xl font-semibold text-foreground
Body text:        text-sm text-muted-foreground
Cards:            bg-card rounded-xl border border-border shadow-sm p-5
CTAs:             <Button> (shadcn) — primary variant
Secondary:        <Button variant="outline">
Destructive:      <Button variant="destructive">
```

**The typography rule:**
- Page/section titles: `font-serif` (Fraunces) — already in `index.css` as h1/h2
- Everything else: `Plus Jakarta Sans` (body font, already default)
- NO Playfair Display anywhere (that's Landing only, and will be replaced)

---

## AGENT PLAN — 7 Agents, 1 Output: A Unified App

Each agent owns one domain. Sequential. Hard gate before next starts.

```
AGENT 0  — Design Token Unification (1 session, 2 hours)
AGENT 1  — Answer Visibility Fix (1 session, 3 hours)  ← from previous plan
AGENT 2  — Generator UX Redesign (1 session, 4 hours)
AGENT 3  — Dashboard + Progress UX (1 session, 3 hours)
AGENT 4  — History + Saved UX (1 session, 3 hours)
AGENT 5  — Auth + Shared + Teacher (1 session, 3 hours)
AGENT 6  — Global Polish: Toast, Mobile, Search (1 session, 4 hours)
```

---

# AGENT 0 — DESIGN TOKEN UNIFICATION
## "One visual language across every screen"

**Read first:** `CLAUDE.md`, `agents/FRONTEND_LEAD.md`, `docs/ui-enterprise-upgrade.md`

### 0-Task-1: Port Landing page to app design system

**Files to change:** `frontend/src/pages/Landing.tsx`

Replace every `indigo-*` → equivalent primary:
```bash
# In Landing.tsx:
bg-indigo-600  →  bg-primary
hover:bg-indigo-700  →  hover:bg-primary/90
text-indigo-600  →  text-primary
border-indigo-600  →  border-primary
shadow-indigo-600/20  →  shadow-primary/20
```

Replace font references:
```bash
font-['Playfair_Display',Georgia,serif]  →  font-serif
# (font-serif is already mapped to Fraunces in index.css h1/h2)
```

Replace raw color tokens:
```bash
text-slate-900  →  text-foreground
text-slate-600  →  text-muted-foreground  
text-slate-400  →  text-muted-foreground/60
text-slate-100  →  text-border
bg-white        →  bg-background (or keep bg-white — this is fine)
border-slate-100  →  border-border
bg-slate-50     →  bg-secondary/30
```

Add import for shadcn Button at the top of Landing:
```tsx
import { Button } from '@/components/ui/button'
```
Replace `<button onClick={onGetStarted} className="px-5 py-2 bg-indigo-600...">Try Free</button>` with:
```tsx
<Button onClick={onGetStarted} size="lg">Try Free</Button>
```

### 0-Task-2: Fix ClassManager indigo leak
**File:** `frontend/src/pages/ClassManager.tsx`

```bash
grep -n "indigo-500" frontend/src/pages/ClassManager.tsx
# Replace all occurrences with text-primary / bg-primary
```

### 0-Task-3: Add pb-20 to all pages (mobile nav clearance)
**The problem:** Mobile bottom nav is 48px tall. Content is hidden beneath it on every page.

**File:** `frontend/src/App.tsx`
```tsx
// Change:
<main className="animate-in fade-in duration-700">

// To:
<main className="animate-in fade-in duration-700 pb-20 md:pb-0">
```
This adds 80px bottom padding on mobile (below md breakpoint) and removes it on desktop.
This single change fixes content overlap on every screen simultaneously.

### 0-Task-4: Add global toast system
**The problem:** Zero feedback on any action across the entire app.

**Install via shadcn:** `npx shadcn@latest add toast` (or `sonner` — lighter)

Recommended: **Sonner** (simpler, better DX):
```bash
cd frontend && npm install sonner
```

**In `frontend/src/main.tsx` or `App.tsx`:**
```tsx
import { Toaster } from 'sonner'
// Add <Toaster position="top-right" richColors /> inside AppContent, above <RoleSelector />
```

**Create `frontend/src/lib/toast.ts`:**
```typescript
import { toast } from 'sonner'
export const notify = {
  success: (msg: string) => toast.success(msg),
  error: (msg: string) => toast.error(msg),
  loading: (msg: string) => toast.loading(msg),
  info: (msg: string) => toast(msg),
}
```

### 0-Validation Gate
```bash
cd frontend && npm run build && npm run lint
# Visual check: Landing page and app screens should look like the same product
# Check: indigo-600 should appear ZERO times in Landing.tsx
grep -r "indigo-" frontend/src/pages/ | grep -v "node_modules"
# Must return empty or only in Landing (none) and ClassManager (none)
```

---

# AGENT 1 — ANSWER VISIBILITY FIX
## (Same as previous plan — do this SECOND, after design unification)

See SCREEN_BY_SCREEN_PRODUCTION_FIX.md for full prompt.
Summary: temperature 0.3, `_slot_to_question` maps explanation to sample_answer, frontend shows answer inline + fallback.

---

# AGENT 2 — GENERATOR UX REDESIGN
## "From overwhelming form to guided creation"

**Read first:** `CLAUDE.md`, `agents/FRONTEND_LEAD.md`, `docs/ui-enterprise-upgrade.md`

### The Core Problem

13 form fields visible simultaneously. On mobile, a parent has to scroll past Board, Grade, Subject, Chapter, Topic, Difficulty, Questions, Language, Child selector, Class selector, Visual mode, Mix recipe — before they can generate anything.

The parent's mental model is: "I want to practise Fractions with my Class 3 daughter." They shouldn't have to think about "Board" or "Language" unless they want to.

### 2-Task-1: Progressive form — smart defaults, advanced options hidden

**In `WorksheetGenerator.tsx`**, restructure the form:

**Step 1 (always visible — 3 fields):**
```
Grade:   [Class 1 ▾]   Subject: [Maths ▾]   Topic: [Fractions ▾]
[Create today's practice →]
```

**Step 2 (collapsed "Customise" accordion — 4 fields):**
```
▶ Customise (Difficulty, Questions, Language, Generate for child/class)
```

**Step 3 (Pro-only section, hidden for free tier):**
```
▶ Advanced (Visual mode, Mix recipe) — "Elite Pro feature"
```

Implementation:
```tsx
const [showCustomise, setShowCustomise] = useState(false)

{/* Main 3 fields */}
<div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
  <GradeSelect value={gradeLevel} onChange={setGradeLevel} />
  <SubjectSelect value={subject} onChange={setSubject} loading={curriculumLoading} />
  <TopicSelect value={topic} onChange={setTopic} />
</div>

{/* Customise accordion */}
<button
  onClick={() => setShowCustomise(!showCustomise)}
  className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mt-3"
>
  <ChevronDownIcon className={`w-4 h-4 transition-transform ${showCustomise ? 'rotate-180' : ''}`} />
  Customise worksheet
</button>
{showCustomise && (
  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-3 pt-3 border-t border-border/50 animate-in slide-in-from-top-1 duration-200">
    <DifficultySelect ... />
    <QuestionsCount ... />
    <LanguageSelect ... />
    <ChildSelect ... />
  </div>
)}
```

### 2-Task-2: Smart grade auto-fill from selected child

When a child is selected → auto-set grade:
```tsx
useEffect(() => {
  const child = children.find(c => c.id === selectedChildId)
  if (child?.grade && !gradeLevel) {
    setGradeLevel(child.grade)
  }
}, [selectedChildId, children])
```

### 2-Task-3: Loading state for subject dropdown (fix the 2-3 second blank)

```tsx
<Select disabled={curriculumLoading}>
  <SelectTrigger>
    {curriculumLoading 
      ? <span className="text-muted-foreground animate-pulse">Loading subjects...</span>
      : <SelectValue placeholder="Select subject" />
    }
  </SelectTrigger>
</Select>
```

### 2-Task-4: Toast notifications on all actions

Using the `notify` helper from Agent 0:
```tsx
// On successful generation:
notify.success('Worksheet ready! ✓')

// On save:
notify.success('Worksheet saved')

// On copy share link:
notify.success('Link copied to clipboard')

// On PDF download start:
notify.loading('Preparing PDF...')

// On error:
notify.error('Generation failed. Please try again.')

// On subscription limit:
notify.error('Monthly limit reached. Upgrade for unlimited worksheets.')
```

### 2-Task-5: "Show Answers" prominent placement (from previous plan)
Already covered in SCREEN_BY_SCREEN fix — merge the answer inline display here.

### 2-Task-6: Worksheet header looks like it belongs to the app

The generated worksheet card currently starts with a `PageHeader` but the worksheet preview itself has a different visual tone (paper-like, printable).

**Keep the print-first design of the worksheet.** But improve the surrounding chrome:

```tsx
{/* Worksheet controls bar — unified look */}
<div className="sticky top-14 z-40 bg-background/95 backdrop-blur-sm border-b border-border/30 print:hidden">
  <div className="max-w-4xl mx-auto px-4 py-2 flex items-center justify-between gap-3">
    {/* Left: worksheet title */}
    <div>
      <h2 className="font-serif text-lg font-semibold text-foreground leading-tight">{worksheet.title}</h2>
      <p className="text-xs text-muted-foreground">{worksheet.grade} · {worksheet.subject} · {worksheet.difficulty}</p>
    </div>
    {/* Right: actions */}
    <div className="flex items-center gap-2">
      <Button variant="outline" size="sm" onClick={() => setShowAnswers(!showAnswers)}>
        {showAnswers ? 'Hide Answers' : 'Show Answers'}
      </Button>
      <Button variant="outline" size="sm" onClick={handleSave}>Save</Button>
      <Button size="sm" onClick={() => handleDownloadPdf('student')}>Download PDF</Button>
    </div>
  </div>
</div>
```

### 2-Validation Gate
```bash
cd frontend && npm run build && npm run lint
# Visual: generator form shows 3 fields initially, "Customise" reveals more
# Visual: loading state visible when subjects load
# Test: select a child → grade auto-fills
# Test: generate worksheet → success toast appears
# Test: save worksheet → save toast appears
```

---

# AGENT 3 — DASHBOARD + PROGRESS UX
## "Make progress feel meaningful and actionable"

**Read first:** `CLAUDE.md`, `agents/FRONTEND_LEAD.md`

### 3-Task-1: Add greeting to Parent Dashboard

```tsx
function getGreeting() {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

// In ParentDashboard render:
<div className="mb-6">
  <h1 className="font-serif text-2xl font-semibold text-foreground">
    {getGreeting()}, {user?.user_metadata?.name?.split(' ')[0] || 'there'} 👋
  </h1>
  <p className="text-sm text-muted-foreground mt-0.5">
    {selectedChild ? `${selectedChild.name}'s progress` : 'Select a child to see progress'}
  </p>
</div>
```

### 3-Task-2: Child picker at top of Progress page

```tsx
const { children } = useChildren()

{children.length > 1 && (
  <div className="flex gap-2 mb-6 overflow-x-auto pb-1">
    {children.map(child => (
      <button
        key={child.id}
        onClick={() => setSelectedChildId(child.id)}
        className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-colors border ${
          selectedChildId === child.id
            ? 'bg-primary text-primary-foreground border-primary'
            : 'bg-card text-foreground border-border hover:border-primary/50'
        }`}
      >
        <span className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-xs">
          {child.name[0].toUpperCase()}
        </span>
        {child.name}
      </button>
    ))}
  </div>
)}
```

### 3-Task-3: Make skill tags human-readable

```typescript
// In ParentDashboard.tsx, replace formatSkillTag:
function formatSkillTag(tag: string): string {
  // "mth_c3_addition_3digit_no_carry" → "3-Digit Addition"
  // "eng_c2_nouns_identify" → "Identify Nouns"
  // "sci_c4_photosynthesis_process" → "Photosynthesis"
  return tag
    .replace(/^(mth|eng|sci|hin|comp|gk|moral|health)_c\d+_/, '')  // strip subject+grade prefix
    .replace(/_/g, ' ')
    .split(' ')
    .map((w, i) => {
      if (i === 0) return w.charAt(0).toUpperCase() + w.slice(1)  // capitalize first
      if (['and', 'or', 'of', 'in', 'the', 'a'].includes(w)) return w  // keep articles lowercase
      return w.charAt(0).toUpperCase() + w.slice(1)
    })
    .join(' ')
}
```

### 3-Task-4: "Practice this" button on each skill

```tsx
{/* In skills table row */}
<div className="flex items-center justify-between">
  <div>
    <p className="text-sm font-medium">{formatSkillTag(skill.skill_tag)}</p>
    <p className="text-xs text-muted-foreground">{skill.total_attempts} attempts · {skill.accuracy}%</p>
  </div>
  <Button
    variant="ghost"
    size="sm"
    onClick={() => {
      // Navigate to generator with this topic
      // The skill_tag contains grade+subject info — extract it
      const subject = skill.skill_tag.startsWith('mth') ? 'Maths'
        : skill.skill_tag.startsWith('eng') ? 'English'
        : skill.skill_tag.startsWith('sci') ? 'Science'
        : skill.skill_tag.startsWith('hin') ? 'Hindi' : 'Maths'
      onNavigate('generator')  // pass subject+topic via app state
    }}
    className="text-primary shrink-0"
  >
    Practice →
  </Button>
</div>
```

### 3-Task-5: Teacher Dashboard — add empty state + class insight

```tsx
{analytics?.total_worksheets === 0 ? (
  <div className="text-center py-16 px-4">
    <div className="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center mx-auto mb-4">
      <BookOpenIcon className="w-8 h-8 text-primary" />
    </div>
    <h3 className="font-serif text-xl font-semibold mb-2">Your workspace is ready</h3>
    <p className="text-muted-foreground text-sm mb-6 max-w-sm mx-auto">
      Generate your first worksheet to see analytics, track topics, and build your library.
    </p>
    <Button onClick={() => onNavigate('generator')}>Create first worksheet →</Button>
  </div>
) : (
  // existing analytics content
)}
```

### 3-Validation Gate
```
Visual: Parent dashboard shows greeting with first name
Visual: Multiple children show as pill buttons at top
Visual: Skill tags read "3-Digit Addition" not "mth_c3_addition_3digit"
Click: "Practice →" on a skill → generator opens (topic doesn't need to pre-fill yet — navigation is enough)
Visual: Teacher dashboard with 0 worksheets shows beautiful empty state
```

---

# AGENT 4 — HISTORY + SAVED UX
## "Find any worksheet, grade it, use it again"

**Read first:** `CLAUDE.md`, `agents/FRONTEND_LEAD.md`

### 4-Task-1: Add search to History

```tsx
const [searchQuery, setSearchQuery] = useState('')

const filteredWorksheets = useMemo(() =>
  worksheets.filter(ws =>
    !searchQuery ||
    ws.topic.toLowerCase().includes(searchQuery.toLowerCase()) ||
    ws.subject.toLowerCase().includes(searchQuery.toLowerCase()) ||
    ws.grade.toLowerCase().includes(searchQuery.toLowerCase())
  ), [worksheets, searchQuery])

{/* Add search bar above the list */}
<div className="relative mb-4">
  <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
  <input
    value={searchQuery}
    onChange={e => setSearchQuery(e.target.value)}
    placeholder="Search topics, subjects..."
    className="w-full pl-9 pr-4 py-2 rounded-lg border border-border bg-card text-sm focus:outline-none focus:ring-2 focus:ring-ring"
  />
</div>
```

### 4-Task-2: Add Show/Hide Answers toggle to History modal
(Full code in SCREEN_BY_SCREEN_PRODUCTION_FIX.md)

### 4-Task-3: Fix blank answer cells in History modal
(Full code in SCREEN_BY_SCREEN_PRODUCTION_FIX.md)

### 4-Task-4: "Generate similar" button in History

```tsx
<Button
  variant="outline"
  size="sm"
  onClick={() => {
    // Pre-fill generator and navigate
    onNavigateToGenerator({
      grade: ws.grade,
      subject: ws.subject,
      topic: ws.topic,
    })
  }}
>
  Generate similar
</Button>
```
This requires passing the pre-fill state up to App.tsx and down to WorksheetGenerator.
**App.tsx change:** Add `generatorPreFill` state:
```tsx
const [generatorPreFill, setGeneratorPreFill] = useState<{grade?:string,subject?:string,topic?:string} | null>(null)
// Pass to WorksheetGenerator as prop
// Pass setter to History/Saved as onNavigateToGenerator callback
```

### 4-Task-5: Add search to Saved Worksheets (same pattern as History)

### 4-Task-6: Add print button to Saved Worksheets modal

```tsx
<Button variant="outline" size="sm" onClick={() => window.print()}>
  Print / PDF
</Button>
```

### 4-Validation Gate
```
Type "Fraction" in History search → only fraction worksheets show
Click "Generate similar" on a history item → generator opens
History modal: Show Answers button visible and works
Saved modal: Show Answers button visible and works
Saved modal: Print button triggers browser print
```

---

# AGENT 5 — AUTH + SHARED + TEACHER SCREENS
## "Professional first impression and viral growth"

**Read first:** `CLAUDE.md`, `agents/FRONTEND_LEAD.md`

### 5-Task-1: Google sign-in on Auth page

```tsx
const handleGoogleSignIn = async () => {
  const { error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo: `${window.location.origin}/` }
  })
  if (error) notify.error('Google sign-in failed. Try email instead.')
}
```

**UI change — add above the email form:**
```tsx
<button
  onClick={handleGoogleSignIn}
  className="w-full flex items-center justify-center gap-3 py-2.5 px-4 border border-border rounded-xl hover:bg-secondary/50 transition-colors text-sm font-medium"
>
  <svg className="w-5 h-5" viewBox="0 0 24 24">
    {/* Google G icon SVG — use standard 4-color Google G */}
  </svg>
  Continue with Google
</button>

<div className="relative my-5">
  <div className="absolute inset-0 flex items-center">
    <div className="w-full border-t border-border" />
  </div>
  <div className="relative flex justify-center text-xs text-muted-foreground">
    <span className="bg-background px-2">or continue with email</span>
  </div>
</div>
{/* email/password form below */}
```

**Enable in Supabase Dashboard:** Auth → Providers → Google → enable, add Google OAuth client ID/secret.

### 5-Task-2: Better Auth errors + Forgot Password

```tsx
const AUTH_ERRORS: Record<string, string> = {
  'Invalid login credentials': 'Wrong email or password.',
  'Email not confirmed': 'Check your inbox for a confirmation email.',
  'User already registered': 'Account exists. Sign in instead.',
  'Email rate limit exceeded': 'Too many attempts. Wait 60 seconds.',
  'Password should be at least 6 characters': 'Password must be at least 6 characters.',
}

const handleForgotPassword = async () => {
  if (!email) { setError('Enter your email first'); return }
  await supabase.auth.resetPasswordForEmail(email, {
    redirectTo: `${window.location.origin}/reset-password`
  })
  notify.success('Reset link sent! Check your inbox.')
}
```

**Add "Forgot password?" below password field:**
```tsx
<div className="flex justify-end mt-1">
  <button onClick={handleForgotPassword} className="text-xs text-primary hover:underline">
    Forgot password?
  </button>
</div>
```

### 5-Task-3: Auth page visual redesign (match app design system)

Current Auth has a white card but its background, typography and structure don't match the app.

```tsx
// Wrap the auth card in the app's background
<div className="min-h-screen gradient-bg flex flex-col items-center justify-center px-4">
  {/* Logo at top */}
  <div className="mb-8 flex items-center gap-2.5">
    <div className="w-9 h-9 rounded-lg bg-primary flex items-center justify-center">
      <BookIcon className="w-5 h-5 text-primary-foreground" />
    </div>
    <span className="font-serif text-xl font-semibold">
      <span className="text-foreground">Practice</span>
      <span className="text-primary">Craft</span>
    </span>
  </div>
  
  {/* Card */}
  <div className="w-full max-w-sm bg-card rounded-2xl border border-border shadow-lg p-7">
    <h1 className="font-serif text-2xl font-semibold text-foreground mb-1">
      {mode === 'signup' ? 'Create your account' : 'Welcome back'}
    </h1>
    <p className="text-sm text-muted-foreground mb-6">
      {mode === 'signup' ? 'Start with 5 free worksheets' : 'Sign in to your workspace'}
    </p>
    {/* Google + email form */}
  </div>
</div>
```

### 5-Task-4: SharedWorksheet — branding footer + print button

```tsx
{/* At the very bottom of SharedWorksheet, before closing div */}
<div className="mt-12 pt-6 border-t border-border/30 print:hidden">
  <div className="flex items-center justify-between">
    <div className="flex items-center gap-2">
      <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center">
        <BookIcon className="w-3.5 h-3.5 text-primary-foreground" />
      </div>
      <span className="text-sm font-medium text-foreground">
        Made with <span className="text-primary">PracticeCraft</span>
      </span>
    </div>
    <div className="flex items-center gap-2">
      <Button variant="outline" size="sm" onClick={() => window.print()}>Print</Button>
      <Button size="sm" onClick={() => window.location.href = '/'}>Create free →</Button>
    </div>
  </div>
</div>
```

### 5-Task-5: Class Manager fixes

Fix `indigo-500` → `text-primary` (already in Agent 0).

Add delete confirmation:
```tsx
const handleDeleteClass = async (classId: string, className: string) => {
  if (!confirm(`Delete "${className}"? All worksheets linked to this class will be unlinked. This cannot be undone.`)) return
  // proceed with delete
  notify.success(`Class "${className}" deleted`)
}
```

Add "Generate for class" button:
```tsx
<Button
  variant="outline"
  size="sm"
  onClick={() => {
    setClassId(cls.id)
    onNavigate('generator')
  }}
>
  Generate worksheet
</Button>
```

Add student count display:
```tsx
<p className="text-xs text-muted-foreground">
  {cls.student_count || 0} students
</p>
```

### 5-Validation Gate
```
Auth: Google sign-in button visible above email form
Auth: "Forgot password?" visible below password input
Auth: Wrong password shows "Wrong email or password" not generic error
Auth: Background matches app gradient-bg
SharedWorksheet: Footer with PracticeCraft branding + Print button visible
ClassManager: No indigo colors (grep should show 0)
ClassManager: Delete shows confirmation dialog
```

---

# AGENT 6 — GLOBAL POLISH
## "The difference between 'looks okay' and 'feels premium'"

**Read first:** `CLAUDE.md`, `agents/FRONTEND_LEAD.md`

### 6-Task-1: Child Profile avatars + visual identity

```tsx
const AVATAR_COLORS = [
  'bg-primary/15 text-primary',
  'bg-accent/20 text-amber-700',
  'bg-blue-100 text-blue-700',
  'bg-purple-100 text-purple-700',
]

function ChildAvatar({ name, index }: { name: string; index: number }) {
  const colorClass = AVATAR_COLORS[index % AVATAR_COLORS.length]
  return (
    <div className={`w-12 h-12 rounded-xl flex items-center justify-center font-serif text-xl font-semibold ${colorClass}`}>
      {name.charAt(0).toUpperCase()}
    </div>
  )
}
```

Each child card gets a coloured initial avatar. Multi-child families can instantly distinguish them.

### 6-Task-2: Toast on every action (wire to all screens)

Using the `notify` helpers from Agent 0, add toasts to:

**WorksheetGenerator.tsx:**
- `notify.success('Worksheet ready!')` after generation completes
- `notify.success('Saved to your library')` after save
- `notify.success('Link copied!')` after copy share link
- `notify.error(message)` on generation failure

**History.tsx:**
- `notify.success('PDF downloading...')` on download
- `notify.error('Download failed')` on error

**SavedWorksheets.tsx:**
- `notify.success('Worksheet deleted')` on delete
- `notify.error('Delete failed')` on error

**ChildProfiles.tsx:**
- `notify.success('Profile saved')` on save
- `notify.success('Child removed')` on delete

**ClassManager.tsx:**
- `notify.success(`Class "${name}" created`)` on create
- `notify.success(`Class deleted`)` on delete

### 6-Task-3: Consistent empty states design

Every empty state should follow the same visual pattern:

```tsx
function EmptyStateCard({
  icon, title, description, action
}: {
  icon: ReactNode
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      <div className="w-14 h-14 rounded-2xl bg-primary/8 flex items-center justify-center mb-4">
        {icon}
      </div>
      <h3 className="font-serif text-lg font-semibold text-foreground mb-2">{title}</h3>
      <p className="text-sm text-muted-foreground max-w-xs mb-6">{description}</p>
      {action}
    </div>
  )
}
```

Use this consistently in History, Saved, Classes, Progress.

### 6-Task-4: Mobile nav labels + active indicator

The mobile nav uses text labels which is fine. But add a clear active state:

```tsx
// Current active state uses bg-secondary/60 — make it cleaner:
className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
  currentPage === tab.id
    ? 'text-primary font-semibold bg-primary/8'  // more visible active
    : 'text-muted-foreground'
}`}
```

### 6-Task-5: Loading skeleton consistency

Currently each page has its own loading skeleton implementation. Standardise:

```tsx
// frontend/src/components/ui/worksheet-skeleton.tsx
export function WorksheetCardSkeleton() {
  return (
    <div className="bg-card rounded-xl border border-border p-5 space-y-3">
      <div className="h-4 bg-secondary rounded w-3/4 animate-pulse" />
      <div className="h-3 bg-secondary rounded w-1/2 animate-pulse" />
      <div className="flex gap-2 mt-4">
        <div className="h-7 bg-secondary rounded-lg w-20 animate-pulse" />
        <div className="h-7 bg-secondary rounded-lg w-20 animate-pulse" />
      </div>
    </div>
  )
}
```

### 6-Task-6: Fix Auth to collect and store full name

Currently "Your name" placeholder exists but name isn't saved to user_metadata.

```tsx
// On signup, include name in signUp call:
const { error } = await supabase.auth.signUp({
  email,
  password,
  options: {
    data: { name: nameField }  // stored in user_metadata.name
  }
})
```
Add `name` field (optional) to signup form:
```tsx
{mode === 'signup' && (
  <div>
    <Label>Your name (optional)</Label>
    <Input
      value={name}
      onChange={e => setName(e.target.value)}
      placeholder="Priya Sharma"
    />
  </div>
)}
```

### 6-Validation Gate
```bash
npm run lint && npm run build
# Visual: every empty state looks the same (icon + title + description + action button)
# Visual: mobile nav active state is visible (primary color, not just gray background)
# Test: generate worksheet → toast appears top-right
# Test: save worksheet → toast appears
# Test: delete saved worksheet → toast appears
# Test: child profiles each have color initial avatar
# Test: signup with name → user menu shows first name
```

---

## HOW TO GIVE THESE TO CLAUDE CODE

### Step-by-step instructions

**Step 1: Put the plans in the repo**

Move both plan files to a readable location in your repo:
```bash
cp SCREEN_BY_SCREEN_PRODUCTION_FIX.md ./agents/AGENT_FIXES.md
cp PRACTICECRAFT_UNIFIED_PLAN.md ./agents/AGENT_UNIFIED_PLAN.md
```

**Step 2: Start Claude Code in terminal**
```bash
cd /path/to/edTech-main
claude
```

**Step 3: Agent 0 prompt (paste exactly)**
```
You are the Frontend Lead Agent.
Read CLAUDE.md, agents/FRONTEND_LEAD.md, and docs/ui-enterprise-upgrade.md before touching any code.
Then read agents/AGENT_UNIFIED_PLAN.md, section "AGENT 0 — DESIGN TOKEN UNIFICATION".

Execute all 4 tasks in order.
After each task, run: cd frontend && npm run lint
Do NOT proceed if lint has errors.
After all 4 tasks, run: cd frontend && npm run build
Report: (a) what files changed, (b) build output, (c) any errors found.
```

**Step 4: Agent 1 prompt (answer visibility)**
```
You are the Backend Lead Agent.
Read CLAUDE.md and agents/BACKEND_LEAD.md first.
Then read agents/AGENT_FIXES.md, section "THE ANSWER VISIBILITY ROOT CAUSE".

Execute all 6 steps.
After backend changes: cd backend && python scripts/test_slot_engine.py
After frontend changes: cd frontend && npm run build
Report what changed and the test output.
```

**Step 5: Agent 2-6 prompts (same pattern)**
```
You are the Frontend Lead Agent.
Read CLAUDE.md and agents/FRONTEND_LEAD.md.
Then read agents/AGENT_UNIFIED_PLAN.md, section "AGENT [N] — [NAME]".
Execute all tasks in order. Run validation gate. Report results.
```

### Important rules for Claude Code sessions

1. **One agent per session** — start a fresh `claude` session for each agent
2. **Never skip the validation gate** — if `npm run build` fails, fix it before moving on
3. **Commit after each agent** — `git commit -am "[Agent-N] description"`
4. **Check the CLAUDE.md update log** — each commit should add a line there

### If an agent gets confused

Paste this as a reset:
```
Stop. Before continuing:
1. Run: cd frontend && npm run lint
2. Run: cd backend && python scripts/test_slot_engine.py
3. Tell me what's currently broken.
Then continue from the last successful step only.
```

---

## WHAT PRODUCTION-READY LOOKS LIKE NOW

When all 7 agents are done, walk through the app as a parent:

1. **Landing** → Forest green, Fraunces font, real prices (₹299). Same visual as app.
2. **Sign up** → Google button prominent. No confusing generic errors.
3. **Generator** → 3 fields. Clean. "Customise" hidden by default. Loads in < 2s on mobile.
4. **Generate worksheet** → Toast: "Worksheet ready ✓". Show Answers button visible below last question. Clicking it reveals answers inline next to each question.
5. **Save worksheet** → Toast: "Saved". 
6. **Progress tab** → Greeting with name. Child pills if multiple. Skill tags say "3-Digit Addition" not "mth_c3_addition". Practice button on each skill.
7. **History** → Search bar. Show/Hide toggle in modal. "Generate similar" button.
8. **Shared worksheet** → Recipient sees worksheet + PracticeCraft branding + "Create your own" CTA.
9. **Mobile** → Nothing hidden behind bottom nav. Every page scrollable to last item.

That is the product that converts free users to paying users.

---

*This plan was written after auditing:*
- *Design tokens in `index.css`*
- *Landing vs App typography/color system mismatch (confirmed: two different systems)*
- *Mobile nav overlap with zero pages having pb-20 on main content*
- *Toast system: zero notifications anywhere*
- *Form field count: 13 in generator simultaneously*
- *Empty states: each page has different design*
- *ClassManager indigo leak*
- *Auth: no Google, no forgot password, name not saved*
