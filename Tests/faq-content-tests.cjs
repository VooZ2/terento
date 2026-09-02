"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const locales = ["en", "de", "fr", "pl", "cs", "it"];
const guideSlug = "guides/install-garmin-maps-mac/";
const localePath = (locale, suffix = "") => locale === "en" ? `/${suffix}` : `/${locale}/${suffix}`;
const homeFile = (locale) => path.join(root, "site", locale === "en" ? "index.html" : path.join(locale, "index.html"));
const pageFile = (locale, suffix) => path.join(root, "site", locale === "en" ? suffix : path.join(locale, suffix));
const read = (file) => fs.readFileSync(file, "utf8");

function visibleText(fragment) {
  return fragment
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

function visibleFaq(source, file) {
  const section = source.match(/<section\b[^>]*\bid=["']faq["'][^>]*>([\s\S]*?)<\/section>/i);
  assert.ok(section, `${file}: Home FAQ section`);
  const entries = [...section[1].matchAll(/<details>\s*<summary>([\s\S]*?)<\/summary>\s*<p>([\s\S]*?)<\/p>\s*(?:<div class="faq-support-actions">[\s\S]*?<\/div>\s*)?<\/details>/gi)]
    .map((match) => ({ question: visibleText(match[1]), answer: visibleText(match[2]), markup: match[0] }));
  assert.equal(entries.length, 5, `${file}: exactly five FAQ entries`);
  return entries;
}

const questionSignals = [
  [/Garmin.*Terento/i, /Compatibility|Kompatibilitätsseite|Compatibilité|kompatybilności|Kompatibilita|Compatibilità/i],
  [/BaseCamp/i, /Mac/],
  [/existing|vorhand|exist|istnie|stávaj|esist/i, /Terento|map/i],
  [/maps|Karten|cartes|mapy|map|mappe|provider|fournisseur|dostawc|poskytovatel/i, /Terento|map/i],
  [/fail|fehlsch|échou|nie powied|selže|riesce/i, /GitHub|hello@terento\.app/i],
];

for (const locale of locales) {
  const home = homeFile(locale);
  const source = read(home);
  const entries = visibleFaq(source, home);
  entries.forEach((entry, index) => {
    assert.match(entry.question, questionSignals[index][0], `${home}: FAQ question ${index + 1} semantic order`);
    assert.match(entry.answer, questionSignals[index][1], `${home}: FAQ answer ${index + 1} content`);
  });
  assert.match(entries[1].answer, /map file|Kartendatei|fichier cartographique|plik mapy|mapový soubor|file cartografico/i, `${home}: BaseCamp answer mentions compatible local map import in user language`);
  assert.match(entries[2].answer, /protected|geschützt|protég|chronione|chráněné|protette/i, `${home}: safety answer protects Garmin/system maps`);
  assert.match(entries[3].question, /provider|anbieter|fournisseur|dostawc|poskytovatel/i, `${home}: provider FAQ question`);
  assert.match(entries[3].answer, /Freizeitkarte/i, `${home}: provider FAQ names Freizeitkarte`);
  assert.match(entries[3].answer, /OpenTopoMap/i, `${home}: provider FAQ names OpenTopoMap`);
  assert.doesNotMatch(entries[3].answer, /beta|bêta|version|release|wersj|verz|versi/i, `${home}: provider FAQ describes Terento without release wording`);
  assert.doesNotMatch(source, /back up|backup|sauvegarder|zálohovat|wykonać kopię|zálohovat|eseguire il backup/i, `${home}: removed backup promise`);
  assert.match(entries[0].markup, new RegExp(`href="${localePath(locale, "compatibility/")}"`), `${home}: Compatibility link`);
  assert.match(entries[1].markup, new RegExp(`href="${localePath(locale, guideSlug)}"`), `${home}: Guide link`);
  assert.match(entries[4].markup, /href="https:\/\/github\.com\/VooZ2\/terento\/issues"[^>]*target="_blank"[^>]*rel="noopener noreferrer"/);
  assert.match(entries[4].markup, /href="mailto:hello@terento\.app\?subject=Terento%20installation%20issue"/);
  assert.match(entries[4].markup, /data-umami-event="support-link-click" data-umami-event-location="home-faq-install-failed" data-umami-event-channel="github-issue"/);
  assert.match(entries[4].markup, /data-umami-event="support-link-click" data-umami-event-location="home-faq-install-failed" data-umami-event-channel="email"/);
  if (locale === "en") {
    assert.match(entries[1].markup, />Read the installation guide\.</);
    assert.match(entries[4].markup, />Open an issue /);
    assert.match(entries[4].markup, />Email the log /);
  }
  assert.doesNotMatch(source, /<section[^>]+id="faq"[^>]*>[\s\S]*?<section[^>]+id="faq"/i, `${home}: one FAQ section`);
  assert.doesNotMatch(source, /href="[^"']*\/faq\//i, `${home}: no standalone FAQ route`);
}

const shellFiles = [
  "index.html",
  "about/index.html",
  "compatibility/index.html",
  "download/index.html",
  `${guideSlug}index.html`,
  "legal/index.html",
  "privacy/index.html",
];
for (const locale of locales) {
  for (const relative of shellFiles) {
    const shellLocale = relative.startsWith("legal/") || relative.startsWith("privacy/") ? "en" : locale;
    const file = pageFile(shellLocale, relative);
    const source = read(file);
    for (const navClass of ["primary-nav", "mobile-nav-links", "footer-nav"]) {
      const nav = source.match(new RegExp(`<nav class="${navClass}"[^>]*>([\\s\\S]*?)<\\/nav>`));
      assert.ok(nav, `${file}: ${navClass}`);
      const faqLinks = [...nav[1].matchAll(/<a href="([^"]+)"[^>]*>[^<]*FAQ/gi)].map((match) => match[1]);
      if (navClass === "footer-nav") {
        assert.deepEqual(faqLinks, [localePath(shellLocale) + "#faq"], `${file}: footer FAQ destination`);
      } else {
        assert.deepEqual(faqLinks, [], `${file}: ${navClass} must not expose FAQ`);
      }
    }
  }
}

for (const locale of locales) {
  const guide = pageFile(locale, `${guideSlug}index.html`);
  const source = read(guide);
  assert.equal((source.match(/class="guide-faq-link"/g) || []).length, 1, `${guide}: one Home FAQ link`);
  assert.match(source, new RegExp(`href="${localePath(locale)}#faq"`), `${guide}: localized Home FAQ link`);
  assert.match(source, /data-umami-event="faq-link-click" data-umami-event-location="guide-troubleshooting"/);
  assert.doesNotMatch(source, /<section class="guide-faq"\b|<details>\s*<summary>/i, `${guide}: no duplicated Guide FAQ`);
  assert.doesNotMatch(source, /"@type":\s*"FAQPage"/);
}

const styles = read(path.join(root, "site", "styles.css"));
assert.match(styles, /\.faq-grid\s*\{[\s\S]*grid-template-columns:\s*minmax\(220px, \.72fr\) minmax\(0, 1\.28fr\)/);
assert.doesNotMatch(styles, /\.guide-faq(?!-link)/, "Guide must not own FAQ layout styles");
assert.match(read(path.join(root, "site", "site-shell.js")), /window\.location\.hash === "#faq"/);

console.log("Canonical localized Home FAQ, Guide deduplication, routing, actions, and shell tests passed.");
