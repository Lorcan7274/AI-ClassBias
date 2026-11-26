// Renders the CV pair pages to 16:9 PNGs:  node slides/render.js
const path = require('path');
const { chromium } = require('playwright');

const dir = __dirname;
const jobs = [['cv_pair_hinted.html', 'slide_cv_comparison.png'],
              ['cv_pair_stated.html', 'slide_cv_comparison_stated.png']];

(async () => {
  const browser = await chromium.launch();
  for (const [page, png] of jobs) {
    const p = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2 });
    await p.goto('file://' + path.join(dir, page));
    await p.waitForFunction(() => document.body.dataset.fitted);
    const size = await p.evaluate(() => document.body.dataset.fitted);
    await p.screenshot({ path: path.join(dir, png) });
    console.log(`${png}: text ${size}px`);
  }
  await browser.close();
})();
