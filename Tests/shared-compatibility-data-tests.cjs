"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const testRoot = path.resolve(process.env.TERENTO_COMPATIBILITY_TEST_ROOT || root);
const read = relative => fs.readFileSync(path.join(testRoot, relative), "utf8");
const data = require(path.join(testRoot, "site/compatibility/compatibility-data.js"));
const locales = require(path.join(testRoot, "site/compatibility/compatibility-locales.js"));

const languages = ["en", "de", "fr", "pl", "cs", "it"];

function embeddedSnapshot(page, language) {
  const snapshotMatch = page.match(/<script type="application\/json" id="compatibility-snapshot">([\s\S]*?)<\/script>/);
  assert.ok(snapshotMatch, `${language}: embedded snapshot`);
  return JSON.parse(snapshotMatch[1]);
}

function summaryValue(page, summary, language) {
  const match = page.match(new RegExp(`data-summary="${summary}">(\\d+)<\\/strong>`));
  assert.ok(match, `${language}: server-rendered ${summary} summary`);
  return Number(match[1]);
}

function snapshotFacts(snapshot) {
  return {
    models: snapshot.models.length,
    successes: snapshot.models.reduce((total, model) => total + model.successfulInstallations, 0),
  };
}

function assertSnapshotFacts(page, snapshot, language) {
  const facts = snapshotFacts(snapshot);
  assert.equal(summaryValue(page, "models", language), facts.models, `${language}: model summary matches snapshot`);
  assert.equal(summaryValue(page, "successes", language), facts.successes, `${language}: successful-install summary matches snapshot`);
  return facts;
}

assert.equal(data.publicModelName("fēnix 8 · 47 mm AMOLED"), "fēnix 8");
assert.equal(data.publicModelName("Forerunner 955 · Standard"), "Forerunner 955");
assert.equal(data.exactVariantLabel({ model: "fēnix 8 · 51 mm, AMOLED", variant: "51mm", caseSizeMm: 51 }), "51 mm, AMOLED");
assert.equal(data.successfulInstallLabel(1), "1 successful install");
assert.equal(data.successfulInstallLabel(5), "5 successful installs");

// Card counts: exact below 100, then rounded down to the hundred with a plus;
// a rounded value always takes the plural form.
const english = locales.getLocale("en");
assert.equal(english.successfulInstallLabel(99), "99 successful installs");
assert.equal(english.successfulInstallLabel(100), "100+ successful installs");
assert.equal(english.successfulInstallLabel(199), "100+ successful installs");
assert.equal(english.successfulInstallLabel(250), "200+ successful installs");
assert.equal(english.successfulInstallLabel(1234), "1,200+ successful installs");
assert.equal(english.cardCount(6), "6");
assert.equal(english.sources.appLabel(english.cardCount(140)), "100+ with the app");
assert.equal(english.sources.webLabel(english.cardCount(6)), "6 with the web installer");
assert.equal(locales.getLocale("de").successfulInstallLabel(1234), "1.200+ erfolgreiche Installationen");
assert.equal(locales.getLocale("fr").successfulInstallLabel(1), "1 installation réussie");
assert.equal(locales.getLocale("fr").successfulInstallLabel(100), "100+ installations réussies");
assert.equal(locales.getLocale("pl").successfulInstallLabel(100), "100+ udanych instalacji");
assert.equal(locales.getLocale("cs").successfulInstallLabel(1), "1 úspěšná instalace");
assert.equal(locales.getLocale("it").successfulInstallLabel(300), "300+ installazioni riuscite");

