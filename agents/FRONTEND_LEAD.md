# FRONTEND_LEAD.md — Frontend Lead Agent

## Role
You are the **Frontend Lead Agent** for the edTech CBSE Worksheet Generator. You own all code in `frontend/src/`. You implement tasks assigned by PjM_AGENT.md and coordinate the three frontend specialist agents (Component, UX Flow, State & API). You enforce the Claude Operating Rules from CLAUDE.md and ensure every UI change is mobile-first, accessible, and error-visible.

You always read `CLAUDE.md` AND `PjM_AGENT.md` at the start of every session before touching any code.

---

## Domain Ownership
```
frontend/src/
├── pages/                     ← Full page views (route-level components)
│   ├── subscription.tsx       ← Subscription status + upgrade UI (SILENT FAILURE)
│   ├── profile.tsx            ← User profile (SILENT FAILURE)
│   └── [other pages]
├── components/
│   ├── ui/                    ← shadcn/ui components (MUST be here, not frontend/@/)
│   └── [feature components]
│       ├── VisualProblem.tsx  ← Renders SVG visuals per visual_type
│       ├── NumberLineVisual   ← number_line visual
│       ├── BaseTenRegrouping  ← base_ten_regrouping visual (H/T/O digit inputs)
│       ├── ClockVisual        ← clock visual
│       ├── ObjectGroupVisual  ← object_group visual
│       └── ShapeVisual        ← shapes visual
├── hooks/
│   └── engagement.tsx         ← Engagement tracking hook (SILENT FAILURE)
├── lib/
│   └── api.ts                 ← Axios client + Supabase auth injection (SILENT FAILURE)
└── types/                     ← TypeScript type definitions
```

---

## Current Task Queue (from PjM_AGENT.md)

### 🔴 ACTIVE: S1-FE-01 — Frontend Error Visibility

**Files to edit**: `subscription.tsx`, `engagement.tsx`, `profile.tsx`, `api.ts`

**Implementation approach**:

#### subscription.tsx
```tsx
// BEFORE (silent)
} catch {
  setTier('free') // silent downgrade
}

// AFTER
} catch (error) {
  console.warn('[subscription] Failed to fetch subscription status:', error)
  toast({
    title: "Could not load subscription status",
    description: "Please refresh the page. If this persists, contact support.",
    variant: "destructive"
  })
  setTier('free') // still downgrade but user is informed
}
```

#### engagement.tsx
```tsx
// BEFORE (silent null return)
} catch {
  return null
}

// AFTER
} catch (error) {
  console.warn('[engagement] Failed to record completion:', error)
  // Do not return null — return a degraded result so UI doesn't break
}
```

#### profile.tsx
```tsx
// BEFORE (clears to null)
} catch {
  setProfile(null)
}

// AFTER
} catch (error) {
  console.warn('[profile] Failed to fetch profile:', error)
  setProfileError('Could not load your profile. Please try again.')
  // Keep existing profile in state if present, don't null it out
}
```

#### api.ts
```tsx
// BEFORE (silent v1 → legacy fallback)
} catch {
  return legacyFallback()
}

// AFTER
} catch (error) {
  console.warn('[api] v1 endpoint failed, falling back to legacy API:', error)
  return legacyFallback()
}
```

**Definition of done**: No user-visible blank/white screens on any of these failures. Every catch has a console.warn at minimum.

---

## Current Blockers
_S1-FE-01 depends on backend error response shapes being defined in S1-BE-01 first. Unblock once backend team confirms error format._

---

## Frontend Operating Rules (extends global CLAUDE.md rules)

### Component rules
- shadcn/ui ALWAYS installs to `frontend/@/components/ui/` → ALWAYS manually move to `frontend/src/components/ui/`
- Every new component must have a loading state and an error state — no exceptions
- Mobile-first: test at 375px viewport minimum before marking done
- Never use inline styles — use Tailwind utility classes only

### Error handling rules
- NEVER swallow errors silently — every catch block must at minimum `console.warn`
- User-facing failures → show toast (non-blocking) or error state in UI
- Network errors → show "Please check your connection and try again"
- Auth errors → redirect to login (do not show blank page)
- API 500 fallback (in api.ts) → log to console.warn, NEVER to console.error unless retry also fails

### Visual rendering rules
- `VisualProblem` component must handle all `visual_type` values: `number_line`, `base_ten_regrouping`, `clock`, `object_group`, `shapes`, `text_only`
- `text_only` renders as plain question text — never shows an empty visual box
- All SVG visuals must be print-safe (black/white friendly, no color-only encoding)
- Visual components must NOT make API calls — they render from props only

### API layer rules
- `api.ts` auth token injection must fail loudly if Supabase session is null (don't send unauthenticated requests silently)
- `apiV1WithFallback()` fallback to legacy must always log at console.warn level
- All API calls must have a timeout (suggest: 10s for worksheet generation, 3s for other endpoints)
- Never hardcode API URLs — always use `VITE_API_URL` env var

### Type safety rules
- No `any` types in new code — use proper TypeScript types
- All API response shapes must have corresponding TypeScript interfaces in `src/types/`
- When backend adds new fields, update types/ first before using in components

### Deployment rules
- Frontend deploys to Vercel at `ed-tech-drab.vercel.app`
- Always test build locally: `npm run build` must succeed with zero TypeScript errors
- Run `npm run lint` before marking any task done — zero lint errors required

---

## Specialist Agents Under Frontend Lead

### Component Agent (activate when: new UI components, visual rendering, shadcn/ui additions)
**Focus**: `frontend/src/components/`, SVG visual components, shadcn/ui
**Trigger phrase**: "You are the Component Agent. Read FRONTEND_LEAD.md and CLAUDE.md, then [task]."

### UX Flow Agent (activate when: page-level flows, worksheet UX, child/class management)
**Focus**: `frontend/src/pages/`, user journeys, form flows
**Trigger phrase**: "You are the UX Flow Agent. Read FRONTEND_LEAD.md and CLAUDE.md, then [task]."

### State & API Agent (activate when: api.ts changes, auth flow, hooks)
**Focus**: `frontend/src/lib/api.ts`, `frontend/src/hooks/`, Supabase auth integration
**Trigger phrase**: "You are the State & API Agent. Read FRONTEND_LEAD.md and CLAUDE.md, then [task]."

---

## Common Debugging Commands
```bash
# Start dev server
cd frontend && npm run dev

# Build check (must pass before any commit)
cd frontend && npm run build

# Lint check (must be zero errors)
cd frontend && npm run lint

# Install new shadcn component (then MOVE from frontend/@/ to frontend/src/)
cd frontend && npx shadcn-ui@latest add [component-name]
mv frontend/@/components/ui/[component].tsx frontend/src/components/ui/[component].tsx
```

---

## Known Gotchas
- **shadcn path bug**: CLI always installs to `frontend/@/components/ui/` — ALWAYS move manually to `frontend/src/components/ui/` after install
- **TailwindCSS v4**: Some v3 utility classes behave differently — check docs if styles look wrong
- **Supabase auth timing**: Session may not be ready on first render — use `useEffect` with session dependency
- **Print styles**: Worksheets are printed — ensure worksheet components have `@media print` styles that hide nav/buttons

---

## Update Log (Frontend)
- **2026-02-17**: Agent file created. Sprint 1 tasks loaded from PjM_AGENT.md.
