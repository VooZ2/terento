const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
const data = require('../site/compatibility/compatibility-data.js');
const locales = require('../site/compatibility/compatibility-locales.js');

assert.equal(data.publicModelName('fēnix 9 Pro · inReach, 51 mm'), 'fēnix 9 Pro · inReach');
assert.equal(locales.getLocale('it').successfulInstallLabel(2), '2 installazioni riuscite');
assert.equal(locales.getLocale('de').successfulInstallLabel(2), '2 erfolgreiche Installationen');
for (const language of ['en', 'de', 'fr', 'pl', 'cs', 'it']) {
  const prefix = language === 'en' ? '' : language + '/';
  const copy = locales.getLocale(language);
  const page = read(`site/${prefix}compatibility/index.html`);
  assert.doesNotMatch(page, /id="compatibility-snapshot"|watch-card/, `${language}: no checked-in compatibility evidence`);
  assert.match(page, /data-summary="models"><\/strong>/, `${language}: model count waits for the API`);
  assert.match(page, /id="watch-grid"[^>]*aria-busy="true"><\/div>/, `${language}: result grid waits for the API`);
  assert.doesNotMatch(page, /More models ready for testing|Weitere Modelle zum Testen|D’autres modèles prêts à être testés|Kolejne modele gotowe do testów|Další modely připravené k testování|Altri modelli pronti per i test/, `${language}: removed testing prompt`);
  assert.doesNotMatch(page, /Evidence refreshed|Nachweise aktualisiert|Données actualisées|Dane odświeżone|Údaje aktualizovány|Dati aggiornati/, `${language}: removed refresh label`);
  assert.equal((page.match(/id="compatibility-clear"/g) || []).length, 1);
  assert.equal((page.match(/id="compatibility-freshness"/g) || []).length, 1);
  assert.match(page, /class="compatibility-freshness"[^>]* hidden/);
  assert.ok(page.indexOf('id="compatibility-clear"') < page.indexOf('id="watch-grid"'));
  const download = read(`site/${prefix}download/index.html`);
  assert.ok(download.includes(`<span class="download-recommended">${copy.freshness.recommended}</span>`));
  for (const asset of ['compatibility', 'compatibility-data', 'compatibility-locales']) {
    assert.ok(page.includes(`${asset}.js?v=${asset === "compatibility-locales" ? "20260911-three-providers-v2" : "20260910-summary-v1"}`));
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
  let offline = true;
  let requests = 0;
  const payload = {
    schemaVersion: 1,
    generatedAt: '2026-09-10T17:30:23Z',
    models: [{
      model: 'fēnix 9 Pro · inReach, 51 mm',
      compatibilityIdentity: 'fenix 9 Pro - inReach, 51mm',
      variant: '51mm',
      caseSizeMm: 51,
      family: 'fenix',
      familyName: 'fēnix',
      attemptedInstallations: 2,
      successfulInstallations: 2,
      failedInstallations: 0,
      evidenceStatus: 'TESTED',
      lastSuccessfulInstallation: '2026-09-10T16:25:51Z',
    }],
  };
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
  assert.equal(node('[data-summary="models"]').textContent, '');
  assert.match(node('#compatibility-freshness').textContent, /Could not load live/);
  assert.equal(node('#compatibility-retry').hidden, false);
  assert.equal(node('#watch-grid').innerHTML, '');
  assert.equal(node('#compatibility-error').hidden, false);
  offline = false;
  await node('#compatibility-retry').listeners.click();
  await flush();
  assert.equal(requests, 2);
  assert.equal(node('#compatibility-retry').hidden, true);
  assert.equal(node('[data-summary="models"]').textContent, '1');
  assert.equal(node('#compatibility-freshness').textContent, '');
  assert.equal(node('.compatibility-freshness').hidden, true);
  assert.equal(node('[data-summary="successes"]').textContent, '2');
  assert.ok(node('#watch-grid').innerHTML.includes('watch-card'));
  offline = true;
  await node('#compatibility-retry').listeners.click();
  await flush();
  assert.match(node('#compatibility-freshness').textContent, /last results loaded from the API/);
  assert.ok(node('#watch-grid').innerHTML.includes('watch-card'));
  node('#watch-search').listeners.input({target: {value: 'no-such-watch'}});
  assert.equal(node('#compatibility-empty').hidden, false);
  assert.equal(node('#watch-grid').innerHTML, '');
  node('#compatibility-clear').listeners.click();
  assert.equal(node('#compatibility-empty').hidden, true);
  assert.equal(node('#watch-search').focused, true);
  assert.ok(node('#watch-grid').innerHTML.includes('watch-card'));
}
checkRefreshAndFilters().then(() => console.log('PASS: six-locale API loading, cache versions, retry and filter reset')).catch(error => { console.error(error); process.exitCode = 1; });
