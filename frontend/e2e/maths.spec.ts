import { test, expect } from '@playwright/test';
import { loginAsParent, navigateToTab, selectValue, waitForGeneration } from './helpers';

test.describe('Suite 2: Worksheet Generation — Maths', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsParent(page);
    await navigateToTab(page, 'Practice');
    await page.locator('#grade').waitFor({ timeout: 10_000 });
  });

  test('generate Maths Class 3 Addition worksheet', async ({ page }) => {
    await selectValue(page, 'grade', /class 3/i);
    // Wait for curriculum subjects to load
    await page.waitForTimeout(3000);

    // Open subject dropdown and pick Maths/Mathematics
    await page.locator('#subject').click();
    await page.waitForTimeout(500);
    // Try both "Maths" and "Mathematics"
    const mathsOpt = page.getByRole('option', { name: /math/i }).first();
    await mathsOpt.click();
    await page.waitForTimeout(3000);

    // Look for topic to select
    const additionTopic = page.getByText('Addition', { exact: false }).first();
    if (await additionTopic.isVisible({ timeout: 5000 })) {
      await additionTopic.click();
    }
    await page.waitForTimeout(500);

    // Click "Create today's practice"
    const generateBtn = page.getByRole('button', { name: /create today|generate/i });
    await expect(generateBtn).toBeVisible({ timeout: 10_000 });
    await generateBtn.click();

    await waitForGeneration(page);

    const pageContent = await page.textContent('body') || '';
    expect(pageContent).not.toContain('[Generation failed');
    expect(pageContent).not.toContain('[Slot fill]');
    expect(pageContent.length).toBeGreaterThan(200);
  });

  test('no blank screen on generator page', async ({ page }) => {
    const pageContent = await page.textContent('body') || '';
    expect(pageContent.length).toBeGreaterThan(50);
    await expect(page.locator('#grade')).toBeVisible();
  });

  test('grade and subject selectors work', async ({ page }) => {
    await expect(page.locator('#grade')).toBeVisible({ timeout: 5_000 });

    await page.locator('#grade').click();
    await page.waitForTimeout(300);
    expect(await page.getByRole('option').count()).toBeGreaterThan(0);

    await page.getByRole('option', { name: /class 3/i }).click();
    await page.waitForTimeout(3000);

    await expect(page.locator('#subject')).toBeVisible({ timeout: 5_000 });
    await page.locator('#subject').click();
    await page.waitForTimeout(500);

    // Should have at least Maths option
    const mathsOpt = page.getByRole('option', { name: /math/i });
    expect(await mathsOpt.count()).toBeGreaterThan(0);
  });
});
