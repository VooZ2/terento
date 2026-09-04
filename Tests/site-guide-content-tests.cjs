"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const baseUrl = "https://terento.app";
const slug = "guides/install-garmin-maps-mac/";
const locales = ["en", "de", "fr", "pl", "cs", "it"];
const breadcrumbNames = {
  en: ["Home", "Install third-party maps on Garmin from a Mac"],
  de: ["Startseite", "Drittanbieter-Karten auf Garmin vom Mac installieren"],
  fr: ["Accueil", "Installer des cartes tierces sur Garmin depuis un Mac"],
  pl: ["Strona główna", "Instalowanie map innych firm na Garminie z Maca"],
  cs: ["Domů", "Instalace map třetích stran do Garminu z Macu"],
  it: ["Home", "Installare mappe di terze parti su Garmin da Mac"],
};
const localePath = (locale, suffix) => locale === "en" ? "/" + (suffix || "") : "/" + locale + "/" + (suffix || "");
const read = (file) => fs.readFileSync(file, "utf8");
const guideFile = (locale) => path.join(root, "site", locale === "en" ? slug : path.join(locale, slug), "index.html");
const metadata = JSON.parse(read(path.join(root, "site", "metadata.json")));
const release = JSON.parse(read(path.join(root, "site", "updates", "macos-arm64.json")));
const metadataByPath = new Map(metadata.pages.map((page) => [page.path, page]));
const currentBetaSignals = {
  en: /Freizeitkarte \+ OpenTopoMap \+ local import/,
  de: /Freizeitkarte \+ OpenTopoMap \+ lokaler Import/,
  fr: /Freizeitkarte \+ OpenTopoMap \+ import local/,
  pl: /Freizeitkarte \+ OpenTopoMap \+ lokalny import/,
  cs: /Freizeitkarte \+ OpenTopoMap \+ místní import/,
  it: /Freizeitkarte \+ OpenTopoMap \+ importazione locale/,
};
const downloadLabels = {
  en: "Download",
  de: "Herunterladen",
  fr: "Télécharger",
  pl: "Pobierz",
  cs: "Stáhnout",
  it: "Scarica",
};

function visibleText(fragment) {
  return fragment.replace(/<[^>]+>/g, "").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&apos;/g, "'").replace(/\s+/g, " ").trim();
}

