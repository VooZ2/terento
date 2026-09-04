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
    heroCompatibility: "Check compatibility",
    download: "Download the beta",
  }],
  ["de", {
    file: path.join(root, "site", "de", "index.html"),
    status: "Beta verfügbar · Die Kompatibilität wird für jedes Modell einzeln bestätigt.",
    scope: "Kompatibilität ansehen",
    heroCompatibility: "Kompatibilität prüfen",
    download: "Beta herunterladen",
  }],
  ["fr", {
    file: path.join(root, "site", "fr", "index.html"),
    status: "Bêta disponible · La compatibilité est confirmée modèle par modèle.",
    scope: "Voir la compatibilité",
    heroCompatibility: "Vérifier la compatibilité",
    download: "Télécharger la bêta",
  }],
  ["pl", {
    file: path.join(root, "site", "pl", "index.html"),
    status: "Beta jest dostępna · Kompatybilność jest potwierdzana dla każdego modelu osobno.",
    scope: "Zobacz kompatybilność",
    heroCompatibility: "Sprawdź kompatybilność",
    download: "Pobierz wersję beta",
  }],
  ["cs", {
    file: path.join(root, "site", "cs", "index.html"),
    status: "Beta je dostupná · Kompatibilita se potvrzuje pro každý model zvlášť.",
    scope: "Zobrazit kompatibilitu",
    heroCompatibility: "Ověřit kompatibilitu",
    download: "Stáhnout betu",
  }],
  ["it", {
    file: path.join(root, "site", "it", "index.html"),
    status: "Beta disponibile · La compatibilità viene confermata modello per modello.",
    scope: "Vedi la compatibilità",
    heroCompatibility: "Verifica la compatibilità",
    download: "Scarica la beta",
  }],
]);

const pageFor = (locale) => fs.readFileSync(locales.get(locale).file, "utf8");
const classTokens = (classValue) => new Set(classValue.trim().split(/\s+/));
const anchorFor = (page, className) => {
  const escapedClass = className.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = page.match(new RegExp(
    `<a class="([^"]*\\b${escapedClass}\\b[^"]*)" href="([^"]+)"([^>]*)>([^<]+)<span aria-hidden="true">([^<]+)</span></a>`
  ));
  assert.ok(match, `missing ${className} CTA`);
  return { classes: classTokens(match[1]), href: match[2], attributes: match[3], label: match[4].trim(), arrow: match[5] };
};

