"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {
  canonicalFamilyKey,
  familyOptions,
  filterByFamily,
  exactVariantLabel,
} = require("../site/compatibility/compatibility-data.js");

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

const compatibilitySource = fs.readFileSync(
  path.join(__dirname, "..", "site", "compatibility", "compatibility.js"),
  "utf8"
);
const compatibilityPage = fs.readFileSync(
  path.join(__dirname, "..", "site", "compatibility", "index.html"),
  "utf8"
);
const siteStyles = fs.readFileSync(
  path.join(__dirname, "..", "site", "styles.css"),
  "utf8"
);
assert.match(compatibilitySource, /\/compatibility\/public\/models\.json/);
assert.match(compatibilitySource, /generic-garmin-watch\.png/);
assert.doesNotMatch(compatibilitySource, /watch-image-placeholder/);
assert.doesNotMatch(compatibilitySource, /\/devices\/catalog\.json/);
assert.equal((compatibilityPage.match(/<h1\b/gi) || []).length, 1);
assert.match(compatibilityPage, /<h1 id="compatibility-title">Garmin compatibility<\/h1>/);
assert.match(compatibilityPage, /See which Garmin watches have real Terento installation results\. Compatibility is tracked by exact model and updated as more installations are shared\./);
assert.doesNotMatch(compatibilityPage, /Garmin watch compatibility with Terento/);
assert.doesNotMatch(compatibilityPage, /Garmin models with evidence/);
assert.doesNotMatch(compatibilityPage, /class="section-heading compatibility-heading"/);
assert.doesNotMatch(compatibilityPage, /aria-labelledby="directory-title"/);
assert.match(compatibilityPage, /data-summary-model-label>models with evidence/);
assert.match(compatibilityPage, /More models ready for testing/);
assert.doesNotMatch(compatibilityPage, /\b3 models tested\b/);
assert.ok(compatibilityPage.indexOf('id="compatibility-summary"') < compatibilityPage.indexOf('class="compatibility-how"'));
assert.ok(compatibilityPage.indexOf('class="compatibility-how"') < compatibilityPage.indexOf('id="compatibility-filters"'));
assert.ok(compatibilityPage.indexOf('id="compatibility-filters"') < compatibilityPage.indexOf('id="watch-grid"'));
assert.doesNotMatch(siteStyles, /\.compatibility-heading\b/);
assert.match(siteStyles, /\.compatibility-directory\s*\{[^}]*padding:\s*clamp\(28px, 4vw, 48px\)/s);
assert.match(siteStyles, /\.compatibility-summary-item\s*\{[^}]*white-space:\s*nowrap/s);

console.log("Compatibility family/data/API-source tests passed.");
