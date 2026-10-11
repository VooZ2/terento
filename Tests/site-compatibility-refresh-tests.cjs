"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");
const data = require("../site/compatibility/compatibility-data.js");
const locales = require("../site/compatibility/compatibility-locales.js");

for (const language of ["en", "de", "fr", "pl", "cs", "it"]) {
  const prefix = language === "en" ? "" : `${language}/`;
  const page = read(`site/${prefix}compatibility/index.html`);
  assert.match(page, /id="compatibility-snapshot"/, `${language}: snapshot is checked in`);
  assert.match(page, /class="watch-card"/, `${language}: cards are server-rendered`);
  assert.match(page, /id="successful-install-filter"/, `${language}: successful-install filter`);
  assert.equal((page.match(/id="compatibility-clear"/g) || []).length, 1);
  assert.equal((page.match(/id="compatibility-snapshot"/g) || []).length, 1);
  assert.ok(!page.includes('option value="successes"'), `${language}: obsolete success filter removed`);
  assert.equal(locales.getLocale(language).successfulInstallLabel(2).includes("2"), true);
}

async function checkSnapshotFirstAndRefresh() {
  const nodes = new Map();
  const snapshot = {
    schemaVersion: 1,
    generatedAt: "2026-09-18T17:25:07Z",
    models: [
      { model: "fēnix 8 · 47 mm, AMOLED", variant: "47 mm, AMOLED", caseSizeMm: 47, family: "fenix", familyName: "fēnix", successfulInstallations: 11, lastSuccessfulInstallation: "2026-09-18T11:17:55Z" },
      { model: "Forerunner 955 · Standard", variant: "Standard", family: "forerunner", familyName: "Forerunner", successfulInstallations: 4, lastSuccessfulInstallation: "2026-09-15T09:45:54Z" },
    ],
  };
  function node(selector) {
    if (!nodes.has(selector)) {
      const current = {
        textContent: selector === "#compatibility-snapshot" ? JSON.stringify(snapshot) : "",
        innerHTML: "",
        hidden: ["#compatibility-error", "#compatibility-retry", "#compatibility-empty", ".compatibility-freshness"].includes(selector),
        value: selector === "#sort-filter" ? "successful" : "ALL",
        options: [{ value: "ALL", remove() {} }],
        listeners: {},
        setAttribute(name, value) { this.attributes = {...this.attributes, [name]: value}; },
        querySelectorAll(query) {
          if (query.startsWith("option")) return this.options.slice(1);
          return [];
        },
        insertAdjacentHTML(position, html) {
          for (const match of html.matchAll(/<option value="([^"]+)">([^<]*)<\/option>/g)) {
            this.options.push({ value: match[1], textContent: match[2], remove() {} });
          }
        },
        addEventListener(event, callback) { this.listeners[event] = callback; },
        focus() { this.focused = true; },
      };
      nodes.set(selector, current);
    }
    return nodes.get(selector);
  }

  let refreshFails = true;
  let requests = 0;
  const livePayload = {
    generatedAt: "2026-09-18T17:25:07Z",
    models: [
      { model: "fēnix 8 · 47 mm, AMOLED", variant: "47 mm, AMOLED", caseSizeMm: 47, family: "fenix", familyName: "fēnix", successfulInstallations: 11, lastSuccessfulInstallation: "2026-09-18T11:17:55Z" },
      { model: "fēnix 8 Pro · 47 mm, AMOLED", variant: "47 mm, AMOLED", caseSizeMm: 47, family: "fenix", familyName: "fēnix", successfulInstallations: 2, lastSuccessfulInstallation: "2026-09-02T22:00:21Z" },
      { model: "Forerunner 970 · AMOLED", variant: "AMOLED", family: "forerunner", familyName: "Forerunner", successfulInstallations: 1234, appSuccessfulInstallations: 1180, webSuccessfulInstallations: 54, lastSuccessfulInstallation: "2026-10-11T09:00:00Z" },
      { model: "TESTING-only row", successfulInstallations: 0, evidenceStatus: "TESTING", family: "other", familyName: "Other" },
    ],
  };
  const context = {
    TerentoCompatibilityData: data,
    TerentoCompatibilityLocale: locales.getLocale("en"),
    document: { querySelector: node },
    window: { location: { hostname: "terento.app" }, setInterval() {} },
    console: { error() {} }, Intl, Date,
    fetch: async () => {
      requests += 1;
      if (refreshFails) throw new Error("offline");
      return { ok: true, json: async () => livePayload };
    },
  };
  vm.runInNewContext(read("site/compatibility/compatibility.js"), context);
  const flush = () => new Promise(resolve => setImmediate(resolve));
  await flush();

  assert.equal(requests, 1);
  assert.equal(node('[data-summary="models"]').textContent, "2");
  assert.ok(node("#watch-grid").innerHTML.includes("watch-card"));
  assert.equal(node("#compatibility-error").hidden, true);
  assert.equal(node("#compatibility-retry").hidden, false);
  assert.match(node("#compatibility-freshness").textContent, /Could not refresh/);

  refreshFails = false;
  await node("#compatibility-retry").listeners.click();
  await flush();
  assert.equal(requests, 2);
  assert.equal(node('[data-summary="models"]').textContent, "3");
  assert.equal(node('[data-summary="successes"]').textContent, "1,247");
  // Summary stays exact; cards round from 100 and show the app/web split.
  const grid = node("#watch-grid").innerHTML;
  assert.match(grid, />1,200\+ successful installs<\/p>/);
  assert.match(grid, /<\/svg>App 1,100\+<\/span> <span class="watch-install-source"><svg[^>]*viewBox="0 0 512 512">[\s\S]*?<\/svg>Web 54<\/span>/);
  assert.match(grid, /aria-label="Forerunner 970, AMOLED, 1,200\+ successful installs, 1,100\+ with the app, 54 with the web installer, Latest successful install/);
  assert.match(grid, /11 successful installs<\/p><p class="watch-install-sources"><span class="watch-install-source"><svg[^>]*>[\s\S]*?<\/svg>App 11<\/span><\/p>/, "older rows count every success as app");
  assert.equal((grid.match(/Font Awesome Free 7\.3\.1/g) || []).length, 4);
  assert.ok(!node("#watch-grid").innerHTML.includes("TESTING-only row"));
  assert.equal(node("#compatibility-retry").hidden, true);

  const headings = () => [...node("#watch-grid").innerHTML.matchAll(/<h3>(.*?)<\/h3>/g)].map(match => match[1]);
  assert.deepEqual(headings(), ["Forerunner 970", "fēnix 8", "fēnix 8 Pro"]);
  node("#successful-install-filter").listeners.change({target: {value: "1_2"}});
  assert.deepEqual(headings(), ["fēnix 8 Pro"]);
  node("#sort-filter").listeners.change({target: {value: "name"}});
  assert.deepEqual(headings(), ["fēnix 8 Pro"]);
  node("#compatibility-clear").listeners.click();
  assert.deepEqual(headings(), ["Forerunner 970", "fēnix 8", "fēnix 8 Pro"]);
  assert.equal(node("#watch-search").focused, true);

  refreshFails = true;
  await node("#compatibility-retry").listeners.click();
  await flush();
  assert.ok(node("#watch-grid").innerHTML.includes("watch-card"));
  assert.match(node("#compatibility-freshness").textContent, /Could not refresh/);
}

checkSnapshotFirstAndRefresh()
  .then(() => console.log("PASS: static snapshot, live refresh, zero-success filtering, fallback, and UI filters"))
  .catch(error => { console.error(error); process.exitCode = 1; });
