"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const locales = new Map([
  ["en", {
    file: path.join(root, "site", "index.html"),
    h1: "Install free maps on your Garmin device",
    hero: "Terento puts free maps from OpenStreetMap projects on Garmin watches and Edge bike computers. Use the Mac app, or install straight from your desktop browser. Free, and the Mac app is open source.",
    experienceLabel: "How it works",
    manageLabel: "Manage maps",
    installStep: "Choose maps from the catalog, or add your own compatible .img map.",
    doneLabel: "Done",
    doneStep: "Your maps are installed and ready to use on your Garmin.",
    manageShowcase: "See what is on your Garmin, update maps when a newer version is out, or remove them. Your original Garmin maps stay untouched.",
    providerTitle: "Pick the map that fits the trip",
    providerCopy: "Choose maps from available providers. Maps are downloaded from each provider's original source.",
    heroCompatibility: "Check compatibility",
    download: "Download for Mac",
    heroDownload: "Download for Mac",
  }],
  ["de", {
    file: path.join(root, "site", "de", "index.html"),
    h1: "Kostenlose Karten auf deinem Garmin-Gerät installieren",
    hero: "Terento bringt kostenlose Karten aus OpenStreetMap-Projekten auf Garmin-Uhren und Edge-Fahrradcomputer. Mit der Mac-App oder direkt im Desktop-Browser. Kostenlos, und die Mac-App ist Open Source.",
    experienceLabel: "So funktioniert es",
    manageLabel: "Karten verwalten",
    installStep: "Wähle Karten aus dem Katalog oder füge deine eigene kompatible .img-Karte hinzu.",
    doneLabel: "Fertig",
    doneStep: "Deine Karten sind installiert und auf deinem Garmin einsatzbereit.",
    manageShowcase: "Sieh, was auf deinem Garmin ist, aktualisiere Karten, sobald eine neuere Version da ist, oder entferne sie. Die Original-Garmin-Karten bleiben unberührt.",
    providerTitle: "Wähle die Karte, die zur Tour passt",
    providerCopy: "Wähle Karten der verfügbaren Anbieter. Karten werden von der Originalquelle des jeweiligen Anbieters geladen.",
    heroCompatibility: "Kompatibilität prüfen",
    download: "Für Mac herunterladen",
    heroDownload: "Für Mac herunterladen",
  }],
  ["fr", {
    file: path.join(root, "site", "fr", "index.html"),
    h1: "Installez des cartes gratuites sur votre appareil Garmin",
    hero: "Terento installe des cartes gratuites issues de projets OpenStreetMap sur les montres Garmin et les compteurs vélo Edge. Avec l’app Mac ou directement dans le navigateur de votre ordinateur. Gratuit, et l’app Mac est open source.",
    experienceLabel: "Comment ça marche",
    manageLabel: "Gérer les cartes",
    installStep: "Choisissez des cartes dans le catalogue ou ajoutez votre propre carte .img compatible.",
    doneLabel: "Terminé",
    doneStep: "Vos cartes sont installées et prêtes à être utilisées sur votre Garmin.",
    manageShowcase: "Voyez ce qui se trouve sur votre Garmin, mettez à jour les cartes quand une nouvelle version sort, ou supprimez-les. Les cartes Garmin d’origine ne sont jamais touchées.",
    providerTitle: "Choisissez la carte adaptée à votre sortie",
    providerCopy: "Choisissez parmi les fournisseurs disponibles. Les cartes sont téléchargées depuis la source d’origine de chaque fournisseur.",
    heroCompatibility: "Vérifier la compatibilité",
    download: "Télécharger pour Mac",
    heroDownload: "Télécharger pour Mac",
  }],
  ["pl", {
    file: path.join(root, "site", "pl", "index.html"),
    h1: "Instaluj darmowe mapy na urządzeniu Garmin",
    hero: "Terento wgrywa darmowe mapy z projektów OpenStreetMap na zegarki Garmin i liczniki rowerowe Edge. W aplikacji na Maca albo prosto z przeglądarki na komputerze. Za darmo, a aplikacja na Maca jest open source.",
    experienceLabel: "Jak to działa",
    manageLabel: "Zarządzaj mapami",
    installStep: "Wybierz mapy z katalogu albo dodaj własną zgodną mapę .img.",
    doneLabel: "Gotowe",
    doneStep: "Twoje mapy są zainstalowane i gotowe do użycia na Twoim Garminie.",
    manageShowcase: "Zobacz, co jest na Twoim Garminie, aktualizuj mapy, gdy pojawi się nowsza wersja, albo je usuń. Oryginalne mapy Garmina pozostają nietknięte.",
    providerTitle: "Wybierz mapę pasującą do wyprawy",
    providerCopy: "Wybieraj mapy od dostępnych dostawców. Mapy są pobierane z oryginalnego źródła każdego dostawcy.",
    heroCompatibility: "Sprawdź kompatybilność",
    download: "Pobierz na Maca",
    heroDownload: "Pobierz na Maca",
  }],
  ["cs", {
    file: path.join(root, "site", "cs", "index.html"),
    h1: "Nainstalujte do zařízení Garmin mapy zdarma",
    hero: "Terento nahraje mapy zdarma z projektů OpenStreetMap do hodinek Garmin a cyklopočítačů Edge. V aplikaci pro Mac, nebo přímo z prohlížeče v počítači. Zdarma, aplikace pro Mac je open source.",
    experienceLabel: "Jak to funguje",
    manageLabel: "Spravovat mapy",
    installStep: "Vybírejte mapy z katalogu podle oblasti nebo přidejte vlastní kompatibilní mapu .img.",
    doneLabel: "Hotovo",
    doneStep: "Vaše mapy jsou nainstalované a připravené k použití ve vašem Garminu.",
    manageShowcase: "Podívejte se, co máte v Garminu, aktualizujte mapy, když vyjde novější verze, nebo je odstraňte. Původních map Garminu se Terento nedotkne.",
    providerTitle: "Vyberte mapu, která sedí k výletu",
    providerCopy: "Vyberte si mapy od dostupných poskytovatelů. Mapy se stahují z původního zdroje každého poskytovatele.",
    heroCompatibility: "Ověřit kompatibilitu",
    download: "Stáhnout pro Mac",
    heroDownload: "Stáhnout pro Mac",
  }],
  ["it", {
    file: path.join(root, "site", "it", "index.html"),
    h1: "Installa mappe gratuite sul tuo dispositivo Garmin",
    hero: "Terento installa mappe gratuite dai progetti OpenStreetMap su orologi Garmin e ciclocomputer Edge. Con l’app per Mac o direttamente dal browser del computer. Gratis, e l’app per Mac è open source.",
    experienceLabel: "Come funziona",
    manageLabel: "Gestisci le mappe",
    installStep: "Scegli le mappe dal catalogo oppure aggiungi la tua mappa .img compatibile.",
    doneLabel: "Fatto",
    doneStep: "Le tue mappe sono installate e pronte per essere usate sul tuo Garmin.",
    manageShowcase: "Vedi cosa c’è sul tuo Garmin, aggiorna le mappe quando esce una nuova versione o rimuovile. Le mappe Garmin originali restano intatte.",
    providerTitle: "Scegli la mappa adatta al percorso",
    providerCopy: "Scegli mappe dei provider disponibili. Le mappe vengono scaricate dalla fonte originale di ciascun provider.",
    heroCompatibility: "Verifica la compatibilità",
    download: "Scarica per Mac",
    heroDownload: "Scarica per Mac",
  }],
]);