for (const [locale, expected] of locales) {
  const page = pageFor(locale);
  assert.match(page, /<link rel="stylesheet" href="\/styles\.css\?v=20260904-language-selector">/, `${locale}: Home stylesheet cache bust`);
  assert.match(page, /your-garmin-1600\.png\?v=20260902-your-garmin/, `${locale}: updated Garmin screenshot cache bust`);
  const status = page.match(/<p class="hero-status">([^<]+)<\/p>/);
  assert.ok(status, `${locale}: missing hero status`);
  assert.equal(status[1], expected.status, `${locale}: hero status copy`);

  const scope = anchorFor(page, "scope-link");
  const download = anchorFor(page, "hero-download-action");
  const heroCompatibility = anchorFor(page, "hero-compatibility-link");
  assert.ok(scope.classes.has("text-link"), `${locale}: scope CTA must use shared text-link class`);
  assert.ok(scope.classes.has("scope-link"), `${locale}: scope CTA must retain section spacing modifier`);
  assert.equal(scope.label, expected.scope, `${locale}: scope CTA label`);
  assert.equal(scope.arrow, "→", `${locale}: scope CTA arrow`);
  assert.equal(scope.href, locale === "en" ? "/compatibility/" : `/${locale}/compatibility/`, `${locale}: static localized Compatibility href`);
  assert.ok(download.classes.has("download-action"), `${locale}: hero Download CTA uses the solid action style`);
  assert.equal(download.label, expected.download, `${locale}: download CTA label`);
  assert.equal(download.arrow, "→", `${locale}: download CTA arrow`);
  assert.ok(heroCompatibility.classes.has("text-link"), `${locale}: Hero Compatibility CTA uses the shared text-link style`);
  assert.ok(heroCompatibility.classes.has("hero-compatibility-link"), `${locale}: Hero Compatibility CTA uses its layout modifier`);
  assert.equal(heroCompatibility.label, expected.heroCompatibility, `${locale}: Hero Compatibility CTA label`);
  assert.equal(heroCompatibility.arrow, "→", `${locale}: Hero Compatibility CTA arrow`);
  assert.equal(heroCompatibility.href, locale === "en" ? "/compatibility/" : `/${locale}/compatibility/`, `${locale}: Hero Compatibility CTA href`);
  assert.match(heroCompatibility.attributes, /data-umami-event="compatibility-link-click"/);
  assert.match(heroCompatibility.attributes, /data-umami-event-location="home-hero"/);
  assert.match(page, /<div class="hero-actions"><a class="download-action hero-download-action"[\s\S]*?<a class="text-link hero-compatibility-link"/);
  assert.equal(
    (page.match(/<a class="text-link scope-link" href="[^"]+">/g) || []).length,
    1,
    `${locale}: expected one Home text-link CTA`
  );
  assert.doesNotMatch(page, /<p class="hero-lede">[^<]*Freizeitkarte/i, `${locale}: hero copy is provider-neutral`);
  assert.doesNotMatch(page, /back up|backup|sauvegarder|zálohovat|wykonać kopię|eseguire il backup/i, `${locale}: no backup marketing copy`);
  const scopeSection = page.match(/<section class="scope-section"[\s\S]*?<\/section>/);
  assert.ok(scopeSection, `${locale}: Compatibility gateway`);
  assert.doesNotMatch(scopeSection[0], /class="scope-list"|class="scope-item"|Map providers|Kartenanbieter|Fournisseurs de cartes|Dostawcy map|Poskytovatelé map|Provider di mappe/i, `${locale}: Compatibility gateway contains only explanation and CTA`);
  assert.doesNotMatch(page, /beta[ .]?8|bêta 8/i, `${locale}: no stale beta.8 copy`);
}

const englishHome = pageFor("en");
assert.match(englishHome, /<p class="hero-lede">A native macOS app for installing and managing third-party maps on Garmin smartwatches\.<\/p>/);
assert.doesNotMatch(englishHome, /<p class="hero-lede">A native macOS app for installing and managing Freizeitkarte maps on Garmin smartwatches\.<\/p>/);
assert.match(englishHome, /<meta name="description" content="Install and manage third-party maps on supported Garmin smartwatches with Terento, a free macOS app for Apple Silicon\.">/);
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
const heroAction = styles.match(/\.hero-download-action\s*\{([^}]*)\}/s);
assert.ok(heroAction, "missing Hero Download CTA sizing block");
assert.match(heroAction[1], /min-height:\s*52px/);
assert.match(heroAction[1], /padding:\s*12px 22px/);
assert.match(heroAction[1], /font-size:\s*15px/);
const heroActions = styles.match(/\.hero-actions\s*\{([^}]*)\}/s);
assert.ok(heroActions, "missing Hero action stack block");
assert.match(heroActions[1], /display:\s*flex/);
assert.match(heroActions[1], /flex-direction:\s*column/);
assert.match(heroActions[1], /align-items:\s*flex-start/);
assert.match(heroActions[1], /gap:\s*14px/);
const heroCompatibilityLink = styles.match(/\.hero-compatibility-link\s*\{([^}]*)\}/s);
assert.ok(heroCompatibilityLink, "missing Hero Compatibility CTA touch target block");
assert.match(heroCompatibilityLink[1], /min-height:\s*44px/);
assert.match(styles, /a:focus-visible,\s*button:focus-visible,\s*summary:focus-visible\s*\{[^}]*outline: 3px solid var\(--focus-ring\)/s);
assert.doesNotMatch(scopeModifier[1], /display|align-items|gap|color|font-size|font-weight|text-decoration/);
assert.match(styles, /\.experience\.section\s*\{[^}]*padding:\s*clamp\(72px, 9vw, 116px\) 0/s);
assert.match(styles, /\.product-showcase\s*\{[^}]*padding:\s*clamp\(68px, 7\.5vw, 100px\) 0/s);
const localizedContent = fs.readFileSync(path.join(root, "site", "localized-content.js"), "utf8");
assert.doesNotMatch(localizedContent, /querySelector\("\.scope-link"\).*setAttribute/s, "localized Compatibility href must not depend on JavaScript");

console.log("Home copy, localized status, shared CTA, and CTA interaction-contract tests passed.");
