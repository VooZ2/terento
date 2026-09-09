const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
const snapshot = JSON.parse(read('site/compatibility/public-models.snapshot.json'));
const data = require('../site/compatibility/compatibility-data.js');
const locales = require('../site/compatibility/compatibility-locales.js');

assert.equal(data.publicModelName('fēnix 9 Pro · inReach, 51 mm'), 'fēnix 9 Pro · inReach');
assert.equal(locales.getLocale('it').successfulInstallLabel(2), '2 installazioni riuscite');
assert.equal(locales.getLocale('de').successfulInstallLabel(2), '2 erfolgreiche Installationen');
for (const language of ['en', 'de', 'fr', 'pl', 'cs', 'it']) {
  const prefix = language === 'en' ? '' : language + '/';
  const copy = locales.getLocale(language);
  const page = read(`site/${prefix}compatibility/index.html`);
  const embedded = JSON.parse(page.match(/id="compatibility-snapshot">([\s\S]*?)<\/script>/)[1]);
  assert.deepEqual(embedded, snapshot, `${language}: exact static/API snapshot parity`);
  assert.ok(page.includes(copy.summary.moreModels), `${language}: localized summary`);
  assert.equal((page.match(/id="compatibility-clear"/g) || []).length, 1);
  assert.equal((page.match(/id="compatibility-freshness"/g) || []).length, 1);
  assert.ok(page.indexOf('id="compatibility-clear"') < page.indexOf('id="watch-grid"'));
  const download = read(`site/${prefix}download/index.html`);
  assert.ok(download.includes(`<span class="download-recommended">${copy.freshness.recommended}</span>`));
  for (const asset of ['compatibility', 'compatibility-data', 'compatibility-locales']) {
    assert.ok(page.includes(`${asset}.js?v=20260909-post-audit-v1`));
  }
}

async function checkRefreshAndFilters() {
  const nodes = new Map();
  function node(selector) {
    if (!nodes.has(selector)) nodes.set(selector, {
      textContent: '', innerHTML: '', hidden: false, value: '', style: {}, listeners: {},
      setAttribute() {}, querySelectorAll() { return []; }, insertAdjacentHTML() {},
      addEventListener(event, callback) { this.listeners[event] = callback; }, focus() { this.focused = true; },
    });
    return nodes.get(selector);
  }
  node('#compatibility-snapshot').textContent = JSON.stringify(snapshot);
  let offline = true;
  let requests = 0;
  const payload = {...snapshot, models: snapshot.models.slice(0, 1)};
  vm.runInNewContext(read('site/compatibility/compatibility.js'), {
    TerentoCompatibilityData: data,
    TerentoCompatibilityLocale: locales.getLocale('en'),
    document: {querySelector: node},
    window: {location: {hostname: 'terento.app'}, setInterval() {}},
    console: {error() {}}, Intl, Date,
    fetch: async () => { requests++; if (offline) throw Error('offline'); return {ok: true, json: async () => payload}; },
  });
  const flush = () => new Promise(resolve => setImmediate(resolve));
  await flush();
  assert.equal(node('[data-summary="models"]').textContent, String(snapshot.models.length));
  assert.match(node('#compatibility-freshness').textContent, /Could not refresh/);
  assert.equal(node('#compatibility-retry').hidden, false);
  assert.ok(node('#watch-grid').innerHTML.includes('watch-card'));
  offline = false;
  await node('#compatibility-retry').listeners.click();
  await flush();
  assert.equal(requests, 2);
  assert.equal(node('#compatibility-retry').hidden, true);
  assert.equal(node('[data-summary="models"]').textContent, '1');
  assert.match(node('#compatibility-freshness').textContent, /Evidence refreshed/);
  node('#watch-search').listeners.input({target: {value: 'no-such-watch'}});
  assert.equal(node('#compatibility-empty').hidden, false);
  assert.equal(node('#watch-grid').innerHTML, '');
  node('#compatibility-clear').listeners.click();
  assert.equal(node('#compatibility-empty').hidden, true);
  assert.equal(node('#watch-search').focused, true);
  assert.ok(node('#watch-grid').innerHTML.includes('watch-card'));
}
checkRefreshAndFilters().then(() => console.log('PASS: six-locale snapshots, cache versions, stale recovery, retry and filter reset')).catch(error => { console.error(error); process.exitCode = 1; });