function jsonLd(source, file) {
  const match = source.match(/<script\b[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/i);
  assert.ok(match, file + ": JSON-LD block");
  return JSON.parse(match[1].trim());
}

function oneEntity(data, type, file) {
  const entities = data["@graph"].filter((item) => item["@type"] === type);
  assert.equal(entities.length, 1, file + ": one " + type + " entity");
  return entities[0];
}

for (const locale of locales) {
  const file = guideFile(locale);
  const source = read(file);
  const publicPath = localePath(locale, slug);
  const page = metadataByPath.get(publicPath);
  assert.ok(page, locale + ": metadata entry");
  assert.ok(source.includes('<html lang="' + locale + '"') && source.includes('data-page="guide"'), locale + ": localized guide html");
  assert.ok(source.includes("<title>" + page.title + "</title>"), locale + ": title");
  assert.ok(source.includes('<meta name="description" content="' + page.description + '">'), locale + ": description");
  assert.ok(source.includes('href="' + baseUrl + publicPath + '"'), locale + ": canonical");
  assert.equal((source.match(/hreflang=/g) || []).length, 7, locale + ": hreflang");
  assert.ok(source.includes('hreflang="x-default" href="' + baseUrl + "/" + slug + '"'), locale + ": x-default");
  assert.equal((source.match(/<h1>/g) || []).length, 1, locale + ": one H1");
  assert.match(source, /<h1>[^<]+<\/h1>/);
  assert.match(source, /<h2 id="before-you-start-title">[^<]+<\/h2>/);
  assert.match(source, /Apple Silicon/);
  assert.match(source, /macOS 13/);
  assert.match(source, /USB/);
  assert.match(source, /free storage|freier Speicher|espace libre|wolnego miejsca|volného místa|spazio libero/i);
  assert.match(source, /1–2 minutes?|1–2 Minuten|1 à 2 minutes|1–2 minuty|1–2 minuti/);
  assert.match(source, currentBetaSignals[locale], locale + ": current beta provider scope label");
  assert.match(source, /Choose a map|Karte auswählen|Choisir une carte|Wybierz mapę|Vyberte mapu|Scegli una mappa/);
  assert.match(source, /third-party \.img|supported map file|unterstützte Kartendatei|fichier cartographique pris en charge|obsługiwany plik mapy|podporovaný mapový soubor|file cartografico supportato/i, locale + ": local map import guidance");
  assert.doesNotMatch(source, /Current beta uses Freizeitkarte|aktuelle Beta verwendet Freizeitkarte|bêta actuelle utilise Freizeitkarte|obecna beta korzysta z Freizeitkarte|aktuální beta používá Freizeitkarte|beta attuale usa Freizeitkarte/i, locale + ": no provider-specific current-beta claim");
  assert.match(source, /install-maps-1280\.avif[^\n]*width="1555" height="1012"/);
  assert.match(source, /installing-maps-1280\.avif[^\n]*width="1568" height="1003"/);
  assert.match(source, /your-garmin-1600\.avif\?v=20260902-your-garmin[^\n]*width="2200" height="1346"/);
  assert.equal([...source.matchAll(/<li class="guide-step">[\s\S]*?<\/li>/g)].length, 5, locale + ": five ordered steps");
  assert.match(source, /<ol class="guide-timeline">/);
  assert.match(source, /<nav class="guide-progress" data-guide-progress[^>]*aria-label="[^"]+">/);
  assert.equal([...source.matchAll(/<li><a href="#[^"]+"[^>]*><span class="guide-progress-number"/g)].length, 5, locale + ": five progress links");
  for (const section of ["before-you-start", "steps", "troubleshooting", "faq-help", "context"]) {
    assert.match(source, new RegExp(`id="${section}"`), `${locale}: progress target ${section}`);
  }
  assert.match(source, /\/guide-progress\.js\?v=20260902-guide-progress/);
  assert.match(source, /\/reading-state\.js\?v=20260902-reading-state/);
  assert.equal((source.match(/class="guide-screenshot"/g) || []).length, 3, locale + ": three screenshots");
  assert.match(source, /your-garmin|install-maps|installing-maps/);
  assert.doesNotMatch(source, /manage-maps|ready-to-install|object IDs?|MTP object trees?|transaction internals?|\/GARMIN|gmappmap\.img|gmaptz\.img|D\*\.img|hashes/i);
  assert.match(source, /href="https:\/\/github\.com\/VooZ2\/terento\/issues"[^>]*target="_blank"[^>]*rel="noopener noreferrer"/);
  assert.match(source, /mailto:hello@terento\.app\?subject=Terento%20installation%20issue/);
  assert.match(source, /hello@terento\.app/);
  assert.equal((source.match(/data-umami-event-location="guide-(?:hero|after-steps|bottom)"/g) || []).length, 3, locale + ": three guide download CTAs");
  const downloadButtons = [...source.matchAll(/<a class="download-action"[^>]*>([^<]+)<span aria-hidden="true">→<\/span><\/a>/g)];
  assert.equal(downloadButtons.length, 3, locale + ": three rendered download buttons");
  for (const button of downloadButtons) assert.equal(button[1].trim(), downloadLabels[locale], locale + ": download button label");
  for (const location of ["guide-hero", "guide-after-steps", "guide-bottom"]) assert.ok(source.includes('data-umami-event-location="' + location + '"'), locale + ": " + location);
  assert.match(source, /data-umami-event="compatibility-link-click" data-umami-event-location="guide-preflight"/);
  assert.match(source, /data-umami-event="support-link-click" data-umami-event-location="guide-install-failed" data-umami-event-channel="github-issue"/);
  assert.match(source, /data-umami-event="support-link-click" data-umami-event-location="guide-install-failed" data-umami-event-channel="email"/);
  assert.doesNotMatch(source, /[?&]utm_/i);
  assert.doesNotMatch(source, /Written by|Byline|Gediminas|author photo/i);
  assert.match(source, /https:\/\/support\.garmin\.com\/en-GB\/\?faq=bcmC4za1sy9hykGnopP8l7/);
  assert.match(source, /https:\/\/support\.garmin\.com\/en-US\/\?faq=4QVp7mKSIA1LDk5fc1OHX8/);
  assert.match(source, /https:\/\/support\.apple\.com\/en-ca\/102527/);
  assert.match(source, /does not replace Garmin Express|ersetzt Garmin Express nicht|ne remplace pas Garmin Express|nie zastępuje Garmin Express|nenahrazuje Garmin Express|non sostituisce Garmin Express/i);
  assert.doesNotMatch(source, /class="breadcrumbs"|<nav\b[^>]*(?:breadcrumb|Brotkrümel|Fil d’Ariane|Okruszki|Drobečková)/i, locale + ": no visible Guide breadcrumb navigation");

  const data = jsonLd(source, file);
  assert.equal(data["@context"], "https://schema.org");
  const article = oneEntity(data, "Article", file);
  assert.equal(article.datePublished, "2026-08-28T00:00:00Z", `${file}: ISO publication datetime`);
  assert.equal(article.dateModified, `${release.publishedAt}T00:00:00Z`, `${file}: ISO modified datetime`);
  assert.deepEqual(oneEntity(data, "Organization", file), {
    "@type": "Organization",
    "@id": baseUrl + "/#organization",
    name: "Terento",
    url: baseUrl + "/",
    logo: baseUrl + "/assets/logo-sky.svg",
    sameAs: ["https://github.com/VooZ2/terento"],
  }, `${file}: organization identity`);
  assert.equal(article.author["@id"], baseUrl + "/#organization");
  assert.equal(article.publisher["@id"], baseUrl + "/#organization");
  assert.equal(article.about["@id"], baseUrl + "/#software");
  assert.equal(article.inLanguage, locale);
  assert.equal(article.mainEntityOfPage["@id"], baseUrl + publicPath);
  assert.deepEqual(
    oneEntity(data, "BreadcrumbList", file).itemListElement.map(({ "@type": type, position, name, item }) => ({ type, position, name, item })),
    [
      { type: "ListItem", position: 1, name: breadcrumbNames[locale][0], item: baseUrl + localePath(locale) },
      { type: "ListItem", position: 2, name: breadcrumbNames[locale][1], item: baseUrl + publicPath },
    ],
    locale + ": two-item localized BreadcrumbList"
  );
  assert.equal(data["@graph"].filter((item) => item["@type"] === "FAQPage").length, 0, locale + ": Guide has no FAQ schema");
  assert.doesNotMatch(source, /<section class="guide-faq"\b|id="faq"/i, locale + ": Guide FAQ section removed");
  assert.match(source, /<section class="guide-faq-link"[^>]*aria-label="[^"]+"/);
  assert.match(source, new RegExp('href="' + localePath(locale) + '#faq"'));
  assert.match(source, /data-umami-event="faq-link-click" data-umami-event-location="guide-troubleshooting"/);
}

for (const locale of locales) {
  const guideIndex = locale === "en"
    ? path.join(root, "site", "guides", "index.html")
    : path.join(root, "site", locale, "guides", "index.html");
  assert.equal(fs.existsSync(guideIndex), false, locale + ": no artificial Guides index page");
}

assert.match(read(path.join(root, "site", "site-shell.js")), /pageType[^\n]*guide|pageType === "guide"/);
assert.match(read(path.join(root, "site", "site-shell.js")), /guides\/install-garmin-maps-mac\//);
for (const locale of locales) {
  const prefix = locale === "en" ? "" : locale + "/";
  for (const relative of [prefix + "index.html", prefix + "about/index.html", prefix + "download/index.html", prefix + "compatibility/index.html", prefix + slug + "index.html"]) {
    const source = read(path.join(root, "site", relative));
    const route = relative.includes("about") ? "about/" : relative.includes("compatibility") ? "compatibility/" : relative.includes("download") ? "download/" : relative.includes("guides/") ? slug : "";
    const rootPath = localePath(locale);
    const primary = source.match(/<nav class="primary-nav"[^>]*>([\s\S]*?)<\/nav>/)?.[1];
    const footer = source.match(/<nav class="footer-nav"[^>]*>([\s\S]*?)<\/nav>/)?.[1];
    assert.ok(primary && footer, relative + ": static shell navs");
    const hrefs = (fragment) => [...fragment.matchAll(/<a[^>]*href="([^"]+)"/g)].map((match) => match[1]);
    assert.deepEqual(hrefs(primary).slice(0, 4), [rootPath + "compatibility/", rootPath + slug, rootPath + "about/", rootPath + "download/"], relative + ": primary nav");
    assert.deepEqual(hrefs(footer), [rootPath + "about/", rootPath + "compatibility/", rootPath + slug, rootPath + "#faq", rootPath + "download/", "/legal/", "/privacy/"], relative + ": footer nav");
    assert.match(source, /Support Terento/);
    const languageOptions = source.match(/<div class="language-options">([\s\S]*?)<\/div>/)?.[1];
    assert.ok(languageOptions, relative + ": language options");
    for (const candidate of locales) assert.ok(languageOptions.includes('href="' + localePath(candidate, route) + '"'), relative + ": language route");
    const mainPrimary = primary.split('<span class="language-switcher">')[0];
    if (route === "about/" || route === "compatibility/" || route === "download/" || route === slug) assert.match(mainPrimary, /aria-current="page"/);
    if (route !== "about/" && route !== "compatibility/" && route !== "download/" && route !== slug) assert.doesNotMatch(mainPrimary, /aria-current="page"/);
  }
  const prefixPath = prefix;
  const home = read(path.join(root, "site", prefixPath + "index.html"));
  const download = read(path.join(root, "site", prefixPath + "download/index.html"));
  const compatibility = read(path.join(root, "site", prefixPath + "compatibility/index.html"));
  assert.match(home, /guides\/install-garmin-maps-mac/);
  assert.ok(download.includes('href="' + localePath(locale, slug) + '"'), locale + ": Download guide link");
  assert.ok(compatibility.includes('href="' + localePath(locale, slug) + '"'), locale + ": Compatibility guide link");
}
const sitemap = read(path.join(root, "site", "sitemap.xml"));
for (const locale of locales) assert.ok(sitemap.includes(baseUrl + localePath(locale, slug)), locale + ": sitemap guide URL");
assert.doesNotMatch(sitemap, /utm_|#/i);
assert.match(read(path.join(root, "README.md")), /Mac installation guide/);
const styles = read(path.join(root, "site", "styles.css"));
assert.doesNotMatch(styles, /\.guide-content\s*\{[^}]*max-width\s*:/s, "Guide must use the shared shell width");
assert.match(styles, /\.guide-step\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\) 72px minmax\(300px, \.9fr\)/s);
assert.match(styles, /\.guide-step-copy\s*\{[^}]*grid-column:\s*3/s);
assert.match(styles, /\.guide-screenshot\s*\{[^}]*grid-column:\s*1/s);
assert.match(styles, /\.guide-step-content\s*\{[^}]*display:\s*contents/s);
assert.doesNotMatch(styles, /zigzag|zig-zag/i);
assert.match(styles, /\.guide-progress\s*\{/);
assert.match(styles, /\.guide-progress a\[aria-current="location"\]/);
const shell = read(path.join(root, "site", "site-shell.js"));
for (const label of ["Guide", "Anleitung", "Guide", "Poradnik", "Průvodce", "Guida"]) assert.ok(shell.includes(`guide: "${label}"`), `shell Guide label: ${label}`);
assert.match(shell, /navLink\("compatibility"\).*navLink\("guide"\).*navLink\("about"\).*navLink\("download", "download-action"\)/s);
assert.match(shell, /<nav class="footer-nav"[\s\S]*navLink\("download"(?:, "", "footer-nav")?\)/s);
const languageScript = read(path.join(root, "site", "language.js"));
assert.match(languageScript, /shellLanguageMenu/);
assert.match(languageScript, /shellLanguageMenu\?\.update\?\.\(language\)/);
assert.match(read(path.join(root, "site", "legal-language.js")), /bindLanguageLinks/);
assert.match(read(path.join(root, "site", "privacy-language.js")), /bindLanguageLinks/);
for (const file of ["site/legal/index.html", "site/privacy/index.html"]) {
  const source = read(path.join(root, file));
  assert.match(source, /data-page="(?:legal|privacy)"/);
  const primary = source.match(/<nav class="primary-nav"[^>]*>([\s\S]*?)<\/nav>/)?.[1];
  assert.ok(primary, file + ": static shell nav");
  assert.deepEqual([...primary.matchAll(/<a[^>]*href="([^"]+)"/g)].slice(0, 4).map((match) => match[1]), ["/compatibility/", "/guides/install-garmin-maps-mac/", "/about/", "/download/"], file + ": primary nav");
}
console.log("Guide content, localization, shell, metadata, schema, links, and Umami contract tests passed.");
