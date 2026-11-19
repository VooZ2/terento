const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

const root = path.resolve(__dirname, "..");
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), "utf8");
const styles = read("site/styles.css");
const shellSource = read("site/site-shell.js");
const languageSource = read("site/language.js");
const styleVersion = "20261119-site-refresh-v5";
const mobileLanguageNames = { en: "English", de: "Deutsch", fr: "Français", pl: "Polski", cs: "Čeština", it: "Italiano" };

const cssBlock = (selector) => {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = styles.match(new RegExp(`(?:^|\\n)${escaped}\\s*\\{([^}]*)\\}`, "s"));
  assert.ok(match, `Missing CSS block for ${selector}`);
  return match[1];
};

assert.match(styles, /--internal-page-intro-padding-top:\s*clamp\(34px, 5vw, 64px\)/);
assert.match(styles, /--product-photo-surface:\s*var\(--footer-text\)/);
for (const selector of [".compatibility-hero", ".guide-intro", ".download-main", ".map-styles-hero"]) {
  assert.match(cssBlock(selector), /var\(--internal-page-intro-padding-top\)/, `${selector} must use the shared intro token`);
}
assert.match(cssBlock(".hero"), /padding:\s*clamp\(48px, 5vw, 72px\)/, "Home hero begins within the first viewport");
assert.doesNotMatch(cssBlock(".hero"), /internal-page-intro/);

