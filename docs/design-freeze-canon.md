# PracticeCraft AI — Design Freeze Canon

## Purpose

This document is the single canonical record of every completed UX, UI, and state-management decision in PracticeCraft AI. It exists so that any engineer or designer joining the project can understand *what was built, why it was built that way, and what must not change without an explicit product decision*.

**This document is NOT:**
- A backlog or feature wishlist
- A place for future ideas or proposals
- A critique of past decisions
- A living design spec (it is frozen)

---

## Core Design Principles

1. **Calm, parent-first UX.** Every screen should feel appropriate for a quiet evening at home or a school staff room. No urgency, no pressure.
2. **Skill-first mental model.** Skills are the primary selection axis. Topics are supplementary context, shown only when the worksheet type demands chapter scope.
3. **Print credibility.** The worksheet preview must look like a real printed page. What you see on screen is what prints. No UI chrome leaks into output.
4. **No hype, no noise.** No marketing language in the product UI. No "AI-powered magic." Calm, factual microcopy throughout.
5. **Explicit user actions only.** Nothing generates, saves, or sends without the user clicking a clear button. No surprise side-effects.

---

## Phase-by-Phase Summary

### Phase 1–2: Microcopy & Typography

**Problem:** Default UI copy was mechanical and generic ("Generate Worksheet," "Loading..."). Typography lacked warmth and academic character.

**Key decisions:**
- Replaced all action labels with reassuring language: "Create today's practice," "Print or save," "Preparing practice aligned to your syllabus..."
- Empty states provide guidance, not dead-ends: "No worksheets yet — create one in under a minute."
- Fraunces serif for H1/H2 page titles only. Plus Jakarta Sans for everything else.
- `font-bold` (never `font-black`), `rounded-2xl` for cards, `rounded-xl` for buttons, `h-11` for inputs.

**Non-goals:** No illustration system. No animated mascots. No gamified language.

---

### Phase 3: Split-Screen Workspace

**Problem:** Vertical stacking of form + preview forced users to scroll between controls and output. No sense of a professional editor workspace.

**Key decisions:**
- Desktop: 40% left panel (controls) / 60% right panel (preview), separated by `lg:gap-10`.
- Right panel is `lg:sticky` so the preview stays visible while scrolling controls.
- Mobile: single view with a floating Edit/Preview toggle pill at the bottom.
- Auto-switch to preview on mobile after successful generation.

**Non-goals:** No drag-to-resize panels. No collapsible sidebar. No tabbed sections.

---

### Phase 4: Landing Page

**Problem:** No pre-login experience. Users landed directly on an auth form with no product context.

**Key decisions:**
- Single-screen hero with one headline, one subline, two CTAs.
- Headline: "Create calm, syllabus-aligned practice for Classes 1-5."
- No testimonials, no pricing table, no feature grid, no stock imagery.
- Footer trust line: "Aligned with NCERT and commonly followed CBSE school curricula."

**Non-goals:** No multi-section marketing page. No animated scroll effects.

---

### Phase 5: Navigation Simplification

**Problem:** Navigation was identical for parents and teachers despite different workflows.

**Key decisions:**
- Teachers see: Dashboard | Classes | Practice | Saved.
- Parents see: Practice | Saved | Syllabus | Profile.
- Desktop: horizontal tabs in header. Mobile: fixed bottom nav bar.
- User dropdown contains region toggle, role switch, and sign-out.

**Non-goals:** No breadcrumbs. No sidebar navigation. No hamburger menu.

---

### Phase 6: Empty, Loading & Error States

**Problem:** Missing data states showed blank screens or raw error text. No loading feedback.

**Key decisions:**
- Every list page has three explicit states: loading (skeletons), empty (icon + guidance + CTA), and populated.
- Skeletons match the dimensions of final content to prevent layout shift.
- Errors use `bg-destructive/5` with icon, always dismissible.
- Success toasts auto-dismiss after 3 seconds.

**Non-goals:** No toast notification library. No global error boundary UI.

---

### Phase 7: Visual Consistency Pass

**Problem:** Inconsistent sizing, weight, and rounding across pages accumulated during rapid feature development.

**Key decisions:**
- Normalized all pages: `font-black` to `font-bold`, `rounded-3xl` to `rounded-2xl`, oversized buttons (`py-7`) to `py-4`, `p-7` to `p-6`.
- Mechanical placeholder text replaced with contextual guidance ("Select grade," "Select subject").
- Applied consistently across ClassManager, TeacherDashboard, SyllabusUpload, App.tsx, SavedWorksheets.

