const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const fixture = name => JSON.parse(fs.readFileSync(path.join(root, 'contracts/fixtures', `${name}.json`), 'utf8'));
const script = fs.readFileSync(path.join(root, 'site/provider-list.js'), 'utf8');

// Run the production script without changing the public asset or its caching.
async function present(payload, fail = false) {
  const counter = { dataset: { countTemplate: '{count} packages in {countries} countries' }, textContent: 'Static fallback' };
  const card = { dataset: { providerCard: 'freizeitkarte' }, hidden: false,
    querySelector: selector => { assert.equal(selector, '[data-provider-count]'); return counter; } };
  let requests = 0;
  vm.runInNewContext(script, {
    document: { querySelectorAll: selector => { assert.equal(selector, '[data-provider-card]'); return [card]; } },
    fetch: async (url, options) => {
      requests++;
      assert.equal(url, 'https://api.terento.app/maps/catalog.json');
      assert.equal(options.headers.Accept, 'application/json');
      if (fail) throw Error('offline');
      return { ok: true, json: async () => payload };
    },
  });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(requests, 1);
  return { hidden: card.hidden, text: counter.textContent };
}

(async () => {
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
  assert.deepEqual(await present(missingCountry), { hidden: false, text: '1 packages in 0 countries' });
  const missingProviderID = structuredClone(available);
  delete missingProviderID.providers[0].id;
  assert.equal((await present(missingProviderID)).hidden, true);
  console.log('PASS: production provider cards consume shared fixtures, tolerate additive fields and preserve fallback behavior');
})().catch(error => { console.error(error); process.exitCode = 1; });
