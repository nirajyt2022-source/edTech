import { Page } from '@playwright/test';

// Test credentials
export const TEST_EMAIL = process.env.TEST_USER_EMAIL || 'nirajyt2022@gmail.com';
export const TEST_PASSWORD = process.env.TEST_USER_PASSWORD || 'Hell@25682356';

const BACKEND_URL = 'https://edtech-production-c7ec.up.railway.app';
const SUPABASE_URL = 'https://idcewaxatkwzxdmqtnsf.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlkY2V3YXhhdGt3enhkbXF0bnNmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzAyMTM0OTQsImV4cCI6MjA4NTc4OTQ5NH0.DNBjnCYvRDIAjl4elNOo8hChf1nsk-lWxL4vYYCWNAE';

/**
 * Get auth token via Supabase REST API.
 */
async function getAuthToken(): Promise<string> {
  const resp = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
    method: 'POST',
    headers: {
      'apikey': SUPABASE_ANON_KEY,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ email: TEST_EMAIL, password: TEST_PASSWORD }),
  });
  const data = await resp.json();
  return data.access_token;
}

/**
 * Switch role via backend API call.
 */
async function switchRoleViaAPI(role: 'parent' | 'teacher') {
  const token = await getAuthToken();
  await fetch(`${BACKEND_URL}/api/users/switch-role`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({ active_role: role }),
  });
}

/**
 * Log in to PracticeCraft and wait for the app to load.
 */
export async function login(page: Page) {
  await page.goto('/');

  const signInBtn = page.getByRole('button', { name: /sign in/i });
  await signInBtn.first().click();

  await page.locator('#email').fill(TEST_EMAIL);
  await page.locator('#password').fill(TEST_PASSWORD);
  await page.getByRole('button', { name: /^sign in$/i }).click();

  await page.waitForSelector('text=PracticeCraft', { timeout: 30_000 });
  await page.waitForSelector('button[role="tab"]', { timeout: 15_000 });
}

/**
 * Log in as parent role. Switches role via API BEFORE loading the page.
 */
export async function loginAsParent(page: Page) {
  // Switch role via API before the page loads
  await switchRoleViaAPI('parent');
  await login(page);
}

/**
 * Log in as teacher role. Switches role via API BEFORE loading the page.
 */
export async function loginAsTeacher(page: Page) {
  await switchRoleViaAPI('teacher');
  await login(page);
}

/**
 * Navigate to a specific tab by label text.
 */
export async function navigateToTab(page: Page, tabLabel: string) {
  const tab = page.getByRole('tab', { name: tabLabel });
  await tab.first().waitFor({ timeout: 10_000 });
  await tab.first().click();
  await page.waitForTimeout(1000);
}

/**
 * Select a value from a shadcn Select component by trigger ID.
 */
export async function selectValue(page: Page, triggerId: string, optionText: string | RegExp) {
  const trigger = page.locator(`#${triggerId}`);
  await trigger.waitFor({ timeout: 10_000 });
  await trigger.click();
  await page.waitForTimeout(300);
  const option = page.getByRole('option', { name: optionText });
  await option.click();
  await page.waitForTimeout(500);
}

/**
 * Wait for worksheet generation to complete.
 */
export async function waitForGeneration(page: Page) {
  try {
    await page.waitForSelector('[class*="animate-spin"]', { timeout: 10_000 });
    await page.waitForSelector('[class*="animate-spin"]', { state: 'detached', timeout: 90_000 });
  } catch {
    // Spinner might have already appeared and gone
  }
  await page.waitForTimeout(3000);
}
