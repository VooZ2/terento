/* Browser check of every Admin page, built from fixtures (tests/admin_presentation_preview.py).
   Usage: node admin_pages_browser.cjs <playwright module> <fixture dir> <output dir>
   Each page must load the Admin stylesheet (HTTP 200, rules applied), run without
   script errors and fit the phone width; a full-page screenshot is written for
   desktop (1440 px) and mobile (390 px) so a CSS change can be compared before/after.
   Never touches production: the pages are served from the local fixture folder. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { chromium } = require(process.argv[2]);

const root = path.resolve(process.argv[3]);
const output = path.resolve(process.argv[4]);
const VIEWPORTS = [{ name: 'desktop', width: 1440, height: 900 }, { name: 'mobile', width: 390, height: 844 }];
const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript',
  '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.ico': 'image/x-icon', '.png': 'image/png' };

// Pages link to real Admin routes; scripts may move there (for example a
// "today" period adds the browser time zone), so routes map to fixtures.
const ROUTES = { '/admin': 'overview.html', '/admin/': 'overview.html', '/admin/devices': 'devices.html',
  '/admin/installations': 'installations.html', '/admin/map-statistics': 'statistics.html',
  '/admin/providers': 'providers.html', '/admin/system-health': 'health.html', '/admin/diagnostics': 'diagnostics.html',
  '/admin/support-reports': 'support-reports.html', '/admin/review/identity': 'identity-review.html',
  '/admin/web-installer': 'web-installer.html', '/admin/first-run': 'first-run.html', '/admin/web-visits': 'web-visits.html' };

function fixturePath(urlPath) {
  let relative = decodeURIComponent(urlPath);
  if (ROUTES[relative]) relative = '/' + ROUTES[relative];
  else if (relative.startsWith('/admin/fonts/')) relative = relative.slice('/admin'.length);
  else if (!relative.startsWith('/admin/map-assets/')) relative = relative.replace(/^\/admin(?=\/)/, '');
  const file = path.resolve(root, '.' + relative);
  return file.startsWith(root + path.sep) ? file : null;
}

const server = http.createServer((request, response) => {
  const file = fixturePath(new URL(request.url, 'http://fixture').pathname);
  if (!file || !fs.existsSync(file) || !fs.statSync(file).isFile()) { response.writeHead(404); response.end(); return; }
  response.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(response);
});

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const pages = fs.readdirSync(root).filter(name => name.endsWith('.html')).sort();
  assert(pages.length >= 40, `expected every Admin fixture page, found ${pages.length}`);
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch(process.env.TERENTO_CHROME_BIN ? { executablePath: process.env.TERENTO_CHROME_BIN } : {});
  const failures = [];
  try {
    for (const viewport of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height }, deviceScaleFactor: 1,
        timezoneId: 'UTC', locale: 'en-US', reducedMotion: 'reduce', colorScheme: 'light',
      });
      const page = await context.newPage();
      await page.clock.setFixedTime(new Date('2026-09-17T12:00:00Z'));
      for (const name of pages) {
        const label = `${name} ${viewport.name}`;
        const errors = [];
        const onError = error => errors.push(error.message);
        page.on('pageerror', onError);
        const stylesheets = [];
        const onResponse = response => { if (response.request().resourceType() === 'stylesheet') stylesheets.push([response.url(), response.status()]); };
        page.on('response', onResponse);
        try {
          await page.goto(`${base}/admin/${name}`, { waitUntil: 'networkidle' });
          await page.evaluate(() => document.fonts.ready);
          const admin = stylesheets.filter(([url]) => /\/admin\/map-assets\/admin\.[0-9a-f]{16}\.css$/.test(url));
          const inline = await page.evaluate(() => [...document.querySelectorAll('style')].some(s => s.textContent.includes('--admin-card-gap')));
          if (!inline) {
            assert.equal(admin.length, 1, `${label}: one versioned Admin stylesheet`);
            assert.equal(admin[0][1], 200, `${label}: Admin stylesheet answers 200`);
          }
          // The stylesheet's own rules apply (a missing file leaves browser defaults).
          const applied = await page.evaluate(() => getComputedStyle(document.body).getPropertyValue('--admin-card-gap').trim());
          assert.notEqual(applied, '', `${label}: Admin styles applied`);
          assert.deepEqual(errors, [], `${label}: script errors`);
          const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
          assert(overflow <= 0, `${label}: page is ${overflow}px wider than the viewport`);
          await page.screenshot({ path: path.join(output, `${name.replace(/\.html$/, '')}-${viewport.name}.png`), fullPage: true, animations: 'disabled', caret: 'hide' });
        } catch (error) {
          failures.push(error.message.split('\n')[0]);
        } finally {
          page.off('pageerror', onError);
          page.off('response', onResponse);
        }
      }
      await context.close();
    }
  } finally {
    await browser.close();
    server.close();
  }
  if (failures.length) {
    console.error(failures.join('\n'));
    process.exit(1);
  }
  console.log(`PASS: ${pages.length} Admin pages at ${VIEWPORTS.map(v => v.width).join(' and ')} px`);
})().catch(error => { console.error(error); process.exit(1); });
