import { test, expect } from '@playwright/test';
import { loginAsParent, navigateToTab, selectValue, waitForGeneration } from './helpers';

test.describe('Suite 4: Worksheet Generation — Science', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsParent(page);
    await navigateToTab(page, 'Practice');
    await page.locator('#grade').waitFor({ timeout: 10_000 });
  });

  test('generate Science Class 3 Plants worksheet', async ({ page }) => {
    await selectValue(page, 'grade', /class 3/i);
    await page.waitForTimeout(3000);

    await page.locator('#subject').click();
    await page.waitForTimeout(500);
    // Science might show as "Science" or "EVS"
    const scienceOpt = page.getByRole('option', { name: /science|evs/i }).first();
    await scienceOpt.click();
    await page.waitForTimeout(3000);

    const plantsTopic = page.getByText('Plants', { exact: false }).first();
    if (await plantsTopic.isVisible({ timeout: 5000 })) {
      await plantsTopic.click();
    }
    await page.waitForTimeout(500);

    const generateBtn = page.getByRole('button', { name: /create today|generate/i });
    await generateBtn.click();

    await waitForGeneration(page);

    const pageText = await page.textContent('body') || '';
    expect(pageText).not.toContain('[Generation failed');
    expect(pageText).not.toContain('[Slot fill]');
    expect(pageText.length).toBeGreaterThan(200);
  });

  test('Science subject available for Class 3', async ({ page }) => {
    await selectValue(page, 'grade', /class 3/i);
    await page.waitForTimeout(3000);

    await page.locator('#subject').click();
    await page.waitForTimeout(500);

    const allText = await page.locator('[role="option"]').allTextContents();
    const hasScience = allText.some(t => /science|evs/i.test(t));
    expect(hasScience).toBeTruthy();
  });
});
