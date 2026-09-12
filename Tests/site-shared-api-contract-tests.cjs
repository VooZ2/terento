const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const fixture = name => JSON.parse(fs.readFileSync(path.join(root, 'contracts/fixtures', `${name}.json`), 'utf8'));
const script = fs.readFileSync(path.join(root, 'site/provider-list.js'), 'utf8');

// Run the production script without changing the public asset or its caching.
async function present(payload, fail = false, cardID = 'freizeitkarte', mapType = '') {
  const counter = { dataset: { countTemplate: '{count} packages in {countries} countries' }, textContent: 'Static fallback' };
  const contourCounter = { dataset: { countTemplate: '{count} contour regions' }, textContent: 'Contour fallback' };
  const addon = { hidden: false, querySelector: () => contourCounter };
  const card = { dataset: { providerCard: cardID, providerType: mapType }, hidden: Boolean(mapType),
    querySelector: selector => selector === '[data-provider-count]' ? counter : cardID === 'opentopomap' ? addon : null };
  let requests = 0;
  vm.runInNewContext(script, {
    document: { querySelector: () => null, querySelectorAll: selector => { assert.equal(selector, '[data-provider-card]'); return [card]; } },
    fetch: async (url, options) => {
      requests++;
      assert.equal(url, 'https://api.terento.app/maps/catalog-v4.json');
      assert.equal(options.headers.Accept, 'application/json');
      if (fail) throw Error('offline');
      return { ok: true, json: async () => payload };
    },
  });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(requests, 1);
  return { hidden: card.hidden, text: counter.textContent, ...(cardID === 'opentopomap' ? { addonHidden: addon.hidden, addonText: contourCounter.textContent } : {}) };
}

// Exercise the actual controls, keyboard handling, resize and reduced motion.
function checkNavigation(reducedMotion) {
  const listeners = {};
  const button = () => ({ disabled: false, addEventListener(type, action) { this[type] = action; } });
  const previous = button(), next = button();
  const controls = { hidden: true, querySelector: selector => selector === '[data-provider-previous]' ? previous : next };
  let behavior;
  const row = { scrollWidth: 630, clientWidth: 339, scrollLeft: 0,
    getBoundingClientRect: () => ({left: 18}),
    addEventListener: (type, action) => { listeners[type] = action; },
    scrollBy(options) { behavior = options.behavior; this.scrollLeft = Math.max(0, Math.min(291, this.scrollLeft + options.left)); listeners.scroll(); },
  };
  const cards = [0, 1].map(index => ({ hidden: false,
    getBoundingClientRect: () => ({left: 18 + index * 325 - row.scrollLeft}),
  }));
  vm.runInNewContext(script, {
    document: { querySelectorAll: () => cards, querySelector: selector => selector === '[data-provider-cards]' ? row : controls },
    window: { matchMedia: () => ({matches: reducedMotion}), addEventListener: (type, action) => { listeners[type] = action; } },
    fetch: async () => { throw Error('offline'); },
  });
  assert.equal(controls.hidden, false);
  assert.equal(previous.disabled, true);
  next.click();
  assert.equal(row.scrollLeft, 291);
  assert.equal(next.disabled, true);
  assert.equal(behavior, reducedMotion ? 'instant' : 'smooth');
  let prevented = false;
  listeners.keydown({target: row, key: 'ArrowLeft', preventDefault() { prevented = true; }});
  assert.equal(prevented, true);
  assert.equal(row.scrollLeft, 0);
  assert.equal(previous.disabled, true);
  row.clientWidth = 630;
  listeners.resize();
  assert.equal(controls.hidden, true);
  assert.equal(row.tabIndex, -1);
}

