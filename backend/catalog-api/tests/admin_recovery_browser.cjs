/* Synthetic local-only UI QA.
   node tests/admin_recovery_browser.cjs playwrightModule chromePath baseURL fixtureDir outputDir
   Generate fixtures with admin_recovery_preview.py and serve fixtureDir locally first. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require(process.argv[2]);
const [chrome, base, fixtures, output] = process.argv.slice(3);
const historical = '11111111-1111-4111-8111-111111111111';
const current = '22222222-2222-4222-8222-222222222222';
(async () => {
  assert(['localhost', '127.0.0.1'].includes(new URL(base).hostname), 'local fixtures only');
  await fs.mkdir(output, {recursive: true});
  const browser = await chromium.launch({executablePath: chrome, headless: true});
  try {
    const page = await browser.newPage({timezoneId: 'UTC'});
    const errors = [], posts = [];
    let rejectPost = false;
    page.on('pageerror', error => errors.push(error.message));
    await page.route('https://terento.app/**', async route => {
      const asset = new URL(route.request().url()).pathname;
      if (asset === '/assets/logo-sky.svg' || /^\/assets\/fonts\/[a-z-]+\.woff2$/.test(asset)) {
        return route.fulfill({contentType: asset.endsWith('.svg') ? 'image/svg+xml' : 'font/woff2', body: await fs.readFile(path.resolve(__dirname, '../../../site' + asset))});
      }
      return route.fulfill({status: 204});
    });
    await page.route('**/admin/providers/bbbike/rechecks', async route => {
      if (route.request().method() === 'POST') {
        posts.push(route.request().postDataJSON());
        assert.equal(route.request().headers()['x-csrf-token'], 'fixture');
        return route.fulfill({status: rejectPost ? 503 : 200, json: rejectPost ? {error: 'fixture_unavailable'} : {jobId: 1}});
      }
      return route.fulfill({json: {jobs: posts.length ? [{id: 1, state: 'RUNNING', results: []}] : []}});
    });
    const serve = async (route, name) => route.fulfill({contentType: 'text/html', body: await fs.readFile(path.join(fixtures, name + '.html'))});
    await page.route('**/admin/providers/bbbike', route => serve(route, 'provider'));
    await page.route('**/admin/update-diagnostics**', route => {
      const url = new URL(route.request().url());
      return serve(route, url.searchParams.get('eventId') === historical ? 'update-missing' : url.searchParams.has('eventId') || url.searchParams.has('diagnosticId') ? 'update-detail' : 'updates');
    });
    const load = async name => {
      await page.goto(`${base}/${name}.html?timeZone=UTC`);
      await page.evaluate(() => document.fonts.ready);
    };
    const fits = async context => assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `${context}: page overflow`);
    for (const width of [390, 720, 1024, 1440]) {
      await page.setViewportSize({width, height: 1000});
      for (const name of ['provider', 'chart', 'updates', 'update-detail', 'update-missing']) {
        await load(name);
        for (const rtl of [false, true]) {
          await page.evaluate(rtl => document.documentElement.dir = rtl ? 'rtl' : 'ltr', rtl);
          await fits(`${name}/${width}/${rtl ? 'RTL' : 'LTR'}`);
        }
        const mainBox = await page.locator('main h1').boundingBox();
        assert(mainBox.x >= 12, `${name}/${width}: content is inset`);
        if (width === 390) assert(await page.getByRole('button', {name: 'Menu', exact: true}).isVisible(), `${name}: mobile menu`);
        // Never let RTL from a stress check leak into the baseline screenshot.
        await page.evaluate(() => document.documentElement.dir = 'ltr');
        if (name === 'chart') {
          assert(await page.locator('.overview-chart-update-failed').count() >= 5, `chart series missing at ${page.url()}: ${await page.locator('main').innerText()}`);
          assert(await page.getByText('Update failed', {exact: true}).count());
          const fills = await page.locator('rect.overview-chart-update-failed').evaluateAll(nodes => nodes.map(n => n.style.fill));
          assert(fills.every(fill => fill.startsWith('url(')), 'failed updates use SVG patterns');
          assert(await page.locator('rect.overview-chart-update').count(), 'success updates have their own series');
        }
        await page.screenshot({path: path.join(output, `${name}-${width}.png`), fullPage: true});
      }
    }
    await page.setViewportSize({width: 720, height: 900});
    for (const name of ['provider', 'chart', 'updates', 'update-detail', 'update-missing']) {
      await load(name);
      for (const rtl of [false, true]) {
        await page.evaluate(rtl => {document.body.style.zoom = '2'; document.documentElement.dir = rtl ? 'rtl' : 'ltr';}, rtl);
        await fits(`${name}/200%/${rtl ? 'RTL' : 'LTR'}`);
      }
    }
    await load('provider');
    assert.equal(await page.locator('.provider-problem').count(), 4);
    await page.locator('[data-package-id]').first().click();
    assert.deepEqual(posts.at(-1), {packageId: 'idaho-bbbike'});
    await page.waitForFunction(() => document.querySelector('#provider-recheck-progress').textContent.includes('RUNNING'));
    await page.locator('button[data-provider-action="rechecks"]:not([data-package-id])').click();
    assert.deepEqual(posts.at(-1), {});
    await page.getByRole('button', {name: 'Copy details'}).first().click();
    await page.getByRole('button', {name: /Copied|Copy unavailable/}).first().waitFor();
    rejectPost = true;
    await page.locator('[data-package-id]').first().click();
    await page.waitForFunction(() => document.querySelector('#provider-action-status').textContent.includes('fixture_unavailable'));
    assert.equal(await page.locator('[data-package-id]').first().isDisabled(), false, 'failed request remains retryable');
    rejectPost = false;
    for (const [id, text] of [[historical, 'Failure details were not received'], [current, 'The update could not finish replacing the previous map.']]) {
      await load('chart');
      await page.locator(`a[href='/admin/update-diagnostics?eventId=${id}']`).click();
      assert((await page.locator('main').innerText()).includes(text));
    }
    await load('update-source');
    await page.getByRole('link', {name: 'Review provider packages'}).click();
    assert.equal(await page.locator('.provider-problem').count(), 4);
    await load('updates');
    await page.getByRole('link', {name: 'View report', exact: true}).click();
    assert((await page.locator('main').innerText()).includes('Not confirmed — inspect device'));
    // Keyboard action and expanded labels stay in document flow at narrow width.
    await load('provider');
    await page.setViewportSize({width: 390, height: 900});
    await page.locator('[data-package-id]').first().focus();
    await page.keyboard.press('Enter');
    assert.equal(posts.at(-1).packageId, 'idaho-bbbike');
    await page.getByRole('button', {name: 'Recheck affected packages'}).evaluate(el => el.textContent = 'Recheck all affected packages and inspect the resulting validation information');
    await fits('provider/expanded-label');
    assert.deepEqual(errors, []);
    console.log('PASS: 20 page/width combinations in LTR+RTL; five pages at 200% in LTR+RTL; scoped/all recheck POSTs, CSRF, retryable error, copy feedback, keyboard action; split SVG patterns; historical/current Activity and provider/detail navigation.');
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
