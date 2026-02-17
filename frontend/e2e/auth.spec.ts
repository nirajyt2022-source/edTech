import { test, expect } from '@playwright/test';
import { TEST_EMAIL, login } from './helpers';

test.describe('Suite 1: Authentication Flow', () => {
  test('unauthenticated user sees landing page', async ({ page }) => {
    await page.goto('/');
    // Should see landing page with "Get Started" or "Sign In" buttons
    await expect(page.getByText('PracticeCraft', { exact: false })).toBeVisible({ timeout: 15_000 });
    // Should NOT see the Practice tab (that's only for authenticated users)
    await expect(page.getByRole('tab', { name: 'Practice' })).not.toBeVisible();
  });

  test('login with valid credentials lands on dashboard', async ({ page }) => {
    await login(page);
    // Should see the Practice tab and navigation
    await expect(page.getByRole('tab', { name: 'Practice' })).toBeVisible();
    // Should see the user menu (avatar initial)
    await expect(page.locator('text=PracticeCraft')).toBeVisible();
  });

  test('login with wrong password shows error message', async ({ page }) => {
    await page.goto('/');

    // Click Sign In on landing page
    const signInBtn = page.getByRole('button', { name: /sign in/i });
    await signInBtn.first().click();

    // Fill login form with wrong password
    await page.locator('#email').fill(TEST_EMAIL);
    await page.locator('#password').fill('WrongPassword123');

    // Submit
    await page.getByRole('button', { name: /^sign in$/i }).click();

    // Should show error alert, NOT a blank screen
    await expect(page.getByRole('alert')).toBeVisible({ timeout: 10_000 });
    // Verify there IS error text
    const alertText = await page.getByRole('alert').textContent();
    expect(alertText).toBeTruthy();
    expect(alertText!.length).toBeGreaterThan(5);
  });

  test('logout redirects to landing page', async ({ page }) => {
    await login(page);

    // Open user dropdown menu — the trigger is the avatar button with chevron in the nav
    const dropdownTrigger = page.locator('nav button:has(svg)').last();
    await dropdownTrigger.click();
    await page.waitForTimeout(500);

    // Click Sign out
    await page.getByRole('menuitem', { name: /sign out/i }).click();

    // Should redirect to landing page (no Practice tab)
    await expect(page.getByRole('tab', { name: 'Practice' })).not.toBeVisible({ timeout: 10_000 });
    // Should see landing page content
    await expect(page.getByText('PracticeCraft', { exact: false })).toBeVisible();
  });
});