**Non-goals:** No new component library. No design token refactor.

---

### Phase 8: Visual Hierarchy Softening

**Problem:** The worksheet generator left panel felt like a dense form. Step indicators and bordered sections added unnecessary visual weight.

**Key decisions:**
- Worksheet preview card: `shadow-2xl` reduced to `shadow-xl`, border opacity lowered to `border/20`, explicit `bg-white`.
- Top accent bar: `h-1.5` reduced to `h-px`, opacity lowered to `primary/15`.
- Question numbers: solid dark squares replaced with soft bordered circles (`rounded-full border-2 border-foreground/15`).
- Increased padding inside the preview card (`px-10 pb-14`).

**Non-goals:** No color theme changes. No new decorative elements.

---

### Phase 9: Left Panel De-boxing

**Problem:** The left controls panel was wrapped in a Card with bordered Sections and numbered step indicators, making it feel like a rigid form rather than a guided workspace.

**Key decisions:**
- Removed Card/CardContent/Section wrappers entirely. Replaced with plain `div` containers.
- Section titles became subtle uppercase labels: `text-[11px] font-semibold text-muted-foreground/70 tracking-wide`.
- Student Profile section anchored with a tinted background (`bg-secondary/25 border border-border/30 rounded-xl`).
- Sections separated by `space-y-7` instead of borders or dividers.

**Non-goals:** No accordion/collapsible sections. No wizard/stepper pattern.

---

### Phase 10: Print & PDF Readiness

**Problem:** Printed output included UI chrome, lacked page breaks, and didn't match the on-screen preview.

**Key decisions:**
- `@page` rule: A4, 18mm top/bottom, 15mm left/right margins.
- Print body font: Georgia serif, 14px, black on white.
- `.paper-texture::before` hidden in print. All shadows, borders, and radii stripped from worksheet card.
- Questions: `break-inside: avoid`. Answer key: `break-before: page`.
- All animations and transitions disabled in print.

**Non-goals:** No custom PDF renderer. No header/footer on printed pages beyond watermark.

---

### Phase 11: Background Texture & Watermark

**Problem:** Large empty background areas felt flat. Generated worksheets had no attribution.

**Key decisions:**
- `.bg-paper-texture`: SVG fractal noise at 1.8% opacity, applied to landing hero and workspace background. Hidden in print.
- Worksheet watermark: "Generated using PracticeCraft" at bottom of preview card, `text-foreground/[0.04]` on screen, `text-black/[0.05]` in print.
- Backend PDF service: same watermark drawn at page bottom via reportlab canvas callback, 7pt Helvetica, light grey.

**Non-goals:** No logo watermark. No background images or illustrations.

---

### Phase 12: Role Integrity Fix

**Problem:** Changing region caused the app to silently switch the user's active role back to their base role.

**Key decisions:**
- Root cause: `setRegion` in ProfileProvider omitted `active_role` from the PUT payload. Backend defaulted missing `active_role` to `request.role`.
- Fix: include `active_role: profile.active_role` in the region-update payload.
- Rule established: role must never change unless the user explicitly switches it.

**Non-goals:** No role-locking mechanism. No confirmation dialog on role switch.

---

### Phase 13: Region Dependency Refresh

**Problem:** Changing region did not update available subjects until a full page refresh.

**Key decisions:**
- Added a `useEffect` on `region` that resets `subject`, `topic`, `selectedSkills`, `selectedLogicTags`, and `selectedTopics`.
- The existing subjects-fetch effect already had `region` in its dependency array, so subjects re-fetch automatically. The missing piece was clearing stale selections.

**Non-goals:** No region-specific UI themes. No region auto-detection.

---

### Phase 14: Field Order & Template Card Softening

**Problem:** Subject appeared visually before Grade in the 2-column layout, breaking the natural top-down selection flow. Template cards were heavier than surrounding controls.

**Key decisions:**
- Flattened the selection grid so fields flow: Board | Grade (row 1) then Subject | Topic (row 2).
- Template cards: `border-2` reduced to `border`, `shadow-sm` removed from selected state, border/background opacity lowered (`border-primary/60`, `bg-primary/[0.03]`).

**Non-goals:** No single-column form layout. No progressive disclosure.

---

### Phase 15: Topic Contextualization

