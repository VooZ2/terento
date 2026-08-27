"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {
  canonicalFamilyKey,
  familyOptions,
  filterByFamily,
  exactVariantLabel,
  publicModelName,
  successfulInstallLabel,
} = require("../site/compatibility/compatibility-data.js");
const compatibilityLocaleApi = require("../site/compatibility/compatibility-locales.js");

const row = (family, familyName, variant, report = 1) => ({
  family,
  familyName,
  model: "fēnix 8",
  variants: [variant],
  report,
});

const twoVariants = [
  row("fenix", "fēnix", "47 mm, AMOLED"),
  row("fenix", "fēnix", "51 mm, AMOLED"),
];
assert.deepEqual(familyOptions(twoVariants), [["fenix", "fēnix"]]);

const repeatedReports = [
  ...twoVariants,
  row(" FENIX ", "fēnix", "47 mm, AMOLED", 2),
  row("fe\u0301nix", "fénix", "51 mm, AMOLED", 2),
];
assert.deepEqual(familyOptions(repeatedReports), [["fenix", "fēnix"]]);

const mixedFamilies = [
  ...twoVariants,
  { family: "forerunner", familyName: "Forerunner", model: "Forerunner 970", variants: ["47 mm"] },
];
assert.deepEqual(familyOptions(mixedFamilies), [["fenix", "fēnix"], ["forerunner", "Forerunner"]]);

const selected = filterByFamily(mixedFamilies, canonicalFamilyKey("fēnix"));
assert.equal(selected.length, 2);
assert.deepEqual(selected.map((item) => item.variants[0]), ["47 mm, AMOLED", "51 mm, AMOLED"]);
assert.notStrictEqual(selected[0], selected[1]);

assert.equal(
  exactVariantLabel({ variant: "AMOLED", caseSizeMm: 47, displayType: "AMOLED" }),
  "47 mm, AMOLED"
);
assert.equal(
  exactVariantLabel({ variant: "AMOLED", caseSizeMm: 51, displayType: "AMOLED" }),
  "51 mm, AMOLED"
);
assert.equal(exactVariantLabel({ variant: "51 mm, AMOLED" }), "51 mm, AMOLED");
assert.equal(
  exactVariantLabel({ model: "fēnix 8 Pro · 51 mm, AMOLED", variant: "51mm", caseSizeMm: 51 }),
  "51 mm, AMOLED"
);
assert.equal(exactVariantLabel({ variant: "47 mm AMOLED" }), "47 mm, AMOLED");
assert.equal(publicModelName("fēnix 8 · 47 mm AMOLED"), "fēnix 8");
assert.equal(publicModelName("fēnix 8 Pro · 51 mm, AMOLED"), "fēnix 8 Pro");
assert.equal(successfulInstallLabel(1), "1 successful install");
assert.equal(successfulInstallLabel(5), "5 successful installs");
assert.deepEqual(compatibilityLocaleApi.statusCodes, ["VERIFIED", "SUPPORTED", "TESTED", "TESTING"]);
for (const locale of ["en", "de", "fr", "pl", "cs", "it"]) {
  const copy = compatibilityLocaleApi.getLocale(locale);
  assert.ok(copy.metaTitle && copy.metaDescription && copy.hero, `${locale}: compatibility metadata and hero copy`);
  assert.equal(Object.keys(copy.statuses).length, 4, `${locale}: all status translations`);
  assert.equal(copy.successfulInstallLabel(1).includes("1"), true, `${locale}: localized install count`);
}

