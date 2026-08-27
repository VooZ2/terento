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
  resultCountLabel,
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
assert.equal(
  exactVariantLabel({ model: "fēnix 8 Pro · 51 mm, AMOLED", variant: "51mm", caseSizeMm: 51 }),
  "51 mm, AMOLED"
);
assert.equal(publicModelName("fēnix 8 · 47 mm AMOLED"), "fēnix 8");
assert.equal(publicModelName("fēnix 8 Pro · 51 mm, AMOLED"), "fēnix 8 Pro");
assert.equal(successfulInstallLabel(1), "1 successful install");
assert.equal(successfulInstallLabel(5), "5 successful installs");
assert.equal(resultCountLabel(2, 2), "");
assert.equal(resultCountLabel(1, 2), "1 of 2 Garmin models");

const compatibilitySource = fs.readFileSync(
  path.join(__dirname, "..", "site", "compatibility", "compatibility.js"),
  "utf8"
);
const compatibilityPage = fs.readFileSync(
  path.join(__dirname, "..", "site", "compatibility", "index.html"),
  "utf8"
);
const compatibilityStyles = fs.readFileSync(
  path.join(__dirname, "..", "site", "styles.css"),
  "utf8"
);
assert.match(compatibilitySource, /\/compatibility\/public\/models\.json/);
assert.match(compatibilitySource, /generic-garmin-watch\.png/);
assert.doesNotMatch(compatibilitySource, /watch-image-placeholder/);
assert.doesNotMatch(compatibilitySource, /\/devices\/catalog\.json/);
assert.match(compatibilityPage, /<h1 id="compatibility-title">Garmin compatibility<\/h1>/);
assert.match(compatibilityPage, />Garmin models tested with Terento</);
assert.match(compatibilityPage, /models tested/);
assert.match(compatibilityPage, /More models ready for testing/);
assert.match(compatibilityPage, /Terento can work with more Garmin models than are listed below\. This list grows as users share successful installation results\./);
assert.doesNotMatch(compatibilityPage, /Compatible Garmin models|models with evidence|Compatibility evidence|Last tested/i);
assert.match(compatibilitySource, /Latest installation/);
assert.doesNotMatch(compatibilitySource, /Last tested|Latest evidence/);
assert.match(compatibilitySource, /elements\.results\.hidden = filtered\.length === state\.rows\.length/);
assert.match(compatibilityStyles, /aspect-ratio: 2;/);
assert.match(compatibilityStyles, /\.watch-card-image img \{[\s\S]*?width: 160px;[\s\S]*?height: 160px;/);
assert.match(compatibilityStyles, /@media \(max-width: 1100px\)/);
assert.match(compatibilityStyles, /@media \(max-width: 1100px\)[\s\S]*?\.watch-card-image \{[\s\S]*?height: 220px;/);
assert.match(compatibilityStyles, /grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/);
assert.match(compatibilityStyles, /@media \(max-width: 640px\)[\s\S]*?grid-template-columns: 1fr/);
assert.match(compatibilityStyles, /@media \(max-width: 640px\)[\s\S]*?aspect-ratio: 1\.95;/);
assert.match(compatibilityStyles, /@media \(max-width: 640px\)[\s\S]*?\.watch-card-image img \{[\s\S]*?width: 130px;[\s\S]*?height: 130px;/);
assert.doesNotMatch(compatibilityStyles, /@media \(min-width: 375px\) and \(max-width: 640px\)/);

console.log("Compatibility family/data/API-source tests passed.");
