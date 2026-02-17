import { test, expect } from '@playwright/test';
import { login, navigateToTab } from './helpers';

async function ensureTeacherRole(page: import('@playwright/test').Page) {
  // Check if already in teacher mode (Dashboard tab visible)
  const dashTab = page.getByRole('tab', { name: /dashboard/i });
  if (await dashTab.count() > 0) {
    return; // Already teacher
  }

  // Open user dropdown and switch
  const dropdownTrigger = page.locator('nav button:has(svg)').last();
  await dropdownTrigger.click();

  const switchBtn = page.getByText(/switch to teacher/i);
  try {
    await switchBtn.waitFor({ timeout: 3_000 });
    await switchBtn.click();
    await page.waitForTimeout(3000);
  } catch {
    // Dropdown may have closed or already teacher — press Escape and continue
    await page.keyboard.press('Escape');
  }
}

test.describe('Suite 8: Teacher Features — Bulk Generation', () => {
  test('switch role via dropdown menu', async ({ page }) => {
    await login(page);

    // Open dropdown
    const dropdownTrigger = page.locator('nav button:has(svg)').last();
    await dropdownTrigger.click();

    // Click whichever switch option is available (teacher or parent)
    const switchToTeacher = page.getByText(/switch to teacher/i);
    const switchToParent = page.getByText(/switch to parent/i);

    if (await switchToTeacher.count() > 0) {
      await switchToTeacher.click();
      await page.waitForTimeout(3000);
      const bodyText = await page.textContent('body') || '';
      expect(bodyText.includes('Dashboard') || bodyText.includes('Classes')).toBeTruthy();
    } else if (await switchToParent.count() > 0) {
      await switchToParent.click();
      await page.waitForTimeout(3000);
      const bodyText = await page.textContent('body') || '';
      expect(bodyText.includes('Progress') || bodyText.includes('Profile') || bodyText.includes('Syllabus')).toBeTruthy();
    }
  });

  test('teacher can access generator page', async ({ page }) => {
    await login(page);
    await ensureTeacherRole(page);

    // Teacher tabs include "Practice"
    const practiceTab = page.getByRole('tab', { name: 'Practice' });
    if (await practiceTab.count() > 0) {
      await practiceTab.first().click();
    }
    await page.waitForTimeout(2000);

    const bodyText = await page.textContent('body') || '';
    expect(bodyText.length).toBeGreaterThan(100);
    const hasForm = bodyText.includes('Grade') || bodyText.includes('Subject') || bodyText.includes('Generate');
    expect(hasForm).toBeTruthy();
  });

  test('teacher dashboard loads without blank screen', async ({ page }) => {
    await login(page);
    await ensureTeacherRole(page);

    const dashTab = page.getByRole('tab', { name: /dashboard/i });
    if (await dashTab.count() > 0) {
      await dashTab.first().click();
      await page.waitForTimeout(3000);
    }

    const bodyText = await page.textContent('body') || '';
    expect(bodyText.length).toBeGreaterThan(50);
  });
});
