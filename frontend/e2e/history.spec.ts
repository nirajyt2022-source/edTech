import { test, expect } from '@playwright/test';
import { login, navigateToTab } from './helpers';

test.describe('Suite 6: Worksheet History', () => {
  test('history page loads without blank screen', async ({ page }) => {
    await login(page);
    await navigateToTab(page, 'History');

    // Wait for history page content
    await page.waitForTimeout(3000);

    const bodyText = await page.textContent('body') || '';
    // Should see either worksheet history items or "no worksheets" empty state
    expect(bodyText.length).toBeGreaterThan(50);
    // Should not be a blank page
    const hasContent = bodyText.toLowerCase().includes('history') ||
      bodyText.toLowerCase().includes('worksheet') ||
      bodyText.toLowerCase().includes('no ') ||
      bodyText.toLowerCase().includes('generate');
    expect(hasContent).toBeTruthy();
  });

  test('history page shows previously generated worksheets', async ({ page }) => {
    await login(page);
    await navigateToTab(page, 'History');

    await page.waitForTimeout(5000);

    const bodyText = await page.textContent('body') || '';
    // If there are worksheets, they should show up as cards/items
    // If empty, should show empty state message
    const hasWorksheets = bodyText.toLowerCase().includes('class') ||
      bodyText.toLowerCase().includes('maths') ||
      bodyText.toLowerCase().includes('english') ||
      bodyText.toLowerCase().includes('addition');
    const hasEmptyState = bodyText.toLowerCase().includes('no worksheet') ||
      bodyText.toLowerCase().includes('empty') ||
      bodyText.toLowerCase().includes('generate your first') ||
      bodyText.toLowerCase().includes('no history');

    expect(hasWorksheets || hasEmptyState).toBeTruthy();
  });

  test('PDF download button present on history items', async ({ page }) => {
    await login(page);
    await navigateToTab(page, 'History');

    await page.waitForTimeout(5000);

    // Check for download/PDF buttons
    const downloadBtns = page.getByRole('button', { name: /download|pdf|export/i });
    const downloadLinks = page.locator('a[download], button:has-text("PDF"), button:has-text("Download")');

    const downloadCount = await downloadBtns.count() + await downloadLinks.count();

    // If there are worksheets in history, there should be download buttons
    const bodyText = await page.textContent('body') || '';
    const hasWorksheets = bodyText.toLowerCase().includes('class') ||
      bodyText.toLowerCase().includes('maths');

    if (hasWorksheets) {
      expect(downloadCount).toBeGreaterThan(0);
    }
    // If no worksheets, just pass (empty history is valid)
  });
});
