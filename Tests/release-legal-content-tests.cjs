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

for (const locale of locales) {
  for (const page of ["LEGAL", "PRIVACY"]) {
    const source = read(`legal/web/${page}-PAGE-${locale.toUpperCase()}.md`);
    assert.match(source, /OpenTopoMap/);
    assert.match(source, page === "PRIVACY" ? /privacy@terento.app/ : /hello@terento.app/);
    assert.ok(!source.includes("ANALYTICS_COPY"));
  }
}
assert.ok(!fs.existsSync(path.join(root, "legal/web/LEGAL-PAGE-LT.md")));
assert.ok(!fs.existsSync(path.join(root, "legal/web/PRIVACY-PAGE-LT.md")));
require("node:child_process").execFileSync("python3", ["scripts/build-legal-pages.py", "--check"], {cwd: root, stdio: "inherit"});
console.log("Legal/Privacy source and locale contracts passed.");
