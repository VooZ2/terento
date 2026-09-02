"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), "utf8");
const locales = ["en", "de", "fr", "pl", "cs", "it"];

for (const locale of locales) {
  const legal = read("site/legal/index.html");
  const privacy = read("site/privacy/index.html");
  const legalLocaleBlock = new RegExp(`legal-version-${locale}[\\s\\S]*?OpenTopoMap`);
  const privacyLocaleBlock = new RegExp(`legal-version-${locale}[\\s\\S]*?OpenTopoMap`);
  assert.match(legal, legalLocaleBlock, `${locale}: legal page names OpenTopoMap`);
  assert.match(legal, /garmin\.opentopomap\.org/, `${locale}: legal page links OpenTopoMap`);
  assert.match(privacy, privacyLocaleBlock, `${locale}: privacy page names OpenTopoMap`);
}

assert.match(read("legal/web/LEGAL-PAGE-EN.md"), /OpenTopoMap/);
assert.match(read("legal/web/LEGAL-PAGE-LT.md"), /OpenTopoMap/);
assert.match(read("legal/web/PRIVACY-PAGE-EN.md"), /OpenTopoMap/);
assert.match(read("legal/web/PRIVACY-PAGE-LT.md"), /OpenTopoMap/);

console.log("Legal and privacy provider-content tests passed for all six locales.");
