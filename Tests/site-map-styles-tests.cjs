"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const data = require(path.join(root, "site", "map-styles", "map-styles-data.js"));
const locales = ["en", "de", "fr", "pl", "cs", "it"];
const read = (file) => fs.readFileSync(file, "utf8");
const localeFile = (locale, suffix) => path.join(root, "site", locale === "en" ? "" : locale, suffix, "index.html");
const contract = JSON.parse(read(path.join(root, "contracts", "map-preview-areas.json")));
const decode = (text) => text
  .replace(/&#x27;|&#39;/g, "'")
  .replace(/&quot;/g, "\"")
  .replace(/&lt;/g, "<")
  .replace(/&gt;/g, ">")
  .replace(/&amp;/g, "&");

function pageData(locale) {
  const match = read(localeFile(locale, "map-styles")).match(/<script type="application\/json" id="map-styles-data">([\s\S]*?)<\/script>/);
  assert.ok(match, `${locale}: embedded page data is missing`);
  return JSON.parse(match[1]);
}

function homeCards(locale) {
  const source = read(localeFile(locale, ""));
  const cards = [];
  const pattern = /<article class="provider-card" data-provider-card="([^"]+)"[^>]*>([\s\S]*?)<\/article>/g;
  let match;
  while ((match = pattern.exec(source))) {
    const body = match[2];
    cards.push({
      name: decode(body.match(/<h3>([\s\S]*?)<\/h3>/)[1].trim()),
      summary: decode(body.match(/<p class="provider-summary">([\s\S]*?)<\/p>/)[1].trim()),
      benefits: [...body.matchAll(/<li>([\s\S]*?)<\/li>/g)].map((item) => decode(item[1].trim())),
    });
  }
  return cards;
}

function testHelpers() {
  const area = {kind: "place", center: [12.3, 46.62], sizeKm: [16, 16], zoom: [12, 16]};
  const [west, south, east, north] = data.bbox(area);
  assert.ok(west < 12.3 && east > 12.3 && south < 46.62 && north > 46.62);
  assert.ok(Math.abs((north - south) * 111.32 - 16) < 0.01);
  assert.equal(data.defaultZoom(area), 13);
  assert.equal(data.defaultZoom({...area, kind: "city", zoom: [12, 17]}), 14);

  assert.equal(data.plural("en", {one: "{n} map", other: "{n} maps"}, 1), "1 map");
  assert.equal(data.plural("pl", {one: "{n} mapa", few: "{n} mapy", many: "{n} map", other: "{n} mapy"}, 5), "5 map");
  assert.ok(data.matches({name: "Tre Cime", routeName: null, countryCodes: ["IT"], tags: ["alpine"]}, "italy", () => "Italy"));
  assert.ok(data.matches({name: "Krkonoše", routeName: null, countryCodes: ["CZ"], tags: []}, "krkonose"));
  assert.ok(!data.matches({name: "Zermatt", routeName: null, countryCodes: ["CH"], tags: []}, "fuji"));

  const state = {area: "zermatt", a: "opentopomap", b: "bbbike", mode: "swipe"};
  assert.deepEqual(data.parseHash(data.serializeHash(state)), {area: "zermatt", style: "opentopomap", compare: "bbbike", mode: "swipe"});
  assert.equal(data.serializeHash({...state, mode: "single"}), "#area=zermatt&style=opentopomap");
  assert.equal(data.parseHash("#mode=bogus").mode, null);

  const manifest = {
    tileUrlTemplate: "https://api.terento.app/assets/previews/20261006T010000Z/{area}/{style}/{z}/{x}/{y}.webp",
    areas: [{id: "zermatt", diffScore: 0.4, layers: [{style: "bbbike", status: "NOT_COVERED"}, {style: "opentopomap", status: "AVAILABLE"}]}],
  };
  assert.equal(data.layerStatus(manifest, "zermatt", "opentopomap"), "AVAILABLE");
  assert.equal(data.layerStatus(manifest, "zermatt", "maprando"), "PENDING");
  assert.equal(data.layerStatus(null, "zermatt", "opentopomap"), "PENDING");
  assert.equal(data.coveredCount(manifest, "zermatt", ["opentopomap", "bbbike", "maprando"]), 2);
  assert.equal(data.tileUrl(manifest, "zermatt", "opentopomap"), "https://api.terento.app/assets/previews/20261006T010000Z/zermatt/opentopomap/{z}/{x}/{y}.webp");
  assert.equal(data.tileUrl({tileUrlTemplate: "https://example.com/{area}/{style}/{z}/{x}/{y}.webp"}, "zermatt", "opentopomap"), null);

  const areas = Array.from({length: 12}, (_, index) => ({id: `a${index}`, featured: index === 0}));
  assert.deepEqual([...data.bestAreas(areas, manifest)], ["a0"]);
  const scored = {areas: areas.map((item, index) => ({id: item.id, diffScore: index / 10}))};
  const best = data.bestAreas(areas, scored);
  assert.equal(best.size, 10);
  assert.ok(best.has("a11") && !best.has("a0") && !best.has("a1"));

}

