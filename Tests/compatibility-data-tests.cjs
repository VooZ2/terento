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
assert.match(compatibilitySource, /\/compatibility\/public\/models\.json/);
assert.match(compatibilitySource, /generic-garmin-watch\.png/);
assert.doesNotMatch(compatibilitySource, /watch-image-placeholder/);
assert.doesNotMatch(compatibilitySource, /\/devices\/catalog\.json/);

console.log("Compatibility family/data/API-source tests passed.");