const appStoreBadge = JSON.parse(fs.readFileSync(path.join(root, "scripts", "templates", "app-store-badge.json"), "utf8"));
const pageFor = (locale) => fs.readFileSync(locales.get(locale).file, "utf8");
const classTokens = (classValue) => new Set(classValue.trim().split(/\s+/));
const anchorFor = (page, className) => {
  const escapedClass = className.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = page.match(new RegExp(
    `<a class="([^"]*\\b${escapedClass}\\b[^"]*)" href="([^"]+)"([^>]*)>([\\s\\S]*?)</a>`
  ));
  assert.ok(match, `missing ${className} CTA`);
  // The Download button carries a decorative icon (aria-hidden SVG) before its label.
  return { classes: classTokens(match[1]), href: match[2], attributes: match[3], label: match[4].replace(/<svg[\s\S]*?<\/svg>/g, "").replace(/<[^>]+>/g, "").trim() };
};

for (const [locale, expected] of locales) {
  const page = pageFor(locale);
  assert.match(page, /<link rel="stylesheet" href="\/styles\.css\?v=20261119-site-refresh-v9">/, `${locale}: Home stylesheet cache bust`);
  assert.match(page, /<script defer src="\/home-features\.js\?v=20261105-home-map-switch-v4"><\/script>/, `${locale}: Home feature script cache bust`);
  assert.match(page, /installing-maps-1600\.png\?v=20261120-app-screens-v3/, `${locale}: installation screenshot cache bust`);
  const heroDevice = page.match(/<figure class="home-device" data-map-switch>[\s\S]*?<\/figure>/)?.[0];
  assert.ok(heroDevice, `${locale}: hero shows the drawn watch with a real map`);
  assert.match(heroDevice, /<img class="home-watch-map" data-map-image src="\/assets\/home\/hero-opentopomap\.webp\?v=[^"]+" width="520" height="520" alt="[^"]+" fetchpriority="high"/);
  assert.match(heroDevice, /<img class="home-watch-body" src="\/assets\/home\/watch-front\.webp\?v=[^"]+"[^>]* alt=""/);
  assert.match(heroDevice, /<img class="home-watch-body"[^>]* srcset="\/assets\/home\/watch-front-680\.webp\?v=[^"]+ 680w, [^"]+ 1080w"[^>]* fetchpriority="high"/, `${locale}: watch frame loads with the map`);
  assert.equal((heroDevice.match(/<button type="button" class="home-switch-button" data-map-style="[a-z]+"[^>]*aria-pressed="(?:true|false)"[^>]*>/g) || []).length, 3, `${locale}: three map styles`);
  assert.equal((heroDevice.match(/aria-pressed="true"/g) || []).length, 1);
  assert.doesNotMatch(heroDevice, /data-map-attribution/, `${locale}: owner removed the visible hero map credit`);
  for (const style of ["opentopomap", "freizeitkarte", "maprando"]) {
    assert.ok(fs.existsSync(path.join(root, "site", "assets", "home", `hero-${style}.webp`)), `hero-${style}.webp exists`);
  }
  const h1 = page.match(/<h1 id="hero-title">([^<]+)<\/h1>/);
  assert.ok(h1, `${locale}: missing hero H1`);
  assert.equal(h1[1], expected.h1, `${locale}: hero H1 copy`);
  const hero = page.match(/<p class="hero-lede">([^<]+)<\/p>/);
  assert.ok(hero, `${locale}: missing hero lede`);
  assert.equal(hero[1], expected.hero, `${locale}: hero lede copy`);
  assert.doesNotMatch(page, /class="hero-requirement"|class="hero-status"/, `${locale}: Hero must not repeat platform or Beta status`);

  const download = anchorFor(page, "hero-download-action");
  const heroCompatibility = anchorFor(page, "hero-compatibility-link");
  assert.doesNotMatch(page, /final-cta/, `${locale}: the closing download block was removed (owner 2026-11-13)`);
  const experience = page.match(/<section class="block home-how" id="how-it-works"[\s\S]*?<\/section>/)?.[0];
  assert.ok(experience);
  assert.equal(experience.match(/<h2 id="steps-title">([^<]+)<\/h2>/)?.[1], expected.experienceLabel);
  const steps = [...experience.matchAll(/<li>([\s\S]*?)<\/li>/g)];
  assert.equal(steps.length, 3);
  assert.equal(steps[1][1].match(/<p>([^<]+)<\/p>\s*$/)?.[1], expected.installStep);
  assert.equal(steps[2][1].match(/<h3>([^<]+)<\/h3>/)?.[1], expected.doneLabel);
  assert.equal(steps[2][1].match(/<p>([^<]+)<\/p>\s*$/)?.[1], expected.doneStep);
  // Round 5 (owner 2026-11-19): no feature cards. "Manage maps" and "Safe for your Garmin" are gone
  // (safety moved to the FAQ); Edge is its own full-width two-column section.
  assert.doesNotMatch(page, /class="block home-features|home-feature--|manage-title|safety-title/, `${locale}: no feature cards on Home`);
  assert.doesNotMatch(page, /class="map-feature-section"|role="tablist"|class="eyebrow"/, `${locale}: no tabs or eyebrow labels on Home`);
  assert.equal((experience.match(/<figure class="col-8 app-shot app-shot--feature">/g) || []).length, 1);
  assert.match(experience, /width="2358" height="1575"/);
  for (const url of experience.match(/\/assets\/app\/optimized\/[^"\s,]+/g) || []) {
    assert.ok(url.startsWith("/assets/app/optimized/install-maps-"));
    assert.ok(url.endsWith("?v=20261120-app-screens-v3"), `${locale}: screenshot cache version`);
  }
  const edge = page.match(/<section class="block home-edge" id="edge" aria-labelledby="edge-title">[\s\S]*?<\/section>/)?.[0];
  assert.ok(edge, `${locale}: Garmin Edge section`);
  assert.match(edge, /<div class="shell home-edge-grid">\s*<figure class="home-device home-edge-figure" data-map-switch>[\s\S]*?class="home-switch"[\s\S]*?<\/figure>\s*<div class="home-edge-copy">\s*<h2 id="edge-title">[^<]+<\/h2>\s*<p>[^<]*Edge 540, 840[^<]*<\/p>/, `${locale}: Edge device first, then H2 and the sentence; the same map switch as the hero`);
  assert.doesNotMatch(edge, /class="card/, `${locale}: Edge section has no card`);
  if (locale === "en") assert.match(edge, /<h2 id="edge-title">On the bike, too<\/h2>[\s\S]*>Read the Garmin Edge guide<\/a>/);
  assert.match(edge, new RegExp(`href="${locale === "en" ? "" : `/${locale}`}/guides/install-garmin-maps-edge-mac/" data-umami-event="guide-link-click" data-umami-event-location="home-edge"`));
  // Home ends with the FAQ: no closing call to action.
  assert.doesNotMatch(page, /class="cta-band|end-cta|data-umami-event-location="home-bottom"/, `${locale}: no end CTA on Home`);
  assert.match(page, /<section class="faq section" id="faq"[\s\S]*?<\/section>\s*<\/main>/, `${locale}: Home ends at the FAQ`);
  // Round 4 (owner): computer actions are "Download for Mac" + "Install from your browser"; phones get
  // "Send this link to your computer" + "Check compatibility". Round 5: one App Store badge, in the Mac app card.
  const computerActions = page.match(/<div class="hero-actions home-actions home-actions--computer">[\s\S]*?<\/div>/)?.[0];
  assert.ok(computerActions, `${locale}: computer hero actions`);
  assert.match(computerActions, /^<div[^>]*><a class="download-action download-action--store hero-download-action"[^>]*data-umami-event="download-cta-click" data-umami-event-location="home-hero">[\s\S]*?<\/a><a class="button-secondary hero-web-installer-link" href="[^"]*\/install\/" data-umami-event="web-installer-link-click" data-umami-event-location="home-hero">/);
  const phoneActions = page.match(/<div class="hero-actions home-actions home-actions--phone">[\s\S]*?<\/div>/)?.[0];
  assert.ok(phoneActions, `${locale}: phone hero actions`);
  assert.match(phoneActions, /data-umami-event="send-to-computer-click" data-umami-event-location="home-hero"[\s\S]*?<a class="text-link hero-compatibility-link"/);
  assert.equal((page.match(/class="app-store-badge/g) || []).length, 1, `${locale}: one App Store badge on Home`);
  assert.doesNotMatch(computerActions + phoneActions, /app-store-badge/, `${locale}: no badge in the hero`);
  assert.doesNotMatch(page, /home-hero-note|home-hero-browser|home-send-link/, `${locale}: no text under the hero buttons`);
  const providerSection = page.match(/<section class="block home-providers"[\s\S]*?<\/section>/)?.[0];
  assert.ok(providerSection, `${locale}: missing provider cards section`);
  assert.match(providerSection, new RegExp(`<h2 id="providers-title">${expected.providerTitle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}<\\/h2>`));
  assert.match(providerSection, new RegExp(`<p class="provider-copy">${expected.providerCopy.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}<\\/p>`));
  assert.equal((providerSection.match(/<article class="provider-card[ "]/g) || []).length, 5, `${locale}: one card per provider`);
  const osmapa = providerSection.match(/<article class="provider-card[^"]*" data-provider-card="osmapa" hidden>[\s\S]*?<\/article>/)?.[0];
  assert.ok(osmapa, `${locale}: OSMapaPL stays hidden until the catalog lists it as active`);
  assert.ok(osmapa.includes("<h3>OSMapaPL</h3>"));
  assert.match(osmapa, /data-provider-count[^>]* hidden><\/p>/);
  const maprando = providerSection.match(/<article class="provider-card[^"]*" data-provider-card="maprando">[\s\S]*?<\/article>/)?.[0];
  assert.ok(maprando, `${locale}: MapRando card`);
  assert.match(maprando, /class="provider-language-note"><span aria-hidden="true">ⓘ<\/span><span>[^<]+<\/span><\/p>/);
  assert.match(maprando, /data-provider-count[^>]* hidden><\/p>/);
  assert.match(maprando, /OpenStreetMap/);
  const bbbike = providerSection.match(/<article class="provider-card[^"]*" data-provider-card="bbbike" hidden>[\s\S]*?<\/article>/)?.[0];
  assert.ok(bbbike, `${locale}: one BBBike card, hidden until the catalog lists BBBike`);
  assert.ok(bbbike.includes("<h3>BBBike</h3>"));
  assert.doesNotMatch(providerSection, /data-provider-type=/, `${locale}: BBBike variants share one card`);
  const otm = providerSection.match(/<article class="provider-card[^"]*" data-provider-card="opentopomap">[\s\S]*?<\/article>/)?.[0];
  assert.ok(otm, `${locale}: OpenTopoMap card`);
  assert.match(otm, /<details class="provider-addon" data-provider-addon="contours">\s*<summary class="provider-addon-toggle">/);
  assert.doesNotMatch(otm, /<details[^>]*\bopen(?:\s|=|>)/);
  assert.match(otm, /<summary[^>]*>[\s\S]*provider-card-badge[\s\S]*provider-addon-title[\s\S]*<\/summary>\s*<p class="provider-addon-copy">/);
  assert.doesNotMatch(providerSection, /data-provider-card="opentopomap-contours"|type="checkbox"|role="switch"/);
  assert.equal((providerSection.match(/class="provider-benefits"/g) || []).length, 5);
  assert.equal((providerSection.match(/<li>/g) || []).length, 15);
  for (const list of providerSection.matchAll(/<ul class="provider-benefits">([\s\S]*?)<\/ul>/g)) {
    assert.equal((list[1].match(/<li>/g) || []).length, 3, `${locale}: exactly three benefits per map`);
  }
  assert.equal((providerSection.match(/class="provider-summary"/g) || []).length, 5);
  assert.doesNotMatch(providerSection, /data-provider-previous|data-provider-next/);
  // Round 6 (owner): "Compare map styles live" is a card in the grid's last row (no separate row under it);
  // href and Umami event unchanged. Its span fills the row: 3 visible providers in the static HTML.
  assert.doesNotMatch(providerSection, /class="provider-compare"/, `${locale}: no full-width Compare row`);
  const compareCard = providerSection.match(/<div class="grid home-provider-grid"[\s\S]*?(<article class="card card--media home-compare-card" data-compare-card data-span="(\d)">[\s\S]*?<\/article>)\s*<\/div>/);
  assert.ok(compareCard, `${locale}: Compare card is the last item of the provider grid`);
  assert.equal(compareCard[2], String(3 - ((providerSection.match(/<article class="provider-card[^"]*" data-provider-card="[^"]+">/g) || []).length % 3)), `${locale}: Compare card fills the last row`);
  assert.match(compareCard[1], new RegExp(`<div class="card-media home-compare-media"><img src="/assets/home/maps-[a-z-]+\\.webp[^"]*"[^>]*><img src="/assets/home/maps-[a-z-]+\\.webp[^"]*"[^>]*></div>[\\s\\S]*<h3><a class="home-compare-link" href="${locale === "en" ? "" : `/${locale}`}/map-styles/" data-umami-event="maps-link-click" data-umami-event-location="home-providers">[^<]+</a></h3>\\s*<p class="home-compare-line">[^<]+</p>`));
  assert.match(page, /provider-list\.js\?v=20261119-compare-card-v1/);
  assert.match(fs.readFileSync(path.join(root, "site", "provider-list.js"), "utf8"), /compare\.dataset\.span = String\(3 - \(cards\.filter\(\(card\) => !card\.hidden\)\.length % 3\)\)/, "provider-list.js keeps the Compare card filling the last row");
  assert.match(providerSection, /data-count-template="[^"]*\{count\}[^"]*"/);
  assert.match(providerSection, /63/);
  assert.match(providerSection, /177/);
  assert.match(providerSection, /157/);
  const cardFragments = [...providerSection.matchAll(/<article class="provider-card"[\s\S]*?<\/article>/g)].map((match) => match[0]);
  cardFragments.forEach((card, index) => {
    assert.doesNotMatch(card, /license|licen[cs]|source|download/i, `${locale}: provider card ${index + 1} avoids technical/legal copy`);
  });
  assert.doesNotMatch(page, /class="scope-section"|class="scope-link"|id="scope-title"|>Beta scope<|Available today|Choose a map and get moving/i, `${locale}: removed Beta scope and stale provider copy`);
  assert.ok(download.classes.has("download-action"), `${locale}: hero Download CTA uses the solid action style`);
  assert.equal(download.label, expected.heroDownload, `${locale}: download CTA label`);
  assert.ok(heroCompatibility.classes.has("text-link"), `${locale}: Hero Compatibility CTA uses the shared text-link style`);
  assert.ok(heroCompatibility.classes.has("hero-compatibility-link"), `${locale}: Hero Compatibility CTA uses its layout modifier`);
  assert.equal(heroCompatibility.label, expected.heroCompatibility, `${locale}: Hero Compatibility CTA label`);
  assert.equal(heroCompatibility.href, locale === "en" ? "/compatibility/" : `/${locale}/compatibility/`, `${locale}: Hero Compatibility CTA href`);
  assert.match(heroCompatibility.attributes, /data-umami-event="compatibility-link-click"/);
  assert.match(heroCompatibility.attributes, /data-umami-event-location="home-hero"/);
  assert.doesNotMatch(page, /<p class="hero-lede">[^<]*Freizeitkarte/i, `${locale}: hero copy is provider-neutral`);
  assert.doesNotMatch(page, /back up|backup|sauvegarder|zálohovat|wykonać kopię|eseguire il backup/i, `${locale}: no backup marketing copy`);
  assert.doesNotMatch(page, /beta[ .]?8|bêta 8/i, `${locale}: no stale beta.8 copy`);
}

const englishHome = pageFor("en");
assert.match(englishHome, /<p class="hero-lede">Terento puts free maps from OpenStreetMap projects on Garmin watches and Edge bike computers\. Use the Mac app, or install straight from your desktop browser\. Free, and the Mac app is open source\.<\/p>/);
assert.match(englishHome, /<h1 id="hero-title">Install free maps on your Garmin device<\/h1>/);
assert.doesNotMatch(englishHome, /<p class="hero-lede">[^<]*Freizeitkarte/i);
assert.match(englishHome, /<meta name="description" content="Install free OpenTopoMap, Freizeitkarte and other OpenStreetMap maps on Garmin watches and Edge bike computers\. Free Mac app or web installer\.">/);
assert.doesNotMatch(englishHome, /class="status-dot"/);
assert.doesNotMatch(englishHome, /Compatibility varies by Garmin model\./);

const styles = fs.readFileSync(path.join(root, "site", "styles.css"), "utf8");
const sharedTextLink = [...styles.matchAll(/\.text-link\s*\{([^}]*)\}/g)]
  .find((match) => /display:\s*inline-flex/.test(match[1]));
assert.ok(sharedTextLink, "missing shared .text-link style block");
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
const desktopNavLinks = styles.match(/\.primary-nav a,\s*\.footer-nav a\s*\{([^}]*)\}/s);
assert.ok(desktopNavLinks, "missing desktop navigation hit-area block");
assert.match(desktopNavLinks[1], /display: inline-flex/);
assert.match(desktopNavLinks[1], /align-items: center/);
assert.match(desktopNavLinks[1], /min-height: 40px/);
const aboutSocialLink = styles.match(/\.about-social-link\s*\{([^}]*)\}/s);
assert.ok(aboutSocialLink, "missing About social-link style block");
assert.match(aboutSocialLink[1], /min-height: 40px/);
assert.match(styles, /\.compatibility-summary-line strong\s*\{[^}]*font-variant-numeric: tabular-nums/s);
assert.match(styles, /\.compatibility-results-count\s*\{[^}]*font-variant-numeric: tabular-nums/s);
assert.match(styles, /\.watch-install-count\s*\{[^}]*font-variant-numeric: tabular-nums/s);
assert.match(styles, /summary:not\(\.language-trigger\)::after\s*\{[^}]*border-right: 1\.5px solid currentColor[^}]*transition: transform 160ms ease-out/s);
assert.match(styles, /\.text-link:hover\s*\{[^}]*color: var\(--link-text-hover\)/s);
// One class for the Download button beside Apple's badge (Home hero and /download/, owner 2026-11-19):
// 40px tall like the badge, natural width, 10px radius, 15px/600 label, 44px touch target via ::after.
const heroAction = styles.match(/\.download-action--store\s*\{([^}]*)\}/s);
assert.ok(heroAction, "missing Hero Download CTA sizing block");
assert.match(heroAction[1], /\bheight:\s*40px/);
assert.match(heroAction[1], /width:\s*auto/);
assert.match(heroAction[1], /padding:\s*0 16px/);
assert.match(heroAction[1], /border-radius:\s*var\(--control-radius\)/);
assert.match(styles, /--control-radius:\s*10px/);
assert.match(heroAction[1], /font-size:\s*15px/);
assert.match(heroAction[1], /font-weight:\s*600/);
assert.doesNotMatch(heroAction[1], /box-shadow/);
assert.match(styles, /\.download-action--store::after\s*\{[^}]*inset:\s*-2px 0/s);
assert.match(styles, /\.download-action-icon\s*\{[^}]*width:\s*18px[^}]*height:\s*18px/s);
assert.match(styles, /@media \(max-width: 560px\)\s*\{\s*\.store-actions\s*\{[^}]*flex-direction:\s*column[^}]*align-items:\s*center/s, "button above badge, centred, at natural width");
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
assert.match(styles, /\.steps > li::before\s*\{[^}]*content:\s*counter\(steps\)/s);
assert.match(styles, /\.section-heading h2 span\s*\{[^}]*color:\s*var\(--sky\)[^}]*font-family:\s*var\(--font-ui\)/s);
assert.match(styles, /\.provider-cards\s*\{[^}]*grid-auto-flow:\s*column/s);
assert.match(styles, /\.provider-card\s*\{[^}]*background:\s*var\(--surface\)/s);
assert.match(styles, /\.provider-addon\s*\{[^}]*border-top:\s*1px solid var\(--border\)/s);
assert.match(styles, /\.provider-cards\s*\{[^}]*align-items:\s*stretch/s);
assert.match(styles, /\.provider-card-badge\s*\{[^}]*text-transform:\s*none/s);
assert.match(styles, /\.provider-benefits\s*\{[^}]*border-top:\s*1px solid var\(--border\)/s);
assert.ok(!fs.existsSync(path.join(root, "site/localized-content.js")), "Home copy is generated, not rewritten in the browser");

