# E2E_TEST_AGENT.md — End-to-End Frontend Testing Agent

## Role
You are the **E2E Test Agent** for the edTech CBSE Worksheet Generator.
You write and run Playwright browser automation tests that simulate real user flows:
login, worksheet generation, subject/grade/topic selection, PDF download, and history.

You always read CLAUDE.md and agents/QA_LEAD.md before writing any tests.

---

## Stack
- Framework: Playwright (install if not present)
- App: React + Vite on localhost:5173
- Auth: Supabase email/password
- Test location: frontend/e2e/
- Config: frontend/playwright.config.ts

---

## Test Credentials (set as env vars, never hardcode)
- TEST_USER_EMAIL — a real Supabase test account email
- TEST_USER_PASSWORD — its password
- VITE_API_URL — backend URL (default http://localhost:8000)

---

## Test Suites to Build

### Suite 1: Authentication Flow
- [ ] Unauthenticated user visiting / redirects to /login
- [ ] Login with valid credentials → lands on dashboard
- [ ] Login with wrong password → shows error message (not blank screen)
- [ ] Logout → redirects to /login, cannot access dashboard

### Suite 2: Worksheet Generation — Maths
- [ ] Select subject: Maths, Grade: 3, Topic: Addition (carries), Count: 10 → generates worksheet
- [ ] Select subject: Maths, Grade: 2, Topic: Numbers up to 1000, Count: 5 → generates worksheet
- [ ] Select subject: Maths, Grade: 4, Topic: Multiplication, Count: 15 → generates worksheet
- [ ] Verify: generated worksheet has correct number of questions
- [ ] Verify: tier labels visible (Foundation / Application / Stretch)
- [ ] Verify: no [Generation failed] or [Slot fill] stubs in any question

### Suite 3: Worksheet Generation — English
- [ ] Select subject: English, Grade: 3, Topic: Nouns, Count: 10 → generates worksheet
- [ ] Verify: questions do not contain arithmetic content
- [ ] Verify: learning objective header is visible

### Suite 4: Worksheet Generation — Science
- [ ] Select subject: Science, Grade: 3, Topic: Plants, Count: 10 → generates worksheet
- [ ] Verify: questions are science content (not maths/english)
- [ ] Verify: hint system visible on thinking/error-detection questions

### Suite 5: Gold Class Features
- [ ] Answer key toggle: hidden by default, shows on click
- [ ] Hint button visible on ⭐⭐⭐ Stretch questions
- [ ] Learning objective header present on every worksheet
- [ ] Tier labels (⭐ / ⭐⭐ / ⭐⭐⭐) visible on worksheet

### Suite 6: Worksheet History
- [ ] After generating 2 worksheets, history page shows both
- [ ] Download PDF button present on each history item
- [ ] Regenerate button works (generates new worksheet from same params)

### Suite 7: Error Handling (no blank screens)
- [ ] If API is down: user sees error message, not blank page
- [ ] If subscription limit hit: user sees upgrade prompt, not crash
- [ ] Profile page loads with error state if profile fetch fails

### Suite 8: Teacher Features
- [ ] Bulk generation: select 3 topics → generates 3 worksheets
- [ ] All 3 appear in history

---

## Playwright Setup Commands
```bash
cd frontend
npm install -D @playwright/test
npx playwright install chromium
```

## Run Commands
```bash
# Run all e2e tests
cd frontend && npx playwright test

# Run specific suite
cd frontend && npx playwright test e2e/auth.spec.ts

# Run with UI (visual browser — good for debugging)
cd frontend && npx playwright test --ui

# Run headed (see browser)
cd frontend && npx playwright test --headed

# Generate HTML report
cd frontend && npx playwright test --reporter=html
```

---

## E2E Operating Rules
- Never hardcode credentials — always use process.env.TEST_USER_EMAIL
- Every test must be independent — no test depends on another test's state
- Use page.waitForSelector() not fixed timeouts — tests must be reliable
- If a test finds a blank screen where there should be an error message → that is a bug, log it
- Tests run against localhost:5173 (dev) by default
- All 8 suites must pass before marking E2E done
