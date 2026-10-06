/* Local fixture parity QA; never creates an external issue.
   node tests/admin_diagnostic_parity_browser.cjs playwrightModule chromePath baseURL fixtureDir outputDir */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require(process.argv[2]);
const [chrome, base, fixtures, output] = process.argv.slice(3);
const deviceID = 'fenix-8-51-amoled';
const diagnosticID = '22222222-2222-4222-8222-222222222222';
(async () => {
  assert(['127.0.0.1', 'localhost'].includes(new URL(base).hostname));
  await fs.mkdir(output, {recursive: true});
  const browser = await chromium.launch({executablePath: chrome, headless: true});
  try {
    const context = await browser.newContext({timezoneId: 'UTC'});
    await context.addInitScript(() => {
      window.__copiedReports = [];
      Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {
        writeText: async text => { window.__copiedReports.push(text); },
      }});
    });
    const state = {install: 'open', update: 'open'};
    const mutations = [], external = [], errors = [];
    await context.route('https://github.com/**', route => {
      external.push({url: route.request().url(), method: route.request().method()});
      return route.fulfill({contentType: 'text/html', body: '<p>Mock issue preparation only.</p>'});
    });
    await context.route('https://terento.app/**', async route => {
      const asset = new URL(route.request().url()).pathname;
      if (asset === '/assets/logo-sky.svg' || asset === '/assets/generic-garmin-watch.png' || /^\/assets\/fonts\/[a-z-]+\.woff2$/.test(asset)) {
        return route.fulfill({contentType: asset.endsWith('.svg') ? 'image/svg+xml' : asset.endsWith('.png') ? 'image/png' : 'font/woff2', body: await fs.readFile(path.resolve(__dirname, '../../../site' + asset))});
      }
      return route.fulfill({status: 204});
    });
    const serve = async (route, name) => route.fulfill({contentType: 'text/html', body: await fs.readFile(path.join(fixtures, name + '.html'))});
    await context.route(base + '/**', async route => {
      const req = route.request(), url = new URL(req.url());
      const kind = url.pathname.startsWith('/admin/update-diagnostics') ? 'update' : 'install';
      if (req.method() === 'POST') {
        assert(/^\/admin\/(update-diagnostics|diagnostics)\/(issue|resolve|reopen|workflow|identity)$/.test(url.pathname), 'only diagnostic review writes');
        const form = new URLSearchParams(req.postData());
        assert.equal(form.get('csrf_token'), 'fixture');
        if (kind === 'update') assert.equal(form.get('diagnostic_id'), diagnosticID);
        mutations.push({kind, action: url.pathname.split('/').at(-1), data: Object.fromEntries(form)});
        state[kind] = url.pathname.endsWith('/resolve') ? 'resolved' : url.pathname.endsWith('/reopen') ? 'open' : form.get('linked_github_issue') ? 'linked' : 'open';
        return route.fulfill({status: 200, json: {saved: true}});
      }
      if (url.pathname.startsWith('/parity/')) return serve(route, url.pathname.split('/').at(-1).replace('.html', ''));
      if (url.pathname === '/admin/diagnostics') return serve(route, 'install-' + state.install);
      if (url.pathname === '/admin/update-diagnostics') return serve(route, 'update-' + state.update);
      if (url.pathname === '/admin/devices/' + deviceID) return serve(route, 'device-updates');
      return route.fulfill({status: 204});
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    page.on('dialog', dialog => dialog.accept());
    const openInstall = async () => {
      const trigger = page.locator('button[data-dialog-id]').first();
      await trigger.click();
      const modal = page.locator('dialog[open]');
      assert(await modal.isVisible());
      const heading = await modal.getAttribute('aria-labelledby');
      assert(await modal.locator('#' + heading).isVisible(), 'dialog accessible name');
      return modal;
    };
    const load = async name => {
      await page.goto(`${base}/parity/${name}.html?timeZone=UTC`);
      await page.evaluate(() => document.fonts.ready);
      return name.startsWith('install') ? openInstall() : page.locator('main');
    };
    const assertFits = async label => {
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, label + ' document overflow');
      for (const modal of await page.locator('dialog[open]').all()) {
        assert.equal(await modal.evaluate(el => el.scrollWidth > el.clientWidth + 1), false, label + ' dialog horizontal overflow');
      }
    };
    for (const width of [320, 390, 720, 1024, 1440]) {
      await page.setViewportSize({width, height: 1000});
      for (const name of ['install-open', 'update-open', 'update-unknown', 'device-updates']) {
        const surface = await load(name);
        for (const rtl of [false, true]) {
          await page.evaluate(rtl => document.documentElement.dir = rtl ? 'rtl' : 'ltr', rtl);
          await assertFits(`${name}/${width}/${rtl}`);
        }
        await page.evaluate(() => document.documentElement.dir = 'ltr');
        if (name === 'install-open' || name === 'update-open') {
          assert(await surface.getByText('GitHub issue', {exact: true}).count());
          assert(await surface.getByText('Technical details', {exact: true}).count());
          assert(await surface.locator('[data-github-create]').isVisible(), 'issue preparation is a visible primary action');
          assert(await surface.getByText('What happened', {exact: true}).isVisible());
          assert(await surface.getByText('Next action', {exact: true}).isVisible());
          assert(await surface.getByText('Safety facts', {exact: true}).isVisible());
          assert.equal(await surface.getByRole('button', {name: 'Resolve diagnostic', exact: true, includeHidden: true}).isVisible(), false, 'review administration is secondary');
          if (width === 1440) {
            const panel = name === 'install-open' ? surface : surface.locator('section.provider-card').first();
            assert((await panel.boundingBox()).width <= 961, 'shared readable panel width');
          }
        }
        if (name === 'update-unknown') assert.equal(await surface.locator(`a[href^='/admin/devices/']`).count(), 0, 'unknown identity has no guessed device route');
        await page.screenshot({path: path.join(output, `${name}-${width}.png`), fullPage: true});
      }
    }
    await page.setViewportSize({width: 320, height: 900});
    for (const name of ['install-open', 'update-open']) {
      const surface = await load(name);
      const copy = surface.getByRole('button', {name: 'Copy issue report', exact: true});
      await copy.focus();
      await page.keyboard.press('Enter');
      assert(await page.evaluate(() => window.__copiedReports.length > 0), name + ' narrow keyboard copy');
      await surface.getByText('Preview issue report', {exact: true}).click();
      await assertFits(name + '/320/expanded-issue');
      await surface.locator('[data-issue-preview-body]').scrollIntoViewIfNeeded();
      if (name === 'update-open') await page.evaluate(() => {window.scrollTo(0, 0); document.activeElement?.blur();});
      await page.screenshot({path: path.join(output, `${name}-320-actions.png`), fullPage: true});
      await surface.getByText('Technical details', {exact: true}).click();
      await assertFits(name + '/320/expanded-technical');
      if (name === 'update-open') assert((await surface.innerText()).includes('readback')); 
    }
    await page.setViewportSize({width: 720, height: 900});
    for (const name of ['install-open', 'update-open', 'update-unknown', 'device-updates']) {
      await load(name);
      for (const rtl of [false, true]) {
        await page.evaluate(rtl => {document.body.style.zoom = '2'; document.documentElement.dir = rtl ? 'rtl' : 'ltr';}, rtl);
        await assertFits(`${name}/200%/${rtl}`);
      }
    }
    await page.setViewportSize({width: 1440, height: 1000});
    for (const kind of ['install', 'update']) {
      state[kind] = 'open';
      await page.goto(`${base}/admin/${kind === 'install' ? 'diagnostics' : 'update-diagnostics'}?timeZone=UTC`);
      let surface = kind === 'install' ? await openInstall() : page.locator('main');
      const githubHeading = surface.getByText('GitHub issue', {exact: true});
      if (await githubHeading.evaluate(el => el.tagName === 'SUMMARY' && !el.parentElement.open)) await githubHeading.click();
      const innerDisclosure = surface.getByText('Report an anomaly or link issue', {exact: true});
      if (await innerDisclosure.count()) await innerDisclosure.click();
      await surface.getByText('Preview issue report', {exact: true}).click();
      assert(await surface.locator('[data-issue-preview-title]').inputValue());
      assert(await surface.locator('[data-issue-preview-body]').inputValue());
      await surface.locator('[data-issue-note]').fill('Check this failure. /Users/synthetic/private token=synthetic-secret tester@example.invalid');
      const body = await surface.locator('[data-issue-preview-body]').inputValue();
      assert(!body.includes('/Users/synthetic/private') && !body.includes('synthetic-secret') && !body.includes('tester@example.invalid'));
      await surface.getByRole('button', {name: 'Copy issue report', exact: true}).click();
      assert((await page.evaluate(() => window.__copiedReports.at(-1))).includes(body));
      const prepare = surface.locator('[data-github-create]');
      const url = new URL(await prepare.getAttribute('href'));
      assert.equal(url.origin + url.pathname, 'https://github.com/VooZ2/terento/issues/new');
      assert(url.href.length <= Number(await prepare.getAttribute('data-url-limit')));
      if (await prepare.getAttribute('data-prefilled') === 'true') {
        const popupPromise = context.waitForEvent('page');
        await prepare.focus();
        await page.keyboard.press('Enter');
        const popup = await popupPromise;
        await popup.waitForLoadState();
        await popup.close();
      }
      // Exercise the bounded URL fallback without creating a remote issue.
      await prepare.evaluate(el => el.dataset.issueBody = 'X'.repeat(9000));
      await surface.locator('[data-issue-note]').fill('Long report fixture');
      assert.equal(await prepare.getAttribute('data-prefilled'), 'false');
      await prepare.click();
      assert((await page.evaluate(() => window.__copiedReports.at(-1))).length > 9000);
      await surface.getByText('Link or manage an existing issue', {exact: true}).click();
      await surface.locator('input[name="linked_github_issue"]').fill('#325');
      await surface.getByRole('button', {name: 'Link issue', exact: true}).click();
      await page.waitForLoadState();
      await page.waitForFunction(() => !document.querySelector('form[data-submitting="true"]'));
      assert.equal(mutations.at(-1).action, 'issue');
      assert.equal(mutations.at(-1).data.linked_github_issue, '#325');
      // Open the linked fixture after the form's actual reload.
      await page.reload();
      surface = kind === 'install' ? await openInstall() : page.locator('main');
      const resolve = surface.getByRole('button', {name: 'Resolve diagnostic', exact: true, includeHidden: true});
      await resolve.evaluate(el => {let p=el.parentElement; while(p){if(p.tagName === 'DETAILS')p.open=true; p=p.parentElement;}});
      await resolve.click();
      await page.waitForFunction(() => !document.querySelector('form[data-submitting="true"]'));
      assert.equal(mutations.at(-1).action, 'resolve');
      await page.reload();
      surface = kind === 'install' ? await openInstall() : page.locator('main');
      const reopen = surface.getByRole('button', {name: 'Reopen diagnostic', exact: true, includeHidden: true});
      await reopen.evaluate(el => {let p=el.parentElement; while(p){if(p.tagName === 'DETAILS')p.open=true; p=p.parentElement;}});
      await reopen.click();
      await page.waitForFunction(() => !document.querySelector('form[data-submitting="true"]'));
      assert.equal(mutations.at(-1).action, 'reopen');
    }
    await load('install-open');
    const modal = page.locator('dialog[open]');
    await modal.locator('[data-close-dialog]').focus();
    await page.keyboard.press('Shift+Tab');
    assert(await modal.evaluate(el => el.contains(document.activeElement)), 'focus trapped in modal');
    await page.keyboard.press('Escape');
    assert.equal(await modal.count(), 0, 'Escape closes dialog');
    assert(await page.locator('button[data-dialog-id]').first().evaluate(el => el === document.activeElement), 'focus restored to trigger');
    await load('update-open');
    await page.locator(`a[href^='/admin/devices/${deviceID}']`).first().click();
    assert((await page.locator('main').innerText()).includes('Update history'));
    const installStats = page.getByRole('group', {name: 'Model installation statistics'});
    assert((await installStats.innerText()).includes('12'));
    assert((await installStats.innerText()).includes('11'));
    const updateStats = page.locator('[aria-labelledby="model-update-kpis-title"]');
    // Update counts are plain numbers (owner decision 2026-10-06); outcome filtering lives in Update history.
    assert.deepEqual(await updateStats.locator('[data-stat]').allTextContents().then(v => v.map(s => s.trim())), ['7','2','1']);
    assert.equal(await updateStats.locator('a').count(), 0);
    assert.equal(await page.locator('#installations tbody tr').count(), 1);
    assert.equal(await page.locator('#updates tbody tr').count(), 3);
    const failedLink = page.locator('#updates .quick-filter').filter({hasText: /^Failed$/});
    const failedURL = new URL(await failedLink.getAttribute('href'), base);
    assert(failedURL.pathname.includes(deviceID));
    assert.equal(failedURL.searchParams.get('updateOutcome'), 'failed');
    await page.locator('#updates a.update-history-inspect').nth(1).click();
    assert(page.url().includes('diagnosticId=' + diagnosticID));
    // Initial server-rendered identity options must work without a search input event.
    for (const exactID of [deviceID, 'fenix-8-47-amoled']) {
      const surface = await load('install-ambiguous');
      const form = surface.locator('[data-identity-form]');
      assert.equal(await form.locator('[data-identity-search]').inputValue(), '');
      assert.equal(await form.locator('[data-identity-device-id]').count(), 2);
      assert.equal(await form.locator('[data-identity-confirm]').isDisabled(), true);
      await form.locator(`[data-identity-device-id='${exactID}']`).click();
      assert.equal(await form.locator('input[name="canonical_device_model_id"]').inputValue(), exactID);
      assert.equal(await form.locator('[data-identity-confirm]').isDisabled(), false);
    }
    const ambiguous = await load('install-ambiguous');
    const picker = ambiguous.locator('[data-identity-form]');
    const search = picker.locator('[data-identity-search]');
    const firstID = await picker.locator('[data-identity-device-id]').first().getAttribute('data-identity-device-id');
    await search.focus();
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');
    assert.equal(await picker.locator('input[name="canonical_device_model_id"]').inputValue(), firstID);
    assert.equal(await picker.locator('[data-identity-confirm]').isDisabled(), false);
    await picker.locator('[data-identity-edit]').click();
    await search.fill('47');
    assert.equal(await picker.locator('input[name="canonical_device_model_id"]').inputValue(), '');
    assert.equal(await picker.locator('[data-identity-confirm]').isDisabled(), true);
    await picker.locator("[data-identity-device-id='fenix-8-47-amoled']").click();
    await picker.locator('[data-identity-confirm]').click();
    await page.waitForFunction(() => !document.querySelector('form[data-submitting="true"]'));
    assert.equal(mutations.at(-1).action, 'identity');
    assert.equal(mutations.at(-1).data.canonical_device_model_id, 'fenix-8-47-amoled');
    assert.equal(mutations.at(-1).data.identity_action, 'ASSIGN');
    assert.equal(mutations.at(-1).data.csrf_token, 'fixture');
    assert.deepEqual(errors, []);
    assert(external.every(request => request.method === 'GET'), 'no remote writes');
    console.log('PASS diagnostic parity: 20 page/width LTR+RTL, 200% CSS zoom, GitHub preview/sanitization/copy/bounded preparation, mock issue link/resolve/reopen, unknown identity, exact-device navigation, dialog ARIA/focus/Escape, initial identity choices/mouse/keyboard/search clearing/exact-ID confirmation.');
  } finally {await browser.close();}
})().catch(error => {console.error(error); process.exitCode = 1;});
