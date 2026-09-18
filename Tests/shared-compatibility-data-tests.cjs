"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");
const data = require("../site/compatibility/compatibility-data.js");
const locales = require("../site/compatibility/compatibility-locales.js");

assert.equal(data.publicModelName("fēnix 8 · 47 mm AMOLED"), "fēnix 8");
assert.equal(data.publicModelName("Forerunner 955 · Standard"), "Forerunner 955");
assert.equal(data.exactVariantLabel({ model: "fēnix 8 · 51 mm, AMOLED", variant: "51mm", caseSizeMm: 51 }), "51 mm, AMOLED");
assert.equal(data.successfulInstallLabel(1), "1 successful install");
assert.equal(data.successfulInstallLabel(5), "5 successful installs");

for (const language of ["en", "de", "fr", "pl", "cs", "it"]) {
  const copy = locales.getLocale(language);
  assert.ok(copy.metaTitle && copy.metaDescription && copy.hero, `${language}: localized SEO copy`);
  assert.match(copy.missing, /model|Modell|modèle|modelu|model|modello/i, `${language}: missing-model guidance`);
  assert.match(copy.evidenceNote, /Garmin/i, `${language}: evidence disclaimer`);
  assert.equal(copy.statuses, undefined, `${language}: public status badges removed`);
  assert.equal(copy.successfulInstallLabel(2).includes("2"), true, `${language}: install count`);

  const prefix = language === "en" ? "" : `${language}/`;
  const page = read(`site/${prefix}compatibility/index.html`);
  const snapshotMatch = page.match(/<script type="application\/json" id="compatibility-snapshot">([\s\S]*?)<\/script>/);
  assert.ok(snapshotMatch, `${language}: embedded snapshot`);
  const snapshot = JSON.parse(snapshotMatch[1]);
  assert.equal(snapshot.models.length, 17, `${language}: public successful model count`);
  assert.ok(snapshot.models.every(model => model.successfulInstallations >= 1), `${language}: no zero-success rows`);
  assert.ok(snapshot.models.some(model => model.model === "fēnix 8 · 47 mm, AMOLED"), `${language}: current model row`);
  assert.match(page, /class="watch-card"/, `${language}: server-rendered cards`);
  assert.match(page, /data-summary="models">17<\/strong>/, `${language}: server-rendered summary`);
  assert.match(page, /data-summary="successes">63<\/strong>\s+(?:successful installs|erfolgreiche Installationen|installations réussies|udane instalacje|úspěšných instalací|installazioni riuscite)/, `${language}: server-rendered total`);
  assert.match(page, /Not seeing your model|Wenn dein Modell|L’absence de votre modèle|Brak Twojego modelu|Pokud zde svůj model|Se il tuo modello/, `${language}: visible missing-model guidance`);
  assert.doesNotMatch(page, /<option value="VERIFIED"|<option value="SUPPORTED"|<option value="TESTED"|<option value="TESTING"/, `${language}: no public status filter`);
  assert.doesNotMatch(page, /class="compatibility-status|status badge|models tested|modelle getestet/i, `${language}: no public status presentation`);
  assert.match(page, /successful-install-filter/, `${language}: successful-install filter`);
  assert.match(page, /1–2/, `${language}: range filters`);
  assert.match(page, /5\+/, `${language}: 5+ range filter`);
  assert.match(page, /data-umami-event-location="compatibility-community-testing"/, `${language}: CTA analytics`);
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
