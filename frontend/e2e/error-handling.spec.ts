import { test, expect } from '@playwright/test';
import { login, navigateToTab, ensureParentRole } from './helpers';

test.describe('Suite 7: Error Handling (no blank screens)', () => {
  test('generator page renders without errors', async ({ page }) => {
    await login(page);
    await navigateToTab(page, 'Practice');

    // Page should have form elements, not a blank screen
    await expect(page.locator('button[role="combobox"]').first()).toBeVisible({ timeout: 10_000 });

    const bodyText = await page.textContent('body') || '';
    expect(bodyText.length).toBeGreaterThan(100);
    // Should see labels like Grade, Subject, etc.
    const hasFormLabels = bodyText.includes('Grade') || bodyText.includes('Subject') || bodyText.includes('Practice');
    expect(hasFormLabels).toBeTruthy();
  });

  test('saved worksheets page loads without blank screen', async ({ page }) => {
    await login(page);
    await navigateToTab(page, 'Saved');

    await page.waitForTimeout(3000);

    const bodyText = await page.textContent('body') || '';
    expect(bodyText.length).toBeGreaterThan(50);
    // Should not be blank — either shows saved worksheets or empty state
  });

  test('history page loads without blank screen', async ({ page }) => {
    await login(page);
    await navigateToTab(page, 'History');

    await page.waitForTimeout(3000);

    const bodyText = await page.textContent('body') || '';
    expect(bodyText.length).toBeGreaterThan(50);
  });

  test('profile/children page loads without blank screen', async ({ page }) => {
    await login(page);

    // For parent role, navigate to Profile tab
    const profileTab = page.getByRole('tab', { name: /profile|children/i });
    if (await profileTab.count() > 0) {
      await profileTab.first().click();
      await page.waitForTimeout(3000);
    }

    const bodyText = await page.textContent('body') || '';
    expect(bodyText.length).toBeGreaterThan(50);
    // Should see profile content or empty state, never a blank screen
  });

  test('subscription info does not crash the page', async ({ page }) => {
    await login(page);

    // The subscription badge should be visible in the nav bar
    await page.waitForTimeout(2000);

    const bodyText = await page.textContent('body') || '';
    // Should see either "Credits" badge or "Elite Pro" badge
    const hasSubscription = bodyText.includes('Credits') ||
      bodyText.includes('Elite Pro') ||
      bodyText.includes('Free');

    // The page should be functional regardless of subscription state
    expect(bodyText.length).toBeGreaterThan(100);
  });
});
