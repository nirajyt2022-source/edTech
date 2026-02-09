# PracticeCraft AI - Enterprise UI Upgrade Guide

**Version:** 1.0  
**Last Updated:** 2026-02-09

---

## UI Direction & Principles

### Visual Strategy: HYBRID
- **Neutral base:** Use neutral grays for backgrounds, surfaces, borders, and most text
- **Brand accents:** Apply forest green (primary) and amber (accent) sparingly—for CTAs, highlights, badges
- **Target aesthetic:** Notion / Linear / Stripe cleanliness with subtle academic warmth
- **Avoid:** Theme-heavy design; brand colors should not dominate

### Typography Rules
- **H1 / H2:** Use `Fraunces` (serif) for page titles only
- **H3 / H4, body, labels, buttons, forms, tables:** Use `Plus Jakarta Sans` (sans-serif)
- **Hierarchy:** Clear distinction between heading levels

### Motion Guidelines
- **Minimal motion only**
- **Allowed:** Subtle hover/focus transitions, dropdown open/close, collapsible sections
- **Scale-on-hover:** Only for primary CTAs or clickable cards, max `scale(1.02)`
- **Avoid:** Jarring animations, bounces, excessive transforms

---

## Design System Tokens

### Color Palette

```css
/* Neutral Base */
--color-background: hsl(0 0% 98%)        /* Page background (near-white) */
--color-surface: hsl(0 0% 100%)          /* Card/surface background (white) */
--color-border: hsl(0 0% 90%)            /* Borders and dividers */
--color-text: hsl(0 0% 10%)              /* Body text (near-black) */
--color-text-muted: hsl(0 0% 45%)        /* Secondary text */

/* Brand Accents (use sparingly) */
--color-primary: hsl(160 45% 22%)        /* Forest green */
--color-primary-foreground: hsl(0 0% 100%)
--color-accent: hsl(42 75% 52%)          /* Warm amber */
--color-accent-foreground: hsl(0 0% 10%)

/* Semantic States */
--color-success: hsl(142 76% 36%)
--color-warning: hsl(38 92% 50%)
--color-error: hsl(0 72% 51%)
--color-info: hsl(199 89% 48%)
```

### Spacing Scale
Use **multiples of 4px** for consistency:
- `4px` (0.25rem) — tight spacing
- `8px` (0.5rem) — compact
- `12px` (0.75rem) — comfortable
- `16px` (1rem) — standard gap
- `24px` (1.5rem) — section spacing
- `32px` (2rem) — large spacing
- `48px` (3rem) — section breaks
- `64px` (4rem) — major dividers

### Typography Scale

```css
/* Headings (Fraunces for H1/H2 only) */
H1: 2.25rem (36px) / font-weight: 600 / line-height: 1.2
H2: 1.875rem (30px) / font-weight: 600 / line-height: 1.25

/* Headings (Plus Jakarta Sans for H3/H4) */
H3: 1.5rem (24px) / font-weight: 600 / line-height: 1.3
H4: 1.25rem (20px) / font-weight: 600 / line-height: 1.4

/* Body (Plus Jakarta Sans) */
Body: 0.9375rem (15px) / font-weight: 400 / line-height: 1.6
Small: 0.875rem (14px) / font-weight: 400 / line-height: 1.5
Caption: 0.75rem (12px) / font-weight: 400 / line-height: 1.4
```

---

## App Shell Standards

### Layout Primitives

#### PageHeader Component
**Purpose:** Standardize top section of every page  
**Structure:**
```tsx
<PageHeader>
  <PageHeader.Title>Page Title</PageHeader.Title>
  <PageHeader.Subtitle>Optional description</PageHeader.Subtitle>
  <PageHeader.Actions>
    <Button>Primary Action</Button>
  </PageHeader.Actions>
</PageHeader>
```

**Rules:**
- H1 or H2 for title (Fraunces)
- Subtitle uses muted text
- Actions slot right-aligned on desktop, full-width on mobile
- Margin bottom: `32px` (2rem)

#### Section Component
**Purpose:** Divide page into logical sections  
**Structure:**
```tsx
<Section>
  <Section.Header>
    <Section.Title>Section Title</Section.Title>
  </Section.Header>
  <Section.Content>
    {/* content */}
  </Section.Content>
</Section>
```

**Rules:**
- H3 for section titles
- Divider line (subtle border) below header
- Margin between sections: `48px` (3rem)

#### Max Width & Padding
- **Max content width:** `max-w-6xl` (1152px) or `max-w-7xl` (1280px)
- **Page padding:** `px-4` on mobile, `px-6` on tablet+
- **Vertical padding:** `py-8` (2rem) standard

---

## Component Standards

### Button Variants

| Variant       | Use Case                     | Style                                      |
|---------------|------------------------------|--------------------------------------------|
| `primary`     | Primary CTA                  | bg-primary, text-primary-foreground        |
| `secondary`   | Secondary actions            | bg-secondary, text-secondary-foreground    |
| `outline`     | Tertiary, cancel             | border, bg-transparent                     |
| `ghost`       | Minimal actions, links       | No border, subtle hover background         |
| `destructive` | Delete, remove               | bg-error, text-white                       |

**Sizes:** `sm` (32px height), `md` (40px height), `lg` (48px height)  
**States:**
- Disabled: 50% opacity, cursor-not-allowed
- Loading: Show spinner, disable interaction
- Hover: Slight background darken (5-10%)
- Focus: Visible focus ring (2px, primary color, 2px offset)

