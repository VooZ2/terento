"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const locales = new Map([
  ["en", {
    file: path.join(root, "site", "index.html"),
    status: "Beta available · Compatibility is confirmed model by model.",
    scope: "See compatibility",
    download: "Download the beta",
  }],
  ["de", {
    file: path.join(root, "site", "de", "index.html"),
    status: "Beta verfügbar · Die Kompatibilität wird für jedes Modell einzeln bestätigt.",
    scope: "Kompatibilität ansehen",
    download: "Beta herunterladen",
  }],
  ["fr", {
    file: path.join(root, "site", "fr", "index.html"),
    status: "Bêta disponible · La compatibilité est confirmée modèle par modèle.",
    scope: "Voir la compatibilité",
    download: "Télécharger la bêta",
  }],
  ["pl", {
    file: path.join(root, "site", "pl", "index.html"),
    status: "Beta jest dostępna · Kompatybilność jest potwierdzana dla każdego modelu osobno.",
    scope: "Zobacz kompatybilność",
    download: "Pobierz wersję beta",
  }],
  ["cs", {
    file: path.join(root, "site", "cs", "index.html"),
    status: "Beta je dostupná · Kompatibilita se potvrzuje pro každý model zvlášť.",
    scope: "Zobrazit kompatibilitu",
    download: "Stáhnout betu",
  }],
  ["it", {
    file: path.join(root, "site", "it", "index.html"),
    status: "Beta disponibile · La compatibilità viene confermata modello per modello.",
    scope: "Vedi la compatibilità",
    download: "Scarica la beta",
  }],
]);

const pageFor = (locale) => fs.readFileSync(locales.get(locale).file, "utf8");
const classTokens = (classValue) => new Set(classValue.trim().split(/\s+/));
const anchorFor = (page, className) => {
  const escapedClass = className.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = page.match(new RegExp(
    `<a class="([^"]*\\b${escapedClass}\\b[^"]*)" href="[^"]+">([^<]+)<span aria-hidden="true">([^<]+)</span></a>`
  ));
  assert.ok(match, `missing ${className} CTA`);
  return { classes: classTokens(match[1]), label: match[2].trim(), arrow: match[3] };
};

for (const [locale, expected] of locales) {
  const page = pageFor(locale);
  assert.match(page, /<link rel="stylesheet" href="\/styles\.css\?v=20260829-faq-consolidation">/, `${locale}: Home stylesheet cache bust`);
  const status = page.match(/<p class="hero-status">([^<]+)<\/p>/);
  assert.ok(status, `${locale}: missing hero status`);
  assert.equal(status[1], expected.status, `${locale}: hero status copy`);

  const scope = anchorFor(page, "scope-link");
  const download = anchorFor(page, "text-link");
  assert.ok(scope.classes.has("text-link"), `${locale}: scope CTA must use shared text-link class`);
  assert.ok(scope.classes.has("scope-link"), `${locale}: scope CTA must retain section spacing modifier`);
  assert.equal(scope.label, expected.scope, `${locale}: scope CTA label`);
  assert.equal(scope.arrow, "→", `${locale}: scope CTA arrow`);
  assert.equal(download.label, expected.download, `${locale}: download CTA label`);
  assert.equal(download.arrow, "↘", `${locale}: download CTA arrow`);
  assert.equal(
    (page.match(/class="(?:text-link|text-link scope-link)"/g) || []).length,
    2,
    `${locale}: expected only the two Home text-link CTAs`
  );
}

const englishHome = pageFor("en");
assert.match(englishHome, /<p class="hero-lede">A native macOS app for installing and managing third-party maps on Garmin smartwatches\.<\/p>/);
assert.doesNotMatch(englishHome, /<p class="hero-lede">A native macOS app for installing and managing Freizeitkarte maps on Garmin smartwatches\.<\/p>/);
assert.match(englishHome, /<meta name="description" content="Free, open-source macOS app for installing and managing third-party maps on Garmin smartwatches\. Apple Silicon required; compatibility is confirmed model by model\.">/);
assert.match(englishHome, /Beta available · Compatibility is confirmed model by model\./);
assert.doesNotMatch(englishHome, /Compatibility varies by Garmin model\./);

const styles = fs.readFileSync(path.join(root, "site", "styles.css"), "utf8");
const sharedTextLink = [...styles.matchAll(/\.text-link\s*\{([^}]*)\}/g)]
  .find((match) => /display:\s*inline-flex/.test(match[1]));
const scopeModifier = styles.match(/\n\.scope-link\s*\{([^}]*)\}/s);
assert.ok(sharedTextLink, "missing shared .text-link style block");
assert.ok(scopeModifier, "missing .scope-link spacing modifier");
for (const declaration of [
  "display: inline-flex",
  "align-items: center",
  "gap: 8px",
  "color: var(--link-text)",
  "font-size: 15px",
  "font-weight: 600",
]) {
  assert.match(sharedTextLink[1], new RegExp(declaration.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
}
assert.match(styles, /\.primary-nav a,\s*\.footer-nav a,\s*\.text-link\s*\{[^}]*text-decoration: none/s);
assert.match(styles, /\.text-link:hover\s*\{[^}]*color: var\(--link-text-hover\)/s);
assert.match(styles, /a:focus-visible,\s*button:focus-visible,\s*summary:focus-visible\s*\{[^}]*outline: 3px solid var\(--focus-ring\)/s);
assert.doesNotMatch(scopeModifier[1], /display|align-items|gap|color|font-size|font-weight|text-decoration/);

console.log("Home copy, localized status, shared CTA, and CTA interaction-contract tests passed.");