function testPages() {
  const titles = new Set();
  const metadata = JSON.parse(read(path.join(root, "site", "metadata.json")));
  for (const locale of locales) {
    const source = read(localeFile(locale, "map-styles"));
    const page = pageData(locale);
    assert.equal(page.locale, locale);
    assert.equal(page.manifestUrl, "https://api.terento.app/maps/previews/manifest.json");
    assert.equal(page.areas.length, contract.areas.length, `${locale}: every contract area is offered`);
    assert.deepEqual(page.areas.map((area) => area.id), contract.areas.map((area) => area.id));
    assert.ok(page.areas.some((area) => area.id === "dolomites-tre-cime"), `${locale}: default area exists`);
    assert.equal(page.styles.length, 5);

    const h1 = source.match(/<h1 id="map-styles-title">([^<]+)<\/h1>/);
    assert.ok(h1 && h1[1].trim() && !h1[1].trim().endsWith("."), `${locale}: H1 is present without a trailing full stop`);
    const title = source.match(/<title>([^<]+)<\/title>/)[1];
    assert.ok(title.length < 70 && !title.includes("|"), `${locale}: title fits the SEO contract`);
    titles.add(title);
    const meta = metadata.pages.find((item) => item.file === path.relative(root, localeFile(locale, "map-styles")));
    assert.ok(meta && meta.alternates === true && meta.indexable !== false, `${locale}: metadata entry is indexable`);

    assert.ok(/<a [^>]*href="[^"]*map-styles\/"[^>]*aria-current="page"/.test(source), `${locale}: navigation marks the current page`);
    for (const suffix of ["", "about", "download", "compatibility"]) {
      assert.ok(read(localeFile(locale, suffix)).includes("map-styles/\""), `${locale}/${suffix}: navigation links to Map styles`);
    }
    assert.ok(!/\sstyle="/.test(source), `${locale}: no inline style attributes under the CSP`);
    assert.ok(!/<script(?![^>]*\bsrc=)(?![^>]*type="application\/(?:json|ld\+json)")[^>]*>/.test(source), `${locale}: no inline executable scripts`);
    assert.ok(source.includes("/assets/vendor/leaflet-1.9.4/leaflet.js"), `${locale}: self-hosted Leaflet`);
    assert.ok(!/unpkg|cdnjs|jsdelivr|tile\.openstreetmap/.test(source), `${locale}: no third-party map hosts`);

    // The overlays stay small: no captions or zoom percentage, collapsed place details and view menu.
    assert.ok(!/map-styles-caption|map-styles-zoom-level|map-styles-side/.test(source), `${locale}: no caption, zoom level or Left/Right words over the map`);
    assert.match(source, /id="map-styles-place-toggle" aria-expanded="false" aria-controls="map-styles-area-meta"/, `${locale}: place details expand`);
    assert.match(source, /<p class="map-styles-place-meta" id="map-styles-area-meta" hidden>/, `${locale}: place details start collapsed`);
    assert.match(source, /id="map-styles-view-toggle" aria-expanded="false" aria-controls="map-styles-view-menu"/, `${locale}: view modes sit in a menu`);
    assert.match(source, /id="map-styles-view-menu"[^>]*hidden>/, `${locale}: view menu starts closed`);
    assert.match(source, /class="map-styles-viewer"[^>]*data-mode="split"/, `${locale}: Side by side is the default view`);
    assert.match(source, /data-mode="split" aria-pressed="true"/, `${locale}: Side by side is marked current`);

    const cards = homeCards(locale);
    assert.ok(cards.length >= 4, `${locale}: home provider cards found`);
    const about = [...source.matchAll(/<article class="map-styles-about-card" data-style-card="([^"]+)">([\s\S]*?)<\/article>/g)];
    assert.equal(about.length, 5, `${locale}: five style descriptions`);
    for (const [, styleId, body] of about) {
      const name = decode(body.match(/<h3>([^<]+)/)[1].trim());
      const summary = decode(body.match(/<p class="map-styles-about-summary">([^<]+)<\/p>/)[1]);
      const benefits = [...body.matchAll(/<li>([^<]+)<\/li>/g)].map((item) => decode(item[1]));
      const card = cards.find((item) => item.name === name);
      assert.ok(card, `${locale}/${styleId}: style matches a home provider card`);
      assert.equal(summary, card.summary, `${locale}/${styleId}: summary matches the home page`);
      assert.deepEqual(benefits, card.benefits.slice(0, benefits.length), `${locale}/${styleId}: benefits match the home page`);
    }
  }
  assert.equal(titles.size, locales.length);
}

// A shared Side by side link must not sync the second map before the first has a view.
function testController() {
  const controller = read(path.join(root, "site", "map-styles", "map-styles.js"));
  const syncs = controller.split("\n").filter((line) => line.includes("mapB.setView(mapA.getCenter()"));
  assert.ok(syncs.length >= 1, "Side by side keeps both maps in sync");
  syncs.forEach((line) => assert.match(line, /\bframed\b/, "Side by side sync waits for the first view"));
  // A page left open across a new preview release must move to it, not show removed tiles.
  assert.match(controller, /\.on\("tileerror", refreshRelease\)/, "failed tiles recheck the release");
  assert.match(controller, /fetchJson\(data\.manifestUrl, "no-cache"\)/, "the recheck bypasses the browser cache");
  assert.match(controller, /visibilitychange/, "returning to the tab rechecks the release");
  // The view stays inside the drawn area: no padding beyond it, 100% is the minimum zoom.
  assert.match(controller, /map\.setMaxBounds\(bounds\);/);
  assert.match(controller, /getBoundsZoom\(boundsOf\(current\), true\)/);
  assert.match(controller, /map\.setMinZoom\(baseZoom\)/);
  assert.doesNotMatch(controller, /bounds\.pad\(/);
  // Side by side is the default on every screen; a shared link still chooses its own view.
  assert.match(controller, /mode: fromHash\.mode \|\| "split"/);
  assert.doesNotMatch(controller, /max-width/, "narrow screens do not force another view");
}

testHelpers();
testPages();
testController();
console.log("Map styles page tests passed for all six locales.");