### Input Pattern
```tsx
<div>
  <Label htmlFor="email">Email</Label>
  <Input id="email" type="email" placeholder="you@example.com" />
  {error && <InputError>{error}</InputError>}
  {helper && <InputHelper>{helper}</InputHelper>}
</div>
```

**Rules:**
- Label always visible (no floating labels)
- Error state: red border + error message below
- Helper text: muted color, 12px font size
- Consistent height with Select component

### Card
- **Padding:** `p-6` (24px) for CardContent
- **Border:** `border border-border` (subtle gray)
- **Shadow:** Minimal or none by default
- **Hover (clickable cards):** Slight border darken, no shadow jump

### EmptyState Component
**Purpose:** Guide users when list/table is empty  
**Structure:**
```tsx
<EmptyState
  icon={<Icon />}
  title="No items yet"
  description="Get started by creating your first item"
  action={<Button>Create Item</Button>}
/>
```

**Rules:**
- Center-aligned
- Icon: 48px, muted color
- Title: H4 weight
- Description: muted text
- CTA button (optional)

### Skeleton Component
**Purpose:** Loading placeholder  
**Rules:**
- Use pulsing gray background
- Match shape of content (text lines, card boxes)
- Animate with subtle pulse (not shimmer)

---

## Page-Level UX Standards

### Loading States
- **Initial load:** Show skeleton matching content layout
- **Action loading:** Disable button, show spinner inside button
- **List refresh:** Show skeleton rows

### Empty States
- **Every list/table must have an EmptyState**
- Include helpful message and CTA to first action

### Error States
- **Form validation:** Inline errors below each field
- **API errors:** Alert banner at top of form/page
- **Network errors:** Friendly message with retry button

### Success States
- **Toast/banner:** Brief confirmation message
- **Inline feedback:** Icon + text (e.g., "Saved successfully")

---

## Page-Specific Rules

### Auth Page
- Premium first impression
- Clear trust indicators (security badges)
- Generous spacing between form fields
- Error/success messages prominent but not jarring

### WorksheetGenerator
- Best-in-class loading states (skeleton while generating)
- Clear empty state ("Generate your first worksheet")
- Generated worksheet displayed in polished card
- Form sections visually separated

### SavedWorksheets
- Scannable list/table with hover states
- Skeleton loading while fetching
- Empty state with CTA to create first worksheet
- Date formatting: short, human-readable

### ChildProfiles
- Trustworthy form design (clear labels, validation)
- Modal polish (clean, centered, accessible)
- Empty state for first-time parents

### SyllabusUpload
- Drag-and-drop zone with clear affordances
- Parsing feedback: loading → success → error
- Preview of parsed syllabus (clean, readable)

### TeacherDashboard
- Clean stat cards (comfortable spacing)
- Skeleton loading for recent worksheets
- Empty states when no classes/worksheets
- Slightly more compact than parent view (but still readable)

### ClassManager
- Clear class cards with hover states
- Modal polish for add/edit class
- Empty state with CTA to create first class

---

## Accessibility & QA Checklist

### Keyboard Navigation
- [ ] All interactive elements reachable via Tab
- [ ] Focus rings visible on all focused elements
- [ ] Logical tab order (top to bottom, left to right)
- [ ] Escape key closes modals/dropdowns

### Color Contrast
- [ ] Text on background: minimum 4.5:1 ratio
- [ ] Icons and borders: minimum 3:1 ratio
- [ ] Run axe DevTools and fix critical issues

### Screen Readers
- [ ] All images have alt text
- [ ] Form inputs have associated labels
- [ ] Buttons have descriptive text (not just icons)

### Responsive Design
- [ ] Test at 375px (mobile), 768px (tablet), 1440px (desktop)
- [ ] Navigation collapses gracefully
- [ ] Cards stack vertically on mobile
- [ ] No horizontal scroll

### Build & Lint
- [ ] `pnpm run lint` — no errors
- [ ] `pnpm run build` — successful
- [ ] `pnpm run preview` — works in production build
- [ ] No console errors in browser

---

## Implementation Order

**Phase 1: Foundation**
1. App Shell (PageHeader, Section components)
2. Design tokens (colors, spacing, typography)
3. Core components (Button, Input, Select, Card)
4. Utility components (EmptyState, Skeleton)

**Phase 2: Pages (Priority Order)**
1. Auth
2. WorksheetGenerator
3. SavedWorksheets
4. ChildProfiles
5. SyllabusUpload
6. TeacherDashboard
7. ClassManager

**Phase 3: Polish & Verification**
- Accessibility audit
- Responsive testing
- Cross-browser testing

---

## Future Extension Guidance

### Adding New Pages
1. Use `PageHeader` for title and primary action
2. Divide into logical `Section` components
3. Include loading, empty, and error states
4. Test responsive behavior

### Adding New Components
1. Follow shadcn/ui pattern (variants via class-variance-authority)
2. Define clear variants and sizes
3. Document usage in this file
4. Ensure accessibility (ARIA labels, keyboard support)

### Maintaining Consistency
- Refer to this document before implementing new UI
- Use design tokens (spacing, colors) instead of arbitrary values
- When in doubt, reference Notion/Linear/Stripe for patterns

---

**End of Document**