(async () => {
  checkNavigation(false);
  checkNavigation(true);
  const valid = fixture('map-catalog.valid');
  const provider = valid.providers.find(p => p.id === 'freizeitkarte');
  assert.equal(provider.status, 'ACTIVE');
  assert.ok(provider.maps.length > 0);
  // A legacy serialized map can omit availability: preserve the existing fallback.
  const initial = await present(valid);
  assert.equal(initial.hidden, false);
  const available = structuredClone(valid);
  available.providers[0].maps[0].availability = 'AVAILABLE';
  const rendered = await present(available);
  assert.deepEqual(rendered, { hidden: false, text: '1 packages in 1 countries' });
  const additive = structuredClone(available);
  additive.futureField = { ignored: true };
  additive.providers[0].futureField = 1;
  additive.providers[0].maps[0].futureField = 'ignored';
  assert.deepEqual(await present(additive), rendered);
  assert.deepEqual(await present(fixture('map-catalog.invalid-missing-schema-version')), initial);
  assert.deepEqual(await present(fixture('map-catalog.invalid-missing-providers')), { hidden: false, text: 'Static fallback' });
  assert.deepEqual(await present(valid, true), { hidden: false, text: 'Static fallback' });
  const missingMaps = structuredClone(available);
  delete missingMaps.providers[0].maps;
  assert.deepEqual(await present(missingMaps), { hidden: false, text: 'Static fallback' });
  const missingCountry = structuredClone(available);
  delete missingCountry.providers[0].maps[0].country;
  delete missingCountry.providers[0].maps[0].countryCodes;
  assert.deepEqual(await present(missingCountry), { hidden: false, text: '1 packages in 0 countries' });
  const missingProviderID = structuredClone(available);
  delete missingProviderID.providers[0].id;
  assert.equal((await present(missingProviderID)).hidden, true);
  const maprando = { providers: [{ id: 'maprando', status: 'ACTIVE', maps: [] }] };
  assert.deepEqual(await present(maprando, false, 'maprando'), { hidden: false, text: '0 packages in 0 countries' });
  maprando.providers[0].maps = [{ availability: 'AVAILABLE', country: 'LT' }, { availability: 'UNAVAILABLE', country: 'NZ' }];
  assert.deepEqual(await present(maprando, false, 'maprando'), { hidden: false, text: '1 packages in 1 countries' });
  maprando.providers[0].status = 'PAUSED';
  assert.equal((await present(maprando, false, 'maprando')).hidden, true);
  const bbbike = { providers: [{id: 'bbbike', status: 'ACTIVE', maps: [
    {availability: 'AVAILABLE', mapType: 'bbbike-latin1', countryCodes: ['LT']},
    {availability: 'AVAILABLE', mapType: 'ontrail-latin1', countryCodes: ['LT']},
    {availability: 'AVAILABLE', mapType: 'ontrail-latin1', countryCodes: ['LT', 'PL']},
    {availability: 'WITHHELD', mapType: 'ontrail-latin1', countryCodes: ['RU']},
  ]}] };
  assert.deepEqual(await present(bbbike, false, 'bbbike', 'bbbike-latin1'), {hidden: false, text: '1 packages in 1 countries'});
  assert.deepEqual(await present(bbbike, false, 'bbbike', 'ontrail-latin1'), {hidden: false, text: '2 packages in 2 countries'});
  assert.equal((await present(bbbike, true, 'bbbike', 'ontrail-latin1')).hidden, true, 'Unreleased type stays hidden when offline');
  assert.equal((await present(bbbike, false, 'bbbike', 'other-type')).hidden, true);
  bbbike.providers[0].status = 'PAUSED';
  assert.equal((await present(bbbike, false, 'bbbike', 'bbbike-latin1')).hidden, true);
  const contours = structuredClone(valid);
  contours.providers = [{
    id: 'opentopomap',
    status: 'ACTIVE',
    maps: [{
      availability: 'AVAILABLE',
      artifacts: [{ kind: 'contours', validationStatus: 'VALIDATED' }],
    }],
  }];
  assert.deepEqual(await present(contours, false, 'opentopomap'), { hidden: false, text: '1 packages in 0 countries', addonHidden: false, addonText: '1 contour regions' });
  contours.providers[0].maps[0].artifacts[0].validationStatus = 'REJECTED';
  assert.deepEqual(await present(contours, false, 'opentopomap'), { hidden: false, text: '1 packages in 0 countries', addonHidden: true, addonText: 'Contour fallback' });
  assert.deepEqual(await present(contours, true, 'opentopomap'), { hidden: false, text: 'Static fallback', addonHidden: false, addonText: 'Contour fallback' });
  contours.providers[0].maps[0].artifacts = [{kind: 'contours', validationState: 'VALIDATED'}, {kind: 'contours', validationStatus: 'VALIDATED'}];
  assert.equal((await present(contours, false, 'opentopomap')).addonText, '1 contour regions');
  contours.providers[0].maps[0].availability = 'WITHHELD';
  assert.equal((await present(contours, false, 'opentopomap')).addonHidden, true);
  console.log('PASS: production provider cards consume shared fixtures, tolerate additive fields and preserve fallback behavior');
})().catch(error => { console.error(error); process.exitCode = 1; });
