/* Synthetic Activity QA. node file playwrightModule chromePath baseURL fixtureDir outputDir */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require(process.argv[2]);
const [chrome, base, fixtures, output] = process.argv.slice(3);
(async () => {
  assert(['localhost', '127.0.0.1'].includes(new URL(base).hostname));
  await fs.mkdir(output, {recursive: true});
  const browser = await chromium.launch({executablePath: chrome, headless: true});
  try {
    const page = await browser.newPage({timezoneId: 'UTC'});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('https://terento.app/**', async route => {
      const asset = new URL(route.request().url()).pathname;
      if (asset === '/assets/logo-sky.svg' || /^\/assets\/fonts\/[a-z-]+\.woff2$/.test(asset)) {
        return route.fulfill({contentType: asset.endsWith('.svg') ? 'image/svg+xml' : 'font/woff2',
          body: await fs.readFile(path.resolve(__dirname, '../../../site' + asset))});
      }
      return route.fulfill({status: 204});
    });
    await page.route(base + '/**', route => route.fulfill({contentType: 'text/html', path: path.join(fixtures, 'activity.html')}));
    for (const width of [320, 390, 720, 1024, 1440]) {
      await page.setViewportSize({width, height: 1000});
      await page.goto(base + '/activity.html?timeZone=UTC');
      await page.evaluate(() => document.fonts.ready);
      const rows = page.locator('.overview-activity-list .map-activity-row');
      assert.equal(await rows.count(), 7);
      for (const rtl of [false, true]) {
        await page.evaluate(rtl => document.documentElement.dir = rtl ? 'rtl' : 'ltr', rtl);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
        for (let index = 0; index < 5; index++) {
          const row = rows.nth(index), device = row.locator('.overview-activity-device');
          assert.equal(await device.count(), 1);
          assert.equal(new URL(await device.getAttribute('href'), base).pathname, '/admin/devices/fenix-8-47-amoled');
          assert.equal(await device.evaluate(el => el.parentElement.className), 'activity-context');
          assert.equal(await device.evaluate(el => getComputedStyle(el).display), 'inline');
          if (width === 1440) {
            const aligned = await device.evaluate(el => {
              const range = document.createRange(); range.selectNodeContents(el.parentElement.firstChild);
              return Math.abs(range.getClientRects()[0].y - el.getClientRects()[0].y) < 1;
            });
            assert(aligned, `desktop model shares context line ${index}/${rtl}`);
          }
        }
        assert.equal(await rows.nth(5).locator('.overview-activity-device').count(), 0);
        assert(!(await rows.nth(5).innerText()).includes('Unverified device name'));
        const custom = await rows.nth(2).locator('.activity-context').innerText();
        assert(custom.startsWith('Custom .img · fēnix 8'));
        assert(!custom.includes('Should never show custom provider') && !custom.includes('BBBike'));
        assert.equal(await page.getByRole('link', {name: 'View failure', exact: true}).count(), 2);
      }
      await page.evaluate(() => {document.documentElement.dir = 'ltr'; document.querySelector('.overview-activity-list').scrollTop = 0;});
      await page.screenshot({path: path.join(output, `activity-${width}-top.png`), fullPage: true});
      await page.locator('.overview-activity-panel').screenshot({path: path.join(output, `activity-${width}-panel.png`)});
      const timeline = page.locator('details.download-history');
      await timeline.locator('summary').click();
      assert.equal(await timeline.locator('.download-timeline li').count(), 3);
      assert.equal(await timeline.locator('.download-elapsed').innerText(), '3m');
      await timeline.scrollIntoViewIfNeeded();
      await page.screenshot({path: path.join(output, `activity-${width}-timeline.png`), fullPage: true});
      await page.locator('.overview-activity-panel').screenshot({path: path.join(output, `activity-${width}-timeline-panel.png`)});
    }
    await page.setViewportSize({width: 720, height: 1000});
    await page.goto(base + '/activity.html?timeZone=UTC');
    for (const rtl of [false, true]) {
      await page.evaluate(rtl => {document.body.style.zoom = '2'; document.documentElement.dir = rtl ? 'rtl' : 'ltr';}, rtl);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, '200% overflow');
      await page.locator('.overview-activity-device').first().focus();
      assert(await page.locator('.overview-activity-device').first().evaluate(el => el === document.activeElement));
    }
    assert.deepEqual(errors, []);
    console.log('PASS Activity: five widths LTR/RTL, inline second-line desktop identity, natural wrapping, exact canonical links/no unknown model/no custom provider, failure buttons, download timeline and duration, 200% CSS zoom and keyboard focus.');
  } finally {await browser.close();}
})().catch(error => {console.error(error); process.exitCode = 1;});
