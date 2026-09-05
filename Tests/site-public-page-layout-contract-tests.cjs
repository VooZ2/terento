const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), "utf8");
const styles = read("site/styles.css");
const styleVersion = "20260905-privacy-legal-v1";
const localizedContentVersion = "20260904-pass3-internal-link-events-v1";

const cssBlock = (selector) => {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = styles.match(new RegExp(`(?:^|\\n)${escaped}\\s*\\{([^}]*)\\}`, "s"));
  assert.ok(match, `Missing CSS block for ${selector}`);
  return match[1];
};

assert.match(styles, /--internal-page-intro-padding-top:\s*clamp\(34px, 5vw, 64px\)/);
assert.match(styles, /--product-photo-surface:\s*var\(--footer-text\)/);
for (const selector of [".compatibility-hero", ".guide-intro", ".download-main"]) {
  assert.match(cssBlock(selector), /var\(--internal-page-intro-padding-top\)/, `${selector} must use the shared intro token`);
}
assert.match(cssBlock(".hero"), /padding:\s*clamp\(48px, 5vw, 72px\)/, "Home hero begins within the first viewport");
assert.doesNotMatch(cssBlock(".hero"), /internal-page-intro/);

assert.match(cssBlock(".shell"), /width:\s*min\(calc\(100% - 48px\), var\(--max-width\)\)/);
assert.doesNotMatch(cssBlock(".compatibility-hero-inner"), /max-width|margin(?:-inline)?:\s*auto|text-align:\s*center/);
assert.match(cssBlock(".compatibility-hero-inner"), /text-align:\s*left/);
assert.match(cssBlock(".compatibility-hero-copy"), /max-width:\s*900px/);
assert.match(cssBlock(".compatibility-hero-copy"), /margin-inline:\s*0/);
assert.match(cssBlock(".compatibility-hero-copy"), /text-align:\s*left/);

