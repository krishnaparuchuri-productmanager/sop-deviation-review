/**
 * take_screenshots.js — Capture all 5 app screens using Playwright.
 *
 * Saves PNG files to screenshots/ in the project root.
 * Run: node take_screenshots.js
 */

const { chromium } = require('playwright');
const path = require('path');
const fs   = require('fs');

const BASE   = 'http://localhost:5173';
const OUTDIR = path.join(__dirname, 'screenshots');

const SCREENS = [
  {
    name:  '1-chat',
    url:   `${BASE}/chat`,
    title: 'Chat — Deviation Review',
    wait:  1500,
    // Pre-fill the textarea with a sample scenario
    setup: async (page) => {
      await page.locator('textarea').fill(
        'During routine QC testing, an analyst discovered that the pH meter used for buffer preparation had an expired calibration sticker. The calibration was due on 2026-04-15.'
      );
    },
  },
  {
    name:  '2-results',
    url:   null,       // navigated via form submit
    title: 'Results — Deviation Assessment',
    wait:  8000,
    // Special: navigate from chat by submitting the form
    navigate: async (page) => {
      await page.goto(`${BASE}/chat`);
      await page.locator('textarea').fill(
        'During routine QC testing, an analyst discovered that the pH meter used for buffer preparation had an expired calibration sticker. The calibration was due on 2026-04-15 and the current date is 2026-05-07.'
      );
      // Click Review Deviation button
      await page.locator('button[type="submit"]').click();
      // Wait for results to load (API call ~5-7s)
      await page.waitForURL(`${BASE}/results`, { timeout: 30000 });
      await page.waitForTimeout(2000);
    },
  },
  {
    name:  '3-dashboard',
    url:   `${BASE}/dashboard`,
    title: 'Dashboard — Analytics',
    wait:  3000,
  },
  {
    name:  '4-evals',
    url:   `${BASE}/evals`,
    title: 'Evals — Evaluation Suite',
    wait:  3000,
  },
  {
    name:  '5-feedback',
    url:   `${BASE}/feedback`,
    title: 'Feedback Queue',
    wait:  3000,
  },
];

async function run() {
  fs.mkdirSync(OUTDIR, { recursive: true });
  console.log(`Screenshots will be saved to: ${OUTDIR}\n`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });

  for (const screen of SCREENS) {
    const page = await context.newPage();
    console.log(`Capturing: ${screen.title}`);

    try {
      if (screen.navigate) {
        await screen.navigate(page);
      } else {
        await page.goto(screen.url, { waitUntil: 'networkidle', timeout: 20000 });
      }

      if (screen.setup) {
        await screen.setup(page);
      }

      await page.waitForTimeout(screen.wait);

      const outFile = path.join(OUTDIR, `${screen.name}.png`);
      await page.screenshot({ path: outFile, fullPage: true });
      const size = fs.statSync(outFile).size;
      console.log(`  -> Saved ${screen.name}.png  (${(size / 1024).toFixed(0)} KB)`);
    } catch (err) {
      console.error(`  !! Failed: ${err.message}`);
      // Save an error screenshot anyway
      try {
        const errFile = path.join(OUTDIR, `${screen.name}-error.png`);
        await page.screenshot({ path: errFile, fullPage: true });
        console.log(`  -> Error screenshot saved: ${screen.name}-error.png`);
      } catch { /* ignore */ }
    }

    await page.close();
  }

  await browser.close();
  console.log('\nAll screenshots captured.');
}

run().catch(err => {
  console.error('Fatal:', err);
  process.exit(1);
});
