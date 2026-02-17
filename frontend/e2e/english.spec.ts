import { test, expect } from '@playwright/test';
import { loginAsParent, navigateToTab, selectValue, waitForGeneration } from './helpers';

test.describe('Suite 3: Worksheet Generation — English', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsParent(page);
    await navigateToTab(page, 'Practice');
    await page.locator('#grade').waitFor({ timeout: 10_000 });
  });

  test('generate English Class 3 Nouns worksheet', async ({ page }) => {
    await selectValue(page, 'grade', /class 3/i);
    await page.waitForTimeout(3000);

    await page.locator('#subject').click();
    await page.waitForTimeout(500);
    await page.getByRole('option', { name: /english/i }).first().click();
    await page.waitForTimeout(3000);

    const nounsTopic = page.getByText('Nouns', { exact: false }).first();
    if (await nounsTopic.isVisible({ timeout: 5000 })) {
      await nounsTopic.click();
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

  test('English subject options available for Class 3', async ({ page }) => {
    await selectValue(page, 'grade', /class 3/i);
    await page.waitForTimeout(3000);

    await page.locator('#subject').click();
    await page.waitForTimeout(500);

    const englishOpt = page.getByRole('option', { name: /english/i });
    expect(await englishOpt.count()).toBeGreaterThan(0);
  });

  test('learning objective visible on English worksheet', async ({ page }) => {
    await selectValue(page, 'grade', /class 3/i);
    await page.waitForTimeout(3000);

    await page.locator('#subject').click();
    await page.waitForTimeout(500);
    await page.getByRole('option', { name: /english/i }).first().click();
    await page.waitForTimeout(3000);

    const topic = page.getByText('Adjectives', { exact: false }).first();
    if (await topic.isVisible({ timeout: 5000 })) {
      await topic.click();
    }
    await page.waitForTimeout(500);

    const generateBtn = page.getByRole('button', { name: /create today|generate/i });
    await generateBtn.click();

    await waitForGeneration(page);

    const bodyText = await page.textContent('body') || '';
    if (bodyText.length > 300) {
      const hasObjective = bodyText.toLowerCase().includes('learning') ||
        bodyText.toLowerCase().includes('goal') ||
        bodyText.toLowerCase().includes('objective');
      expect(hasObjective).toBeTruthy();
    }
  });
});