const compatibilitySource = fs.readFileSync(
  path.join(__dirname, "..", "site", "compatibility", "compatibility.js"),
  "utf8"
);
const compatibilityPage = fs.readFileSync(
  path.join(__dirname, "..", "site", "compatibility", "index.html"),
  "utf8"
);
const homePage = fs.readFileSync(
  path.join(__dirname, "..", "site", "index.html"),
  "utf8"
);
const localizedHomePages = new Map([
  ["de", fs.readFileSync(path.join(__dirname, "..", "site", "de", "index.html"), "utf8")],
  ["fr", fs.readFileSync(path.join(__dirname, "..", "site", "fr", "index.html"), "utf8")],
  ["pl", fs.readFileSync(path.join(__dirname, "..", "site", "pl", "index.html"), "utf8")],
  ["cs", fs.readFileSync(path.join(__dirname, "..", "site", "cs", "index.html"), "utf8")],
  ["it", fs.readFileSync(path.join(__dirname, "..", "site", "it", "index.html"), "utf8")],
]);
const siteStyles = fs.readFileSync(
  path.join(__dirname, "..", "site", "styles.css"),
  "utf8"
);
assert.match(compatibilitySource, /\/compatibility\/public\/models\.json/);
assert.match(compatibilitySource, /generic-garmin-watch\.png/);
assert.doesNotMatch(compatibilitySource, /watch-image-placeholder/);
assert.doesNotMatch(compatibilitySource, /\/devices\/catalog\.json/);
assert.match(compatibilitySource, /publicModelName\(row\.model\)/);
assert.match(compatibilitySource, /aria-label="\$\{escapeHtml\(accessibleName\)\}"/);
assert.doesNotMatch(compatibilitySource, /Last tested/);
assert.match(compatibilitySource, /locale\.card\.latest/);
const compatibilityLocalesSource = fs.readFileSync(
  path.join(__dirname, "..", "site", "compatibility", "compatibility-locales.js"),
  "utf8"
);
assert.match(compatibilityLocalesSource, /Terento can install third-party maps on this model/);
assert.match(compatibilityLocalesSource, /3–4 successful installations have confirmed compatibility/);
assert.match(compatibilityLocalesSource, /5 or more successful installations have confirmed compatibility/);
assert.match(compatibilitySource, /statusCodes = \["VERIFIED", "SUPPORTED", "TESTED", "TESTING"\]/);
assert.match(compatibilitySource, /watch-card-model-row/);
assert.match(compatibilitySource, /watch-variant/);
assert.match(compatibilitySource, /successfulInstallLabel\(row\.successful\)/);
assert.equal((compatibilityPage.match(/<h1\b/gi) || []).length, 1);
assert.match(compatibilityPage, /<h1 id="compatibility-title">Garmin compatibility<\/h1>/);
assert.match(compatibilityPage, /See real Terento installation results for third-party maps by exact Garmin watch model and variant\. Compatibility grows as more successful installations are shared by users\./);
assert.doesNotMatch(compatibilityPage, /Garmin watch compatibility with Terento/);
assert.doesNotMatch(compatibilityPage, /Garmin models with evidence/);
assert.doesNotMatch(compatibilityPage, /class="section-heading compatibility-heading"/);
assert.doesNotMatch(compatibilityPage, /aria-labelledby="directory-title"/);
assert.match(compatibilityPage, /data-summary-model-label>models with evidence/);
assert.match(compatibilityPage, /More models ready for testing/);
assert.match(compatibilityPage, /Public compatibility is based on real installation evidence from exact Garmin models and variants\. Each successful installation shared by users helps us confirm compatibility with greater confidence\./);
assert.match(compatibilityPage, /Garmin Watch Compatibility — Terento/);
assert.match(compatibilityPage, /data-umami-event="download-cta-click"/);
assert.match(compatibilityPage, /data-umami-event-location="compatibility-community-testing"/);
assert.doesNotMatch(compatibilityPage, /\b3 models tested\b/);
assert.ok(compatibilityPage.indexOf('id="compatibility-summary"') < compatibilityPage.indexOf('class="compatibility-how"'));
assert.ok(compatibilityPage.indexOf('class="compatibility-how"') < compatibilityPage.indexOf('id="compatibility-filters"'));
assert.ok(compatibilityPage.indexOf('id="compatibility-filters"') < compatibilityPage.indexOf('id="watch-grid"'));
assert.doesNotMatch(siteStyles, /\.compatibility-heading\b/);
assert.match(siteStyles, /\.compatibility-directory\s*\{[^}]*padding:\s*clamp\(28px, 4vw, 48px\)/s);
assert.match(siteStyles, /\.compatibility-summary-item\s*\{[^}]*white-space:\s*nowrap/s);
assert.match(siteStyles, /\.watch-card-model-row\s*\{[^}]*gap:\s*12px/s);
assert.match(siteStyles, /\.watch-card-model-row h3\s*\{[^}]*min-width:\s*0/s);

assert.match(homePage, /<h2 id="scope-title">Compatibility grows with every shared installation\.<\/h2>/);
assert.match(homePage, /Terento is designed for Garmin smartwatches with map support\. Public compatibility for third-party map installation is confirmed model by model from real results shared by users\./);
assert.match(homePage, /Terento is designed for Garmin smartwatches with map support\. Public compatibility for third-party map installation is confirmed by exact model and variant using real results shared by users\. See the <a href="\/compatibility\/">Compatibility page<\/a> for the current evidence\./);
assert.doesNotMatch(homePage, /Selected scope, not every Garmin\.|small, evidence-led set/);

const localizedScopeHeadings = {
  de: "Kompatibilität wächst mit jeder geteilten Installation.",
  fr: "La compatibilité progresse à chaque installation partagée.",
  pl: "Kompatybilność rośnie z każdą udostępnioną instalacją.",
  cs: "Kompatibilita roste s každou sdílenou instalací.",
  it: "La compatibilità cresce con ogni installazione condivisa.",
};
for (const [locale, page] of localizedHomePages) {
  assert.match(page, new RegExp(`<h2 id="scope-title">${localizedScopeHeadings[locale].replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}<\\/h2>`));
  assert.match(page, /localized-content\.js/);
  assert.match(page, /public|öffentliche|publique|publiczna|veřejná|pubblica/i);
  assert.doesNotMatch(page, /small, evidence-led|kleine, evidenzbasierte|petit ensemble|niewielkiej, opartej|malou, důkazy|piccolo insieme/);
}

console.log("Compatibility family/data/API-source tests passed.");