**Problem:** Topic dropdown was redundant alongside the skill selector, since skills already define practice scope.

**Key decisions:**
- Topic dropdown hidden by default in the curriculum skill-first flow.
- Shown only when `selectedTemplate === 'chapter-test'` (chapter-bounded scope).
- On template switch away from chapter-test: topic cleared to empty.
- Validation unchanged: curriculum flow requires skills, not topic.

**Non-goals:** No topic-to-skill filtering. No dynamic skill narrowing based on topic.

---

### Phase 16: Generation State Integrity

**Problem:** Switching Subject A + Topic A then Subject B + Skills B before generating could leak stale selections into the worksheet payload.

**Key decisions:**
- Added `selectionVersionRef` (useRef counter) that increments on any selection change.
- `handleGenerate` captures version before API call; discards response if version changed during flight.
- Grade onChange now cascades: clears subject, topic, skills, and selectedTopics.
- Subject onChange now also clears `selectedTopics`.

**Non-goals:** No debounced generation. No draft/autosave system. No undo.

---

## Canonical UX Rules (Must Not Be Broken)

1. **Role never changes implicitly.** Only `switchRole()` or explicit user action in the dropdown may change `active_role`.
2. **Region/Board/Grade changes invalidate dependent state.** Subject, topic, and skills must be cleared and re-fetched.
3. **Worksheets generate ONLY on explicit user action.** The "Create today's practice" button is the sole trigger. No auto-generation on selection change.
4. **Skills are primary; Topics are contextual.** The skill selector is the default input. Topic dropdown appears only for chapter-bounded templates.
5. **Preview must match print/PDF output.** The right panel preview is the source of truth for what the user will receive on paper.
6. **Stale async results are discarded.** Any API response received after selections have changed is silently dropped.

---

## Known Tradeoffs (Intentional)

**Simplicity over feature density.** The product deliberately has fewer controls than competing worksheet generators. Each field earns its place by being necessary for generation quality. This reduces cognitive load for parents who are not educators.

**Contextual hiding over always-visible controls.** The topic dropdown, class/child selectors, and answer key section are conditionally rendered. This reduces clutter for the common case at the cost of discoverability for edge cases. Accepted because the hidden controls appear automatically when relevant.

**Visual restraint over engagement optimization.** No confetti, no streaks dashboard, no gamified progress bars in the main flow. The engagement feedback (star + streak) appears only after a completed download, and dismisses on click. This is intentional: the product serves adults managing children's education, not children directly.

**Single-page generation over multi-step wizard.** All controls are visible in one scrollable panel rather than spread across steps. This was chosen because the total number of required fields (5-6) does not justify wizard overhead, and experts benefit from seeing everything at once.

---

## Design Freeze Declaration

The UI/UX of PracticeCraft AI is frozen as of the completion of Phase 16. All phases documented above represent final, shipped decisions.

Any change to layout, copy, interaction patterns, state management rules, or visual design beyond this point requires an explicit product decision with a written rationale. Bug fixes to existing behavior are permitted; new behavior is not.

---

## Appendix

### Terminology

| Term | Definition |
|------|-----------|
| **Skill** | A specific learning competency from the curriculum canon (e.g., "2-digit addition with regrouping"). Primary axis for worksheet generation. |
| **Topic** | A chapter-level subject area (e.g., "Addition," "Fractions"). Secondary context, shown only for chapter-bounded templates. |
| **Worksheet Type** | A template that pre-fills difficulty, question count, and custom instructions. Values: Weekly Practice, Chapter Test, Revision Sheet, Custom. |
| **Role** | Parent or Teacher. Determines navigation tabs, class/child selectors, and PDF export options. |
| **Active Role** | The currently selected role. A user may have both roles but operates in one at a time. |
| **Region** | India or UAE. Determines curriculum source for subjects and skills. |
| **Curriculum Flow** | The skill-first generation path, active when curriculum subjects are available for the selected grade and region. |
| **Selection Version** | A ref-based counter incremented on any form change, used to detect and discard stale async results. |

### Guidance for Future Contributors

Before changing any UX:
1. Read this document in full.
2. Identify which phase your change intersects with.
3. Confirm the change does not violate any rule in "Canonical UX Rules."
4. If the change contradicts a "Key decision" from any phase, it requires a product-level sign-off, not just an engineering review.
5. Run print preview after any layout change to verify print output is unaffected.