assert.match(cssBlock(".shell"), /width:\s*min\(calc\(100% - 48px\), var\(--max-width\)\)/);
// Round 4 (owner): one hero on every page, left-aligned on the canvas in a 720px column, no card.
assert.match(cssBlock("#main-content .page-hero"), /padding:\s*var\(--hero-top\) 0 var\(--hero-gap\)/);
assert.match(cssBlock("#main-content .page-hero"), /background:\s*none/);
assert.match(cssBlock("#main-content .page-hero .hero-copy"), /max-width:\s*720px/);
assert.match(cssBlock("#main-content .page-hero .hero-copy"), /text-align:\s*left/);
assert.match(cssBlock("#main-content .page-hero .hero-lede"), /max-width:\s*65ch/);
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
assert.match(cssBlock(".download-hero"), /grid-template-columns:\s*minmax\(0, 1fr\) minmax\(0, 400px\)/);
assert.match(cssBlock(".download-details-list"), /grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/);
assert.match(cssBlock(".download-details"), /border-top:\s*1px solid var\(--border\)/);
assert.match(cssBlock(".download-detail"), /background:\s*var\(--surface\)/);
assert.match(cssBlock(".download-detail"), /border-radius:\s*16px/);
assert.match(styles, /a:focus-visible,[\s\S]*?outline:\s*3px solid var\(--focus-ring\)/);
assert.match(styles, /h1,\s*\nh2,\s*\nh3\s*\{[\s\S]*?text-wrap:\s*balance;/, "marketing headings must balance their lines");
assert.match(styles, /\.hero-lede,\s*\n\.download-intro,\s*\n\.provider-summary,\s*\n\.provider-addon-copy\s*\{[\s\S]*?text-wrap:\s*pretty;/, "short supporting copy should avoid awkward final lines");
assert.match(cssBlock(".download-action"), /transition-property:\s*scale, background-color/);
assert.match(styles, /\.download-action:active\s*\{[^}]*scale:\s*0\.96/);
assert.match(styles, /\.provider-addon > summary\.provider-addon-toggle::after,[\s\S]*?transition:\s*transform 160ms ease-out;/);
assert.match(cssBlock(".provider-count"), /font-variant-numeric:\s*tabular-nums/);
assert.match(cssBlock(".provider-addon-count"), /font-variant-numeric:\s*tabular-nums/);

const downloadCopy = JSON.parse(read("scripts/templates/download-copy.json"));
// Apple's official badge: unmodified artwork per locale (English where Apple has no localized Mac App Store badge).
const appStoreBadge = JSON.parse(read("scripts/templates/app-store-badge.json"));
const appStoreArtwork = {
  en: "15111cd04380b58d95307dcb07f0b6b06304dbc7504c57fd9cdbf0a2f78e3a92",
  de: "9847a40d54aed58c0a19ef87f262e9dde56da82960c1f09ada58a6ffb56dc33e",
  fr: "28c046d4b469e9a56547486fe9edb2a646279e45c361d80eb7c3cb0c34754976",
  it: "9d7bfb44ace53629ae11ab7412bbb9f7aaee82e7e7588c7ec2aea23f02bbd228",
};
assert.deepEqual(fs.readdirSync(path.join(root, "site/assets/app-store")).sort(), Object.keys(appStoreArtwork).sort().map((name) => `download-on-the-mac-app-store-${name}.svg`));
for (const [name, digest] of Object.entries(appStoreArtwork)) {
  const artwork = fs.readFileSync(path.join(root, `site/assets/app-store/download-on-the-mac-app-store-${name}.svg`));
  assert.equal(crypto.createHash("sha256").update(artwork).digest("hex"), digest, `${name} App Store badge is Apple's unmodified file`);
}
assert.deepEqual(Object.fromEntries(Object.entries(appStoreBadge.badges).map(([locale, badge]) => [locale, badge.artwork])), { en: "en", de: "de", fr: "fr", pl: "en", cs: "en", it: "it" });
assert.match(cssBlock(".app-store-badge img"), /height:\s*40px/, "App Store badge keeps Apple's 40px minimum height");
assert.match(cssBlock(".download-action--store"), /\bheight:\s*40px/, "Download button has the badge height");
assert.match(cssBlock(".download-action--store"), /border-radius:\s*var\(--control-radius\)/, "Download button keeps the 10px control radius");
assert.match(styles, /--control-radius:\s*10px;/, "control radius token is 10px");
assert.match(cssBlock(".store-actions"), /gap:\s*12px/, "Button and badge sit 12px apart");
assert.doesNotMatch(styles, /\.app-store-badge[^{]*\{[^}]*(transform|filter|animation|transition|opacity|rotate|scale)/, "App Store badge is never modified, angled or animated");
const manifest = JSON.parse(read("site/updates/macos-arm64.json"));
const locales = Object.fromEntries(["en", "de", "fr", "pl", "cs", "it"].map((locale) => [locale, {
  file: `site/${locale === "en" ? "" : `${locale}/`}download/index.html`,
  root: locale === "en" ? "/" : `/${locale}/`,
}]));

for (const [locale, contract] of Object.entries(locales)) {
  const html = read(contract.file);
  const copy = downloadCopy[locale];
  const main = html.match(/<main[\s\S]*?<\/main>/)[0];
  assert.match(html, new RegExp(`/styles\\.css\\?v=${styleVersion}`));
  assert.equal((html.match(/<link rel="stylesheet" href="\/styles\.css\?v=[^"]+">/g) || []).length, 1, `${locale} must load the shared stylesheet once`);
  assert.match(main, /<main id="main-content" class="download-main download-v2">/);
  assert.equal((main.match(/<h1>/g) || []).length, 1);
  assert.doesNotMatch(main, /class="eyebrow"|→|·/, `${locale} Download has no eyebrow labels, arrows or middle dots`);
  // One primary action: the DMG. The Mac App Store listing is Apple's official badge with the site-download campaign.
  assert.equal((main.match(/class="download-action[ "]/g) || []).length, 1, `${locale} has one primary download action`);
  assert.match(main, new RegExp(`<a class="download-action download-action--store download-v2-primary" href="${manifest.downloadURL.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"`));
  const badge = appStoreBadge.badges[locale];
  const badgeLang = badge.artwork === locale ? "" : ` lang="${badge.artwork}"`;
  assert.ok(main.includes(`<a class="app-store-badge download-v2-store-link" href="https://apps.apple.com/app/apple-store/id6828556832?pt=129348028&amp;ct=site-download&amp;mt=8" data-umami-event="app-store-click" data-umami-event-location="download-page"><img src="/assets/app-store/download-on-the-mac-app-store-${badge.artwork}.svg?v=${appStoreBadge.asset_version}" width="156" height="40" alt="${badge.alt}"${badgeLang}></a></div><p class="hero-secondary download-v2-web">`), `${locale} App Store badge follows the Download button`);
  assert.equal((main.match(/apps\.apple\.com/g) || []).length, 1, `${locale} links the App Store once`);
  assert.equal((html.match(/class="app-store-badge /g) || []).length, 1, `${locale} shows one App Store badge`);
  assert.doesNotMatch(main, /download-v2-store-note|download-v2-store-status|Coming soon/, `${locale} has no App Store note or "coming soon" status`);
  assert.ok(main.indexOf("download-v2-actions") < main.indexOf("download-v2-shot"));
  for (const need of copy.needs) assert.ok(main.includes(need.replace(/’/g, "’")), `${locale} lists requirement: ${need}`);
  assert.equal((main.match(/<h2 /g) || []).length, 2, `${locale} has one requirements and one after-download heading`);
  assert.equal((main.match(/<ol class="steps">[\s\S]*?<\/ol>/)[0].match(/<li>/g) || []).length, 3, `${locale} has three after-download steps`);
  assert.doesNotMatch(main, /\.zip"/, `${locale} keeps the ZIP off the page`);
  // Round 5 (owner): no checksum block; "What's new" opens the GitHub release page, which lists the
  // checksum of every file. One short release line.
  assert.doesNotMatch(main, /download-sha|<code>|SHA-256/, `${locale} no SHA-256 block`);
  const release = main.match(/<p class="download-release">[\s\S]*?<\/p>/)?.[0];
  assert.ok(release, `${locale} release line`);
  assert.ok(release.includes(`<a class="text-link" href="${manifest.releaseNotesURL}" rel="noopener noreferrer">`), `${locale} "What's new" opens the GitHub release page`);
  assert.match(manifest.releaseNotesURL, /^https:\/\/github\.com\/VooZ2\/terento\/releases\/tag\//);
  if (locale === "en") assert.equal(release.replace(/<[^>]+>/g, ""), "Latest version v1.2.1, November 14, 2026. What’s new");
  const links = [...main.matchAll(/<a class="text-link( download-info-link)?" href="([^"]+)" data-umami-event="([^"]+)" data-umami-event-location="([^"]+)">/g)].map((m) => [m[2], m[3], m[4], Boolean(m[1])]);
  assert.deepEqual(links, [
    [`${contract.root}install/`, "web-installer-link-click", "download-page", false],
    [`${contract.root}compatibility/`, "compatibility-link-click", "download-page", true],
    [`${contract.root}guides/install-garmin-maps-mac/`, "guide-link-click", "download-page", false],
    [`${contract.root}guides/install-garmin-maps-edge-mac/`, "guide-link-click", "download-page-edge", false],
  ], `${locale} Download links keep their Umami events`);
  assert.doesNotMatch(html, /localized-content\.js/);
}

for (const locale of Object.keys(locales)) {
  const prefix = locale === "en" ? "" : `${locale}/`;
  const html = read(`site/${prefix}compatibility/index.html`);
  assert.equal((html.match(/ compatibility-hero-copy"/g) || []).length, 1, `${locale} must use one constrained hero copy wrapper`);
  // Round 4 (owner): plain hero (no card): H1 and one lead, no device images, no model names.
  // Round 5: one quiet summary sentence under the lead; the grid starts right under the toolbar.
  assert.match(html, /<section class="compatibility-hero page-hero" aria-labelledby="compatibility-title">\s*<div class="shell"><div class="hero-copy compatibility-hero-copy">\s*<h1 id="compatibility-title">[^<]+<\/h1>\s*<p class="hero-lede">[^<]+<\/p>\s*<div class="compatibility-summary" id="compatibility-summary"[^>]*><p class="compatibility-summary-line" data-summary-content>[\s\S]*?<\/p><p class="compatibility-freshness"[\s\S]*?<\/p><\/div>\s*<\/div><\/div>\s*<\/section>/);
  assert.match(html, /<\/form>\s*<p class="compatibility-results-count" id="results-count"[^>]*>[^<]+<\/p><div class="watch-grid"/, `${locale} the grid follows the toolbar directly`);
  assert.match(html, /<form class="compatibility-filters" id="compatibility-filters" role="search"><div class="segmented compatibility-chips" role="group" aria-label="[^"]+">(?:<button type="button" class="segmented-option" data-device-filter="[^"]+" aria-pressed="(?:true|false)">[^<]+<\/button>){3}<\/div><div class="compatibility-filter-control compatibility-search"><input id="watch-search" type="search" placeholder="[^"]+" aria-label="[^"]+" autocomplete="off"><\/div><details class="compatibility-more-filters">/, `${locale} segmented control, search without a visible label, More filters`);
  assert.match(html, /<div class="compatibility-after grid"><div class="compatibility-community-cta card">[\s\S]*?<\/div><\/div><div class="compatibility-how card"><h2>[^<]+<\/h2><div class="compatibility-how-body">(?:<p[^>]*>[^<]+<\/p>){3}<\/div><\/div><\/div><div class="cta-band end-cta">/, `${locale} "How this list works" sits under the grid next to "Don't see your Garmin here?", full text`);
  assert.doesNotMatch(html.match(/<div class="watch-grid"[\s\S]*?<\/div><script/)[0], /watch-variant">(?:Smartwatch|Montre connectée|Bike computer|Fahrradcomputer)<|\d{1,2}\/\d{1,2}\/\d{4}/, `${locale} no filler variant and no numeric US dates`);
  assert.doesNotMatch(html.match(/<section class="compatibility-hero[\s\S]*?<\/section>/)[0], /<img\b|130 Plus/, `${locale} compatibility hero has no images and names no models`);
}

for (const locale of Object.keys(locales)) {
  const prefix = locale === "en" ? "" : `${locale}/`;
  const html = read(`site/${prefix}compatibility/index.html`);
  assert.match(html, /data-compatibility-evidence-note/);
  assert.match(html, /not Garmin certification|keine Garmin-Zertifizierung|certification Garmin|certyfikatem firmy Garmin|certyfikacją Garmin|certifikaci Garmin|certificazione Garmin/i);
}

assert.doesNotMatch(styles, /\.download-trust\s*\{/);

for (const [locale, contract] of Object.entries(locales)) {
  const html = read(contract.file);
  const trigger = html.match(/<summary class="language-trigger"[^>]*>([\s\S]*?)<\/summary>/)?.[1];
  assert.ok(trigger, `${locale} must have a language trigger`);
  assert.match(trigger, new RegExp(`class="language-code"[^>]*>${locale.toUpperCase()}<`));
  assert.doesNotMatch(trigger, /language-current|🇬🇧|🇩🇪|🇫🇷|🇵🇱|🇨🇿|🇮🇹/);
  assert.match(html, /class="language-option-flag"[^>]*>[^<]+<\/span><span>[^<]+<\/span>/);
  assert.match(html, /class="language-option"[^>]*aria-current="page"/);
  const mobileNav = html.match(/<nav class="mobile-nav-links"[^>]*>([\s\S]*?)<\/nav>/);
  assert.ok(mobileNav, `${locale} must have a mobile navigation`);
  assert.match(mobileNav[1], /href="[^"]*download\//, `${locale} mobile navigation must expose Download`);
  const mobileTrigger = html.match(/<details class="language-menu mobile-language-menu">\s*<summary class="language-trigger"[^>]*><span class="mobile-language-label">([^<]+)<\/span>/);
  assert.ok(mobileTrigger, `${locale} must have a full-name mobile language trigger`);
  assert.equal(mobileTrigger[1], mobileLanguageNames[locale], `${locale} mobile language trigger must use the full language name`);
}

assert.doesNotMatch(styles, /language-trigger::after|mobile-language-menu[^{]*\.language-trigger::after/);
assert.match(cssBlock(".language-options"), /width:\s*176px/);
assert.match(cssBlock(".language-option"), /justify-content:\s*flex-start/);
assert.match(cssBlock(".language-option > span:not(.language-option-flag)"), /text-overflow:\s*ellipsis/);
assert.match(styles, /\.mobile-language-menu \.language-options\s*\{[^}]*grid-template-columns:\s*1fr/s);
assert.match(styles, /\.mobile-language-menu \.language-option\s*\{[^}]*width:\s*100%[^}]*min-height:\s*44px/s);

assert.match(cssBlock(".about-social-link"), /min-height:\s*40px/);
assert.match(cssBlock(".about-social-link"), /padding:\s*7px 11px/);
assert.match(cssBlock(".about-social-link"), /border-radius:\s*var\(--control-radius\)/);
assert.match(cssBlock(".about-bullet-list"), /gap:\s*12px/);
assert.match(styles, /@media \(min-width: 1100px\)\s*\{\s*\.app-shot--hero\s*\{[^}]*width:\s*115%/s);
assert.match(cssBlock(".problem-statement p"), /font-family:\s*var\(--font-ui\)/);
assert.match(cssBlock(".problem-statement p"), /font-size:\s*clamp\(18px, 2vw, 21px\)/);
assert.match(cssBlock(".faq.section"), /padding:\s*clamp\(64px, 8vw, 96px\) 0/);
assert.match(cssBlock('.primary-nav .download-action[aria-current="page"]'), /background:\s*var\(--interactive\)/);
assert.match(cssBlock(".mobile-language-menu .language-trigger"), /border:\s*1px solid var\(--border\)/);
assert.match(cssBlock(".mobile-language-menu .language-trigger"), /background:\s*var\(--surface-muted\)/);
assert.match(cssBlock(".mobile-language-menu .language-options"), /border:\s*1px solid var\(--border\)/);
assert.match(cssBlock(".mobile-language-menu .language-options"), /background:\s*var\(--surface\)/);
assert.doesNotMatch(styles, /\.mobile-language-menu \.language-options\s*\{[^}]*grid-template-columns:\s*repeat/);
assert.doesNotMatch(shellSource, /navLink\("download", "download-action", "mobile-nav"\)/);
assert.match(shellSource, /mobile-language-label/);
assert.doesNotMatch(shellSource, /replaceWith|createContextualFragment/);

for (const locale of Object.keys(locales)) {
  const prefix = locale === "en" ? "" : `${locale}/`;
  const html = read(`site/${prefix}about/index.html`);
  assert.match(html, new RegExp(`/styles\\.css\\?v=${styleVersion}`));
  // Round 5 (owner): H1, one-line lead, "What Terento is, and what it isn't", then "Who makes it": the
  // story at body size, then the contact links and the donation line in the same section. No panel, no CTA.
  assert.equal((html.match(/about-story-card/g) || []).length, 0, `${locale} the story is not a card`);
  assert.equal((html.match(/class="card about-socials"|about-socials card/g) || []).length, 0, `${locale} contacts are not a panel`);
  assert.equal((html.match(/class="card col-6 about-item about-item--group"/g) || []).length, 2, `${locale} must have one Does and one Doesn't card`);
  assert.doesNotMatch(html, /class="compatibility-hero about-hero"/);
  assert.equal((html.match(/<h1\b/g) || []).length, 1, `${locale} must have one primary About heading`);
  assert.match(html, /<section class="page-hero about-hero" aria-labelledby="about-title">\s*<div class="shell"><div class="hero-copy">\s*<h1 id="about-title">(?:About Terento|Über Terento|À propos de Terento|O Terento|Informazioni su Terento)<\/h1>\s*<p class="hero-lede">[^<]+<\/p>\s*<\/div><\/div>\s*<\/section>\s*<section class="block about-main"/, `${locale} H1, one-line lead, then what it is and isn't`);
  assert.doesNotMatch(html, /about-maker-photo/, `${locale} no photo`);
  assert.doesNotMatch(html, /about-title-icon/);
  assert.doesNotMatch(html.match(/<main[\s\S]*?<\/main>/)[0], /class="eyebrow"|about-intro-copy|data-umami-event-location="about-intro"/, `${locale} no product sentence or Download button at the top`);
  const story = html.match(/<section class="block about-story" aria-labelledby="about-maker-title">[\s\S]*?<\/section>/)?.[0];
  assert.ok(story, `${locale} "Who makes it" section`);
  assert.ok(html.indexOf('class="block about-main"') < html.indexOf('class="block about-story"'), `${locale} what it is/isn't comes first`);
  assert.match(story, /<div class="about-story-copy">\s*<h2 id="about-maker-title">[^<]+<\/h2>\s*<p class="about-maker"><span class="about-maker-name">Gediminas<\/span><span class="about-maker-role">[^<]+<\/span><\/p>/, `${locale} heading, then name and role`);
  assert.doesNotMatch(story.split('<div class="about-socials">')[0], /<img\b/, `${locale} About story is text only (no photo or avatar)`);
  const storyCopy = story.match(/<div class="about-story-copy">[\s\S]*?<\/div>/)?.[0];
  assert.ok(storyCopy, `${locale} must have a story copy block`);
  assert.equal((storyCopy.match(/<p>/g) || []).length, 3, `${locale} owner-approved story in three short paragraphs`);
  assert.match(storyCopy, /Garmin fēnix/, `${locale} fēnix keeps its macron`);
  assert.match(story, /<\/div>\s*<div class="about-socials">\s*<p class="about-social-label">[^<]+<\/p>[\s\S]*class="about-donate"/, `${locale} contact links and the donation line follow the story in the same section`);
  assert.doesNotMatch(html, /cta-band|end-cta|about-bottom/, `${locale} no closing call to action on About`);
  const schema = JSON.parse(html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/)[1]);
  const person = schema["@graph"].find(node => node["@type"] === "Person");
  assert.deepEqual(person.sameAs, ["https://www.linkedin.com/in/gediminasc/", "https://www.reddit.com/user/MrDonas/"], `${locale} Person sameAs lists only the profiles on the page`);
  assert.equal(person.email, undefined, `${locale} no e-mail in schema`);
  assert.deepEqual(schema["@graph"].find(node => node["@type"] === "Organization").founder, { "@id": person["@id"] });
  // Code and map credits live in the footer and on Map styles, not in a separate About section (2026-11-16).
  const aboutMain = html.match(/<main[\s\S]*?<\/main>/)[0];
  assert.doesNotMatch(html, /about-v2-open|about-open-title/, `${locale} About no longer repeats the code and map credits`);
  assert.match(html, /<a class="footer-project-link" data-project-link href="https:\/\/github\.com\/VooZ2\/terento"/, `${locale} footer links the source code`);
  assert.match(aboutMain, new RegExp(`href="/${prefix}map-styles/" data-umami-event="maps-link-click" data-umami-event-location="about-main"`), `${locale} About points to the map credits`);
  const mapStyles = read(`site/${prefix}map-styles/index.html`);
  assert.equal((mapStyles.match(/© [^<]*OpenStreetMap[^<]* \(ODbL\)/g) || []).length, 5, `${locale} Map styles keeps the © OpenStreetMap (ODbL) credit for every map project`);
  for (const project of ["OpenTopoMap", "Freizeitkarte", "MapRando", "BBBike", "OSMapaPL"]) assert.match(mapStyles, new RegExp(project), `${locale} Map styles credits ${project}`);
  const mentions = aboutMain.match(/<section class="block about-v2-mentions" aria-labelledby="about-mentions-title">[\s\S]*?<\/section>/)?.[0];
  assert.ok(mentions, `${locale} About lists who wrote about Terento`);
  assert.ok(aboutMain.indexOf('class="block about-main"') < aboutMain.indexOf('class="block about-v2-mentions"'), `${locale} mentions close the page`);
  // Round 3: one card per mention (site name label, title link), two columns from 900px.
  assert.match(mentions, /<h2 id="about-mentions-title">[^<]+<\/h2><p>[^<]+<\/p><\/div>\s*<ul class="grid about-mentions">/);
  const mentionLinks = [...mentions.matchAll(/<li class="card about-mention"><p class="about-mention-source">([^<]+)<\/p><a class="text-link" href="([^"]+)"([^>]*)>([^<]+)<\/a><\/li>/g)];
  assert.deepEqual(mentionLinks.map(match => match[2]), [
    "https://the5krunner.com/2026/09/22/garmin-mac-custom-maps-terento/",
    "https://hikingguy.com/gear/garmin-fenix-9-pro-review/",
    "https://www.youtube.com/watch?v=szqwPHHWiTM",
  ], `${locale} mention order`);
  assert.deepEqual(mentionLinks.map(match => match[4]), [
    "Terento Makes Installing Custom Maps on Garmin Watches Effortless for Mac Users",
    "Garmin Fenix 9 Pro Review",
    "Garmin Fenix: 17 Tips I Wish I Knew Sooner",
  ], `${locale} mention titles stay in the original language`);
  assert.equal(mentionLinks[0][1], "the5krunner (Indie Spotlight)", `${locale} the5krunner label stays in English`);
  assert.equal(mentionLinks[1][1], "HikingGuy", `${locale} HikingGuy label`);
  assert.match(mentionLinks[2][1], /^HikingGuy \([^)]+\)/, `${locale} the video mention says it is a video`);
  for (const match of mentionLinks) {
    assert.doesNotMatch(match[3], /rel=|target=/, `${locale} mentions are normal followed links`);
    assert.equal(match[3], locale === "en" ? "" : ' lang="en"', `${locale} English titles carry their language`);
  }
  assert.doesNotMatch(html, /vibe coding|software developer|Softwareentwickler|développeur logiciel|programistą|vývojář|sviluppatore software/i);
  const main = html.match(/<main[\s\S]*?<\/main>/)[0];
  assert.equal((main.match(/class="download-action /g) || []).length, 0, `${locale} About has no Download button`);
  assert.match(main, new RegExp(`href="/${prefix}compatibility/"`));
  assert.match(main, /\.img/);
  assert.equal((html.match(/class="about-bullet-list"/g) || []).length, 2, `${locale} must use lists for Does and Doesn't`);
  assert.match(html, /href="https:\/\/www\.linkedin\.com\/in\/gediminasc\/"[^>]+data-umami-event="social-link-click"[^>]+data-umami-event-location="about-story"[^>]+data-umami-event-channel="linkedin"[^>]+data-umami-event-destination="linkedin\.com"/);
  assert.match(html, /href="https:\/\/www\.reddit\.com\/user\/MrDonas\/"[^>]+data-umami-event="social-link-click"[^>]+data-umami-event-location="about-story"[^>]+data-umami-event-channel="reddit"[^>]+data-umami-event-destination="reddit\.com"/);
  assert.match(html, /<a class="about-social-link about-email-link" href="mailto:hello&#64;terento\.app"[^>]+data-umami-event="support-link-click"[^>]+data-umami-event-location="about-story"[^>]+data-umami-event-channel="email"[^>]*>[\s\S]*<span>(?:Email|E-Mail|E-mail)<\/span><\/a>/);
  assert.doesNotMatch(html, /about-social-address|hello&#64;terento\.app<\/a>/, `${locale} must keep the email address out of the visible About social links`);
  assert.match(html, /href="https:\/\/buymeacoffee\.com\/vooz2"[^>]+data-umami-event="donate"[^>]+data-umami-event-location="about-story"[^>]+data-umami-event-channel="donate"/);
  assert.equal((html.match(/class="about-social-link(?:\s|\")/g) || []).length, 4, `${locale} must have LinkedIn, Reddit, Email, and Donate links`);
    assert.doesNotMatch(html, /does not promise compatibility|verspricht keine Kompatibilität|ne promet pas la compatibilité|nie obiecuje kompatybilności|neslibuje kompatibilitu|non promette la compatibilità/);
  assert.match(html, /\/assets\/social\/(?:email|linkedin|reddit|buymeacoffee)\.svg/);
  assert.doesNotMatch(html, /href="mailto:hello@terento\.app"/);
  assert.doesNotMatch(html, /Your device, ready for where you['’]re going|Open source by choice|Open source par choix|Open source od podstaw|Open source jako základ|Open source alla base/);
}

console.log("Public page intro and Download link layout contracts passed for all six locales.");

assert.match(styles, /\.guide-facts span,\s*\.download-badges li\s*\{[^}]*border-radius:\s*999px/);