console.log("Home copy, localized Hero, shared CTA, and CTA interaction-contract tests passed.");

assert.match(englishHome, /Add lines that show elevation and help you read slopes\./);
assert.match(styles, /grid-auto-columns: min\(90%, 420px\)/);
assert.match(styles, /\.provider-cards\s*\{[^}]*max-width: 1300px/s);
assert.match(styles, /overflow-x: auto/);

// Round 5 (owner 2026-11-19): the Mac app card has "Download for Mac" with the official Mac App Store
// badge under it (location home-section); the web installer card has one button. Same height.
for (const [locale] of locales) {
  const html = pageFor(locale);
  assert.equal((html.match(/class="app-store-badge/g) || []).length, 1, `${locale}: one App Store badge on Home`);
  const ways = [...html.matchAll(/<article class="card col-6 home-way">([\s\S]*?)<\/article>/g)].map(match => match[1]);
  assert.equal(ways.length, 2, `${locale}: two ways`);
  for (const way of ways) {
    assert.match(way, /^\s*<div class="home-feature-visual"><svg[\s\S]*?<\/svg><\/div>\s*<h3>[^<]+<\/h3>\s*<p>[^<]+<\/p>\s*<div class="card-action home-way-actions"><a class="[^"]+"[^>]*>[\s\S]*?<\/a>(?:<a class="app-store-badge home-app-store"[^>]*><img [^>]+><\/a>)?<\/div>\s*$/, `${locale}: way card`);
  }
  assert.match(ways[0], /<a class="download-action download-action--store" href="[^"]+" data-umami-event="download-cta-click" data-umami-event-location="home-section">[\s\S]*?<\/a><a class="app-store-badge home-app-store" href="https:\/\/apps\.apple\.com\/[^"]*ct=site-home[^"]*" data-umami-event="app-store-click" data-umami-event-location="home-section"><img src="\/assets\/app-store\/[^"]+" width="\d+" height="40" alt="[^"]+"(?: lang="en")?><\/a><\/div>/, `${locale}: Mac card badge under Download for Mac`);
  assert.match(ways[1], /<a class="button-secondary" href="[^"]*\/install\/" data-umami-event="web-installer-link-click" data-umami-event-location="home-section">/);
  assert.doesNotMatch(ways[1], /app-store-badge/, `${locale}: no badge in the web installer card`);
}
assert.match(styles, /\.home-way \.home-way-actions\s*\{\s*margin-top:\s*auto;/, "Way card buttons line up at the bottom");
