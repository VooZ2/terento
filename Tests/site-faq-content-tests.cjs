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
  assert.equal(entries.length, 6, `${file}: exactly six FAQ entries`);
  return entries;
}

const questionSignals = [
  [/Garmin.*Terento/i, /Compatibility|Kompatibilitätsseite|Compatibilité|kompatybilności|zgodności|Kompatibilita|Compatibilità/i],
  [/BaseCamp/i, /Mac|macOS/],
  [/own|my own|ma propre|moją|vlastn|mia|\.img/i, /\.img|map|mapa|carte|Karte|mapy|mappa/i],
  [/update|aktual|mise à jour|à jour|nowsz|novější|più recent|aggiorn/i, /Terento|map/i],
  [/Garmin/, /Garmin Express[\s\S]*Android File Transfer[\s\S]*OpenMTP/],
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
  assert.match(entries[1].answer, /simple|einfach|simple|proste|jednoduch|semplice/i, `${home}: BaseCamp answer explains simple map management`);
  assert.match(entries[2].answer, /\.img|compatible|kompatib|zgodn|kompatibil|support/i, `${home}: own-map answer explains compatible local import`);
  assert.match(entries[5].answer, /already filled in|bereits ausgefüllten|déjà rempli|już wypełnionym|již vyplněnou|già compilato/, `${home}: installation report is prefilled`);
  assert.doesNotMatch(entries[5].answer, /copies a diagnostic|kopiert einen Diagnosebericht|copie un rapport|kopiuje raport|zkopíruje|copia un rapporto/, `${home}: no obsolete clipboard instruction`);
  assert.match(entries[3].question, /update|aktual|mise à jour|à jour|nowsz|novější|più recent|aggiorn/i, `${home}: update FAQ question`);
  assert.match(entries[3].answer, /newer|neuere|plus récente|nowsz|novější|più recent/i, `${home}: update FAQ answer`);
  assert.match(source, /class="provider-section section"[^>]*id="providers"[\s\S]*Freizeitkarte[\s\S]*OpenTopoMap[\s\S]*MapRando/i, `${home}: provider directory names current providers`);
  assert.match(source, /data-provider-card="freizeitkarte"[\s\S]*data-provider-card="opentopomap"/, `${home}: provider cards are data-driven`);
  assert.doesNotMatch(entries[3].answer, /beta|bêta|betę|betu/i, `${home}: update FAQ avoids beta-specific wording`);
  assert.doesNotMatch(source, /back up|backup|sauvegarder|zálohovat|wykonać kopię|zálohovat|eseguire il backup/i, `${home}: removed backup promise`);
  assert.match(entries[0].markup, new RegExp(`href="${localePath(locale, "compatibility/")}"`), `${home}: Compatibility link`);
  assert.match(entries[1].markup, new RegExp(`href="${localePath(locale, guideSlug)}"`), `${home}: Guide link`);
  assert.match(entries[1].markup, /data-umami-event="guide-link-click"/);
  assert.match(entries[1].markup, /data-umami-event-location="home-faq-basecamp"/);
  assert.match(entries[5].markup, /href="https:\/\/github\.com\/VooZ2\/terento\/issues\/new\/choose"[^>]*target="_blank"[^>]*rel="noopener noreferrer"/);
  assert.match(entries[5].markup, /href="mailto:hello&#64;terento\.app\?subject=Terento%20installation%20issue"/);
  assert.doesNotMatch(entries[5].markup, /href="mailto:hello@terento\.app/);
  assert.match(entries[5].markup, /data-umami-event="support-link-click" data-umami-event-location="home-faq-install-failed" data-umami-event-channel="github-issue"/);
  assert.match(entries[5].markup, /data-umami-event="support-link-click" data-umami-event-location="home-faq-install-failed" data-umami-event-channel="email"/);
  // The FAQ section has one general Troubleshooting link, on the installation-failed answer.
  const faqSection = source.match(/<section\b[^>]*\bid=["']faq["'][^>]*>([\s\S]*?)<\/section>/i)[1];
  const troubleshootingLinks = [...faqSection.matchAll(/<a\b[^>]*href="([^"]*guides\/troubleshooting\/[^"]*)"[^>]*>/g)].map((match) => match[0]);
  assert.equal(troubleshootingLinks.length, 1, `${home}: exactly one Troubleshooting link in the FAQ`);
  assert.equal(
    troubleshootingLinks[0],
    `<a href="${localePath(locale, "guides/troubleshooting/")}" data-umami-event="guide-link-click" data-umami-event-location="home-faq-troubleshooting">`,
    `${home}: general Troubleshooting link without an anchor`,
  );
  assert.match(entries[5].markup, /data-umami-event-location="home-faq-troubleshooting"/, `${home}: Troubleshooting link sits on the installation-failed answer`);
  assert.doesNotMatch(faqSection, /guides\/troubleshooting\/#/, `${home}: no anchor links inside FAQ answers`);
  assert.doesNotMatch(entries[4].markup, /<a\b/, `${home}: watch-not-showing-up answer has no inline links`);
  if (locale === "en") {
    assert.match(entries[1].markup, />Read the installation guide\.</);
    assert.match(entries[5].markup, />Open an issue /);
    assert.match(entries[5].markup, />Email support /);
    assert.equal(entries[4].question, "Why isn’t my Garmin watch showing up on my Mac?");
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
  "guides/troubleshooting/index.html",
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
      if (navClass === "mobile-nav-links") {
        assert.match(nav[1], /href="[^"]*download\//, `${file}: mobile navigation must expose Download`);
      }
    }
  }
}

for (const locale of locales) {
  const guide = pageFile(locale, `${guideSlug}index.html`);
  const source = read(guide);
  assert.doesNotMatch(source, /class="guide-faq-link"|id="faq-help"|id="context"/, `${guide}: Guide keeps the focused flow without duplicate help sections`);
  assert.doesNotMatch(source, /<section class="guide-faq"\b|<details>\s*<summary>/i, `${guide}: no duplicated Guide FAQ`);
  assert.doesNotMatch(source, /"@type":\s*"FAQPage"/);
}

const styles = read(path.join(root, "site", "styles.css"));
assert.match(styles, /\.faq-grid\s*\{[\s\S]*grid-template-columns:\s*minmax\(220px, \.72fr\) minmax\(0, 1\.28fr\)/);
assert.doesNotMatch(styles, /\.guide-faq(?!-link)/, "Guide must not own FAQ layout styles");
assert.match(read(path.join(root, "site", "site-shell.js")), /window\.location\.hash === "#faq"/);

console.log("Canonical localized Home FAQ, focused Guide flow, routing, actions, and shell tests passed.");