const linkBlock = cssBlock(".download-info-link");
assert.match(linkBlock, /width:\s*fit-content/);
assert.match(linkBlock, /max-width:\s*100%/);
assert.match(linkBlock, /margin-top:\s*auto/);
assert.doesNotMatch(linkBlock, /justify-content:\s*space-between|(?:^|\n)\s*width:\s*100%/);
assert.match(styles, /\.text-link\s*\{[^}]*display:\s*inline-flex/);
assert.match(styles, /\.text-link\s*\{[^}]*font-size:\s*15px/);
assert.match(styles, /\.text-link\s*\{[^}]*font-weight:\s*600/);
assert.match(cssBlock(".download-info-link:visited"), /color:\s*var\(--link-text\)/);
assert.match(cssBlock(".download-info-link:hover,\n.download-info-link:focus-visible,\n.download-info-link:active"), /color:\s*var\(--link-text-hover\)/);
assert.doesNotMatch(cssBlock(".download-info-link-label"), /underline/);
assert.match(cssBlock(".download-info-link-tail"), /white-space:\s*nowrap/);
assert.match(cssBlock(".download-info-link-arrow"), /text-decoration:\s*none/);
assert.match(styles, /\.download-detail a:not\(\.text-link\)\s*\{/);
assert.match(cssBlock(".download-hero"), /max-width:\s*920px/);
assert.match(cssBlock(".download-details-list"), /grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/);
assert.match(cssBlock(".download-details"), /border-top:\s*1px solid var\(--border\)/);
assert.match(cssBlock(".download-detail"), /background:\s*var\(--surface\)/);
assert.match(cssBlock(".download-detail"), /border-radius:\s*16px/);
assert.match(styles, /a:focus-visible,[\s\S]*?outline:\s*3px solid var\(--focus-ring\)/);

const locales = {
  en: {
    file: "site/download/index.html",
    guide: "/guides/install-garmin-maps-mac/",
    compatibility: "/compatibility/",
    guideLabel: "Read the Mac installation guide",
    compatibilityLabel: "Check compatibility",
  },
  de: {
    file: "site/de/download/index.html",
    guide: "/de/guides/install-garmin-maps-mac/",
    compatibility: "/de/compatibility/",
    guideLabel: "Mac-Installationsanleitung lesen",
    compatibilityLabel: "Kompatibilität prüfen",
  },
  fr: {
    file: "site/fr/download/index.html",
    guide: "/fr/guides/install-garmin-maps-mac/",
    compatibility: "/fr/compatibility/",
    guideLabel: "Lire le guide d’installation sur Mac",
    compatibilityLabel: "Vérifier la compatibilité",
  },
  pl: {
    file: "site/pl/download/index.html",
    guide: "/pl/guides/install-garmin-maps-mac/",
    compatibility: "/pl/compatibility/",
    guideLabel: "Przeczytaj instrukcję instalacji na Macu",
    compatibilityLabel: "Sprawdź kompatybilność",
  },
  cs: {
    file: "site/cs/download/index.html",
    guide: "/cs/guides/install-garmin-maps-mac/",
    compatibility: "/cs/compatibility/",
    guideLabel: "Přečíst průvodce instalací na Macu",
    compatibilityLabel: "Ověřit kompatibilitu",
  },
  it: {
    file: "site/it/download/index.html",
    guide: "/it/guides/install-garmin-maps-mac/",
    compatibility: "/it/compatibility/",
    guideLabel: "Leggi la guida all’installazione su Mac",
    compatibilityLabel: "Verifica la compatibilità",
  },
};

const visibleText = (html) => html
  .replace(/<span class="download-info-link-arrow"[^>]*>[\s\S]*?<\/span>/g, "")
  .replace(/<[^>]+>/g, " ")
  .replace(/\s+/g, " ")
  .trim();

for (const [locale, contract] of Object.entries(locales)) {
  const html = read(contract.file);
  assert.match(html, new RegExp(`/styles\\.css\\?v=${styleVersion}`));
  assert.equal((html.match(/<link rel="stylesheet" href="\/styles\.css\?v=[^"]+">/g) || []).length, 1, `${locale} must load the shared stylesheet once`);
  assert.equal((html.match(/class="download-hero"/g) || []).length, 1, `${locale} must use one focused download hero`);
  assert.equal((html.match(/class="download-details"/g) || []).length, 1, `${locale} must use one technical details section`);
  assert.equal((html.match(/class="download-detail"/g) || []).length, 2, `${locale} must use two decision-support detail cards`);
  assert.doesNotMatch(html, /class="download-visual"|class="app-shot app-shot--download"|your-garmin-640\.avif/);
  assert.doesNotMatch(html, /class="download-requirement"/);
  assert.doesNotMatch(html, /class="download-trust"|Free · Notarized|Kostenlos · Notarisiert|Gratuit · Notarié|Bezpłatna · Notaryzowana|Zdarma · Notarizovaná|Gratuita · Notarizzata/);
  const intro = html.match(/<p class="download-intro"[^>]*>[\s\S]*?<\/p>/);
  assert.ok(intro, `${locale} must have a Download intro`);
  assert.doesNotMatch(intro[0], /<strong>/);
  assert.match(html, /class="download-action download-action-primary"[^>]+\.dmg/);
  assert.match(html, /class="download-action download-action-secondary"[^>]+\.zip/);
  assert.match(html, /class="download-action download-action-tertiary"[^>]+releases\/tag/);
  assert.doesNotMatch(html, /class="download-sections"|class="download-grid"|What is included|Was enthalten ist|Ce qui est inclus|Co zawiera|Co obsahuje|Cosa include/);
  assert.doesNotMatch(html, /New to third-party maps\?|Neu bei Drittanbieter-Karten\?|Vous débutez avec les cartes tierces|Dopiero zaczynasz z mapami innych firm|Začínáte s mapami třetích stran|È la prima volta che installi mappe di terze parti/);

  const anchors = [...html.matchAll(/<a class="text-link download-info-link" href="([^"]+)"([^>]*)>([\s\S]*?)<\/a>/g)];
  assert.equal(anchors.length, 2, `${locale} must expose exactly two Download information links`);
  assert.deepEqual(anchors.map((match) => match[1]), [contract.guide, contract.compatibility]);
  assert.deepEqual(anchors.map((match) => visibleText(match[3])), [contract.guideLabel, contract.compatibilityLabel]);
  for (const match of anchors) {
    assert.match(match[3], /class="download-info-link-tail"/);
    assert.match(match[3], /class="download-info-link-arrow" aria-hidden="true">→<\/span>/);
    assert.doesNotMatch(match[1], /utm_/i);
  }
  assert.match(anchors[1][2], /data-umami-event="compatibility-link-click"/);
  assert.match(anchors[1][2], /data-umami-event-location="download-page"/);
  if (locale !== "en") {
    assert.match(html, new RegExp(`/localized-content\\.js\\?v=${localizedContentVersion}`));
  }
}

for (const locale of Object.keys(locales)) {
  const prefix = locale === "en" ? "" : `${locale}/`;
  const html = read(`site/${prefix}compatibility/index.html`);
  assert.equal((html.match(/class="compatibility-hero-copy"/g) || []).length, 1, `${locale} must use one constrained hero copy wrapper`);
  assert.match(html, /<div class="shell compatibility-hero-inner"><div class="compatibility-hero-copy">/);
}

for (const locale of Object.keys(locales)) {
  const prefix = locale === "en" ? "" : `${locale}/`;
  const html = read(`site/${prefix}compatibility/index.html`);
  assert.match(html, /data-compatibility-evidence-note/);
  assert.match(html, /not Garmin certification|keine Garmin-Zertifizierung|certification Garmin|certyfikatem firmy Garmin|certifikaci Garmin|certificazione Garmin/i);
}

assert.doesNotMatch(read("site/localized-content.js"), /download-compatibility-link/);
assert.doesNotMatch(read("site/localized-content.js"), /download-requirement|download-item|copy\.included/);
assert.doesNotMatch(styles, /\.download-trust\s*\{/);

for (const [locale, contract] of Object.entries(locales)) {
  const html = read(contract.file);
  const trigger = html.match(/<summary class="language-trigger"[^>]*>([\s\S]*?)<\/summary>/)?.[1];
  assert.ok(trigger, `${locale} must have a language trigger`);
  assert.match(trigger, new RegExp(`class="language-code"[^>]*>${locale.toUpperCase()}<`));
  assert.doesNotMatch(trigger, /language-current|🇬🇧|🇩🇪|🇫🇷|🇵🇱|🇨🇿|🇮🇹/);
  assert.match(html, /class="language-option-flag"[^>]*>[^<]+<\/span><span>[^<]+<\/span>/);
  assert.match(html, /class="language-option"[^>]*aria-current="page"/);
}

assert.doesNotMatch(styles, /language-trigger::after|mobile-language-menu[^{]*\.language-trigger::after/);
assert.match(cssBlock(".language-options"), /width:\s*176px/);
assert.match(cssBlock(".language-option"), /justify-content:\s*flex-start/);
assert.match(cssBlock(".language-option > span:not(.language-option-flag)"), /text-overflow:\s*ellipsis/);
assert.match(styles, /\.mobile-language-menu \.language-options\s*\{[^}]*grid-template-columns:\s*1fr/s);
assert.match(styles, /\.mobile-language-menu \.language-option\s*\{[^}]*width:\s*100%[^}]*min-height:\s*44px/s);

assert.match(cssBlock(".about-social-link"), /min-height:\s*36px/);
assert.match(cssBlock(".about-social-link"), /padding:\s*7px 11px/);
assert.match(cssBlock(".about-social-link"), /border-radius:\s*8px/);
assert.match(cssBlock(".about-bullet-list"), /gap:\s*12px/);

for (const locale of Object.keys(locales)) {
  const prefix = locale === "en" ? "" : `${locale}/`;
  const html = read(`site/${prefix}about/index.html`);
  assert.match(html, new RegExp(`/styles\\.css\\?v=${styleVersion}`));
  assert.equal((html.match(/class="about-story"/g) || []).length, 1, `${locale} must have one personal story section`);
  assert.equal((html.match(/class="about-socials"/g) || []).length, 1, `${locale} must have one social links group`);
  assert.equal((html.match(/class="about-item about-item--group"/g) || []).length, 2, `${locale} must have one Does and one Doesn't group`);
  assert.doesNotMatch(html, /class="compatibility-hero about-hero"/);
  assert.equal((html.match(/<h1\b/g) || []).length, 1, `${locale} must have one primary About heading`);
  assert.match(html, /<section class="about-story" aria-labelledby="about-title">[\s\S]*<h1 id="about-title">/);
  assert.match(html, /<p class="eyebrow"><span class="status-dot" aria-hidden="true"><\/span>/, `${locale} About story eyebrow must use the shared status dot`);
  const storyCopy = html.match(/<div class="about-story-copy">[\s\S]*?<\/div>/)?.[0];
  assert.ok(storyCopy, `${locale} must have a story copy block`);
  assert.equal((storyCopy.match(/<p>/g) || []).length, 4, `${locale} must group the story into four idea-led paragraphs`);
  assert.match(html, /class="[^"]*about-slogan/);
  assert.equal((html.match(/class="about-bullet-list"/g) || []).length, 2, `${locale} must use lists for Does and Doesn't`);
  assert.match(html, /href="https:\/\/www\.linkedin\.com\/in\/gediminasc\/"[^>]+data-umami-event="social-link-click"[^>]+data-umami-event-location="about-story"[^>]+data-umami-event-channel="linkedin"/);
  assert.match(html, /href="https:\/\/www\.reddit\.com\/user\/MrDonas\/"[^>]+data-umami-event="social-link-click"[^>]+data-umami-event-location="about-story"[^>]+data-umami-event-channel="reddit"/);
  assert.match(html, /href="mailto:hello&#64;terento\.app"[^>]+data-umami-event="support-link-click"[^>]+data-umami-event-location="about-story"[^>]+data-umami-event-channel="email"[^>]*>[\s\S]*about-social-address[^>]*>hello&#64;terento\.app<\/span>/);
  assert.match(html, /href="https:\/\/buymeacoffee\.com\/vooz2"[^>]+data-umami-event="donate"[^>]+data-umami-event-location="about-story"[^>]+data-umami-event-channel="donate"/);
  assert.equal((html.match(/class="about-social-link(?:\s|\")/g) || []).length, 4, `${locale} must have LinkedIn, Reddit, Email, and Donate links`);
  assert.match(html, /\/assets\/social\/(?:email|linkedin|reddit|buymeacoffee)\.svg/);
  assert.doesNotMatch(html, /href="mailto:hello@terento\.app"/);
  assert.doesNotMatch(html, /Your device, ready for where you['’]re going|Open source by choice|Open source par choix|Open source od podstaw|Open source jako základ|Open source alla base/);
}

console.log("Public page intro and Download link layout contracts passed for all six locales.");