const localeFacts = [];
for (const language of languages) {
  const copy = locales.getLocale(language);
  assert.ok(copy.metaTitle && copy.metaDescription && copy.hero, `${language}: localized SEO copy`);
  assert.match(copy.missing, /model|Modell|modèle|modelu|model|modello/i, `${language}: missing-model guidance`);
  assert.match(copy.evidenceNote, /Garmin/i, `${language}: evidence disclaimer`);
  assert.equal(copy.statuses, undefined, `${language}: public status badges removed`);
  assert.equal(copy.successfulInstallLabel(2).includes("2"), true, `${language}: install count`);
  assert.equal(copy.sources.app, "App", `${language}: app source label`);
  assert.equal(copy.sources.web, "Web", `${language}: web source label`);
  assert.ok(copy.sources.appLabel("4").startsWith("4 ") && copy.sources.webLabel("2").startsWith("2 "), `${language}: spoken source split`);

  const prefix = language === "en" ? "" : `${language}/`;
  const page = read(`site/${prefix}compatibility/index.html`);
  const snapshot = embeddedSnapshot(page, language);
  assert.ok(Array.isArray(snapshot.models), `${language}: snapshot models`);
  assert.ok(snapshot.models.every(model => model.successfulInstallations >= 1), `${language}: no zero-success rows`);
  assert.ok(snapshot.models.some(model => model.model === "fēnix 8 · 47 mm, AMOLED"), `${language}: current model row`);
  assert.match(page, /class="watch-card"/, `${language}: server-rendered cards`);
  assert.equal((page.match(/<p class="watch-install-sources">/g) || []).length, snapshot.models.length, `${language}: every card shows the app/web split`);
  const facts = assertSnapshotFacts(page, snapshot, language);
  localeFacts.push({ language, ...facts });
  assert.match(page, new RegExp(`data-summary="successes">${facts.successes}<\\/strong>\\s+(?:successful installs|erfolgreiche Installationen|installations réussies|udane instalacje|úspěšných instalací|installazioni riuscite)`), `${language}: localized server-rendered total`);
  assert.match(page, /Not seeing your model|Wenn dein Modell|L’absence de votre modèle|Brak Twojego modelu|Pokud zde svůj model|Se il tuo modello/, `${language}: visible missing-model guidance`);
  assert.doesNotMatch(page, /<option value="VERIFIED"|<option value="SUPPORTED"|<option value="TESTED"|<option value="TESTING"/, `${language}: no public status filter`);
  assert.doesNotMatch(page, /class="compatibility-status|status badge|models tested|modelle getestet/i, `${language}: no public status presentation`);
  assert.match(page, /successful-install-filter/, `${language}: successful-install filter`);
  assert.match(page, /1–2/, `${language}: range filters`);
  assert.match(page, /5\+/, `${language}: 5+ range filter`);
  assert.match(page, /data-umami-event-location="compatibility-community-testing"/, `${language}: CTA analytics`);
}

const expectedLocaleFacts = { models: localeFacts[0].models, successes: localeFacts[0].successes };
for (const facts of localeFacts.slice(1)) {
  assert.deepEqual({ models: facts.models, successes: facts.successes }, expectedLocaleFacts, `${facts.language}: factual values match en`);
}

const compatibilitySource = read("site/compatibility/compatibility.js");
assert.match(compatibilitySource, /initializeSnapshot/);
assert.match(compatibilitySource, /public\/models\.json/);
assert.match(compatibilitySource, /filter\(\(row\) => row\.successful > 0\)/);
assert.match(compatibilitySource, /successfulRange/);
assert.doesNotMatch(compatibilitySource, /statusCodes|createStatusBadge|evidenceStatus|attemptedInstallations/);
assert.match(compatibilitySource, /preserveExistingResults/);

const home = read("site/index.html");
assert.match(home, /Garmin smartwatches with map support/);
assert.match(home, /at least one successful shared installation/);
assert.match(home, /not necessarily unsupported/);

const metadata = JSON.parse(read("site/metadata.json"));
const compatibilityMetadata = metadata.pages.filter(page => page.path.endsWith("/compatibility/"));
assert.equal(compatibilityMetadata.length, 6);
assert.ok(compatibilityMetadata.every(page => /successful|erfolgreiche|réussies|udane|úspěšné|riuscite/i.test(page.title)));

console.log("Compatibility snapshot, public semantics, localization, and raw HTML tests passed.");
