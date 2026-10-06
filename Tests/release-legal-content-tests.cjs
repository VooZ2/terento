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
// Support reports are described conditionally ("where the app offers") so the
// notice stays true before and after the app ships the in-app sender.
const supportReports = {
  en: ["## Support reports", /Where the app offers/, /12 months/, /Unit IDs/],
  de: ["## Supportberichte", /Wenn die App anbietet/, /12 Monate/, /Unit IDs/],
  fr: ["## Rapports d’assistance", /Lorsque l’application propose/, /12 mois/, /Unit IDs/],
  pl: ["## Raporty pomocy", /Gdy aplikacja oferuje/, /12 miesięcy/, /Unit IDs/],
  cs: ["## Zprávy podpoře", /Pokud aplikace nabízí/, /12 měsíců/, /Unit IDs/],
  it: ["## Rapporti di assistenza", /Quando l’app offre/, /12 mesi/, /Unit IDs/],
};
const privacyPage = read("site/privacy/index.html");
for (const locale of locales) {
  const source = read(`legal/web/PRIVACY-PAGE-${locale.toUpperCase()}.md`);
  const [heading, ...signals] = supportReports[locale];
  const sections = source.split(/\n(?=## )/);
  const section = sections.find((chunk) => chunk.startsWith(heading + "\n"));
  assert.ok(section, `${locale}: privacy notice describes support reports`);
  for (const signal of signals) assert.match(section, signal, `${locale}: support report section ${signal}`);
  const headings = sections.map((chunk) => chunk.split("\n", 1)[0]);
  assert.equal(headings.indexOf(heading), 5, `${locale}: support reports follow help and public issues`);
  assert.ok(privacyPage.includes(`<h2>${heading.slice(3)}</h2>`), `${locale}: rendered support report heading`);
}
assert.ok(!fs.existsSync(path.join(root, "legal/web/LEGAL-PAGE-LT.md")));
assert.ok(!fs.existsSync(path.join(root, "legal/web/PRIVACY-PAGE-LT.md")));
require("node:child_process").execFileSync("python3", ["scripts/build-legal-pages.py", "--check"], {cwd: root, stdio: "inherit"});
console.log("Legal/Privacy source and locale contracts passed.");
