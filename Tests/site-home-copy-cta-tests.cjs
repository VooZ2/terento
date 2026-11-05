"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const locales = new Map([
  ["en", {
    file: path.join(root, "site", "index.html"),
    h1: "Install free maps on your Garmin",
    hero: "Terento puts free maps from OpenStreetMap projects on Garmin watches and Edge bike computers. Use the Mac app, or install straight from your desktop browser. Free and open source.",
    experienceLabel: "How it works",
    manageLabel: "Manage maps",
    installStep: "Choose maps from the catalog, or add your own compatible .img map.",
    doneLabel: "Done",
    doneStep: "Your maps are installed and ready to use on your Garmin.",
    manageShowcase: "See what's installed, update maps when newer releases are available, and remove third-party maps managed by Terento. Original Garmin maps remain protected.",
    providerTitle: "Pick the map that fits the trip",
    providerCopy: "Choose maps from available providers. Maps are downloaded from each provider's original source.",
    heroCompatibility: "Check compatibility",
    download: "Download for Mac",
    heroDownload: "Download for Mac",
  }],
  ["de", {
    file: path.join(root, "site", "de", "index.html"),
    h1: "Kostenlose Karten auf deinem Garmin installieren",
    hero: "Terento bringt kostenlose Karten aus OpenStreetMap-Projekten auf Garmin-Uhren und Edge-Fahrradcomputer. Mit der Mac-App oder direkt im Desktop-Browser. Kostenlos und Open Source.",
    experienceLabel: "So funktioniert es",
    manageLabel: "Karten verwalten",
    installStep: "Wähle Karten aus dem Katalog oder füge deine eigene kompatible .img-Karte hinzu.",
    doneLabel: "Fertig",
    doneStep: "Deine Karten sind installiert und auf deinem Garmin einsatzbereit.",
    manageShowcase: "Sieh, was installiert ist, aktualisiere Karten, wenn neuere Versionen verfügbar sind, und entferne von Terento verwaltete Drittanbieter-Karten. Originale Garmin-Karten bleiben geschützt.",
    providerTitle: "Wähle die Karte, die zur Tour passt",
    providerCopy: "Wähle Karten der verfügbaren Anbieter. Karten werden von der Originalquelle des jeweiligen Anbieters geladen.",
    heroCompatibility: "Kompatibilität prüfen",
    download: "Für Mac herunterladen",
    heroDownload: "Für Mac herunterladen",
  }],
  ["fr", {
    file: path.join(root, "site", "fr", "index.html"),
    h1: "Installez des cartes gratuites sur votre Garmin",
    hero: "Terento installe des cartes gratuites issues de projets OpenStreetMap sur les montres Garmin et les compteurs vélo Edge. Avec l’app Mac ou directement dans le navigateur de votre ordinateur. Gratuit et open source.",
    experienceLabel: "Comment ça marche",
    manageLabel: "Gérer les cartes",
    installStep: "Choisissez des cartes dans le catalogue ou ajoutez votre propre carte .img compatible.",
    doneLabel: "Terminé",
    doneStep: "Vos cartes sont installées et prêtes à être utilisées sur votre Garmin.",
    manageShowcase: "Consultez les cartes installées, mettez-les à jour lorsqu’une version plus récente est disponible et supprimez les cartes tierces gérées par Terento. Les cartes Garmin d’origine restent protégées.",
    providerTitle: "Choisissez la carte adaptée à votre sortie",
    providerCopy: "Choisissez parmi les fournisseurs disponibles. Les cartes sont téléchargées depuis la source d’origine de chaque fournisseur.",
    heroCompatibility: "Vérifier la compatibilité",
    download: "Télécharger pour Mac",
    heroDownload: "Télécharger pour Mac",
  }],
  ["pl", {
    file: path.join(root, "site", "pl", "index.html"),
    h1: "Instaluj darmowe mapy na swoim Garminie",
    hero: "Terento wgrywa darmowe mapy z projektów OpenStreetMap na zegarki Garmin i liczniki rowerowe Edge. W aplikacji na Maca albo prosto z przeglądarki na komputerze. Za darmo i open source.",
    experienceLabel: "Jak to działa",
    manageLabel: "Zarządzaj mapami",
    installStep: "Wybierz mapy z katalogu albo dodaj własną zgodną mapę .img.",
    doneLabel: "Gotowe",
    doneStep: "Twoje mapy są zainstalowane i gotowe do użycia na Twoim Garminie.",
    manageShowcase: "Sprawdź, co jest zainstalowane, aktualizuj mapy, gdy dostępne są nowsze wydania, i usuwaj mapy innych firm zarządzane przez Terento. Oryginalne mapy Garmin pozostają chronione.",
    providerTitle: "Wybierz mapę pasującą do wyprawy",
    providerCopy: "Wybieraj mapy od dostępnych dostawców. Mapy są pobierane z oryginalnego źródła każdego dostawcy.",
    heroCompatibility: "Sprawdź kompatybilność",
    download: "Pobierz na Maca",
    heroDownload: "Pobierz na Maca",
  }],
  ["cs", {
    file: path.join(root, "site", "cs", "index.html"),
    h1: "Nainstalujte do svého Garminu mapy zdarma",
    hero: "Terento nahraje mapy zdarma z projektů OpenStreetMap do hodinek Garmin a cyklopočítačů Edge. V aplikaci pro Mac, nebo přímo z prohlížeče v počítači. Zdarma a open source.",
    experienceLabel: "Jak to funguje",
    manageLabel: "Spravovat mapy",
    installStep: "Vybírejte mapy z katalogu podle oblasti nebo přidejte vlastní kompatibilní mapu .img.",
    doneLabel: "Hotovo",
    doneStep: "Vaše mapy jsou nainstalované a připravené k použití ve vašem Garminu.",
    manageShowcase: "Prohlédněte si nainstalované mapy, aktualizujte je, když je k dispozici novější vydání, a odstraňte mapy třetích stran spravované aplikací Terento. Původní mapy Garmin zůstávají chráněné.",
    providerTitle: "Vyberte mapu, která sedí k výletu",
    providerCopy: "Vyberte si mapy od dostupných poskytovatelů. Mapy se stahují z původního zdroje každého poskytovatele.",
    heroCompatibility: "Ověřit kompatibilitu",
    download: "Stáhnout pro Mac",
    heroDownload: "Stáhnout pro Mac",
  }],
  ["it", {
    file: path.join(root, "site", "it", "index.html"),
    h1: "Installa mappe gratuite sul tuo Garmin",
    hero: "Terento installa mappe gratuite dai progetti OpenStreetMap su orologi Garmin e ciclocomputer Edge. Con l’app per Mac o direttamente dal browser del computer. Gratis e open source.",
    experienceLabel: "Come funziona",
    manageLabel: "Gestisci le mappe",
    installStep: "Scegli le mappe dal catalogo oppure aggiungi la tua mappa .img compatibile.",
    doneLabel: "Fatto",
    doneStep: "Le tue mappe sono installate e pronte per essere usate sul tuo Garmin.",
    manageShowcase: "Visualizza le mappe installate, aggiornatele quando è disponibile una versione più recente e rimuovi le mappe di terze parti gestite da Terento. Le mappe Garmin originali restano protette.",
    providerTitle: "Scegli la mappa adatta al percorso",
    providerCopy: "Scegli mappe dei provider disponibili. Le mappe vengono scaricate dalla fonte originale di ciascun provider.",
    heroCompatibility: "Verifica la compatibilità",
    download: "Scarica per Mac",
    heroDownload: "Scarica per Mac",
  }],
]);

const pageFor = (locale) => fs.readFileSync(locales.get(locale).file, "utf8");
const classTokens = (classValue) => new Set(classValue.trim().split(/\s+/));
const anchorFor = (page, className) => {
  const escapedClass = className.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = page.match(new RegExp(
    `<a class="([^"]*\\b${escapedClass}\\b[^"]*)" href="([^"]+)"([^>]*)>([^<]+)</a>`
  ));
  assert.ok(match, `missing ${className} CTA`);
  return { classes: classTokens(match[1]), href: match[2], attributes: match[3], label: match[4].trim() };
};

for (const [locale, expected] of locales) {
  const page = pageFor(locale);
  assert.match(page, /<link rel="stylesheet" href="\/styles\.css\?v=20261105-type-scale-v1">/, `${locale}: Home stylesheet cache bust`);
  assert.match(page, /<script defer src="\/home-features\.js\?v=20261105-home-map-switch-v4"><\/script>/, `${locale}: Home feature script cache bust`);
  assert.match(page, /installing-maps-1600\.png\?v=20260912-app-screens-v2/, `${locale}: installation screenshot cache bust`);
  const heroDevice = page.match(/<figure class="home-device" data-map-switch>[\s\S]*?<\/figure>/)?.[0];
  assert.ok(heroDevice, `${locale}: hero shows the drawn watch with a real map`);
  assert.match(heroDevice, /<img class="home-watch-map" data-map-image src="\/assets\/home\/hero-opentopomap\.webp\?v=[^"]+" width="520" height="520" alt="[^"]+" fetchpriority="high"/);
  assert.match(heroDevice, /<img class="home-watch-body" src="\/assets\/home\/watch-front\.webp\?v=[^"]+"[^>]* alt=""/);
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
  const finalCta = page.match(/<section class="final-cta"[\s\S]*?<\/section>/)?.[0];
  assert.ok(finalCta, `${locale}: missing final CTA`);
  const finalDownload = finalCta.match(/<a class="download-action[^"]*"[^>]*>([^<]+)(?:<span aria-hidden="true">([^<]+)<\/span>)?<\/a>/);
  assert.ok(finalDownload, `${locale}: missing final CTA download button`);
  assert.equal(finalDownload[1].trim(), expected.download, `${locale}: final CTA download label`);
  assert.equal(finalDownload[2] || "", "", `${locale}: final CTA has no decorative arrow`);
  assert.doesNotMatch(finalCta, /beta|bêta|betę|betu/i, `${locale}: final CTA avoids beta-specific button copy`);
  const experience = page.match(/<section class="home-steps section" id="how-it-works"[\s\S]*?<\/section>/)?.[0];
  assert.ok(experience);
  assert.equal(experience.match(/<h2 id="steps-title">([^<]+)<\/h2>/)?.[1], expected.experienceLabel);
  const steps = [...experience.matchAll(/<li class="step">([\s\S]*?)<\/li>/g)];
  assert.equal(steps.length, 3);
  assert.equal(steps[1][1].match(/<p>([^<]+)<\/p>\s*$/)?.[1], expected.installStep);
  assert.equal(steps[2][1].match(/<h3>([^<]+)<\/h3>/)?.[1], expected.doneLabel);
  assert.equal(steps[2][1].match(/<p>([^<]+)<\/p>\s*$/)?.[1], expected.doneStep);
  const manage = page.match(/<section class="home-manage section"[\s\S]*?<\/section>/)?.[0];
  assert.ok(manage, `${locale}: missing manage maps section`);
  assert.equal(manage.match(/<h2 id="manage-title">([^<]+)<\/h2>/)?.[1], expected.manageLabel);
  assert.equal(manage.match(/<h2 id="manage-title">[^<]+<\/h2>\s*<p>([^<]+)<\/p>/)?.[1], expected.manageShowcase);
  assert.doesNotMatch(page, /class="map-feature-section"|role="tablist"|class="eyebrow"/, `${locale}: no tabs or eyebrow labels on Home`);
  for (const [section, stem] of [[experience, "install-maps"], [manage, "manage-maps"]]) {
    assert.equal((section.match(/<figure class="app-shot app-shot--feature">/g) || []).length, 1);
    assert.match(section, /width="2358" height="1575"/);
    for (const url of section.match(/\/assets\/app\/optimized\/[^"\s,]+/g) || []) {
      assert.ok(url.startsWith(`/assets/app/optimized/${stem}-`));
      assert.ok(url.endsWith("?v=20260912-app-screens-v2"), `${locale}: screenshot cache version`);
    }
  }
  const edge = page.match(/<section class="home-edge section" id="edge"[\s\S]*?<\/section>/)?.[0];
  assert.ok(edge, `${locale}: Garmin Edge section`);
  assert.match(edge, /Edge 540, 840/);
  assert.match(edge, new RegExp(`href="${locale === "en" ? "" : `/${locale}`}/guides/install-garmin-maps-edge-mac/" data-umami-event="guide-link-click" data-umami-event-location="home-edge"`));
  assert.doesNotMatch(page, /class="home-app-store"/, `${locale}: App Store button waits for the approved listing`);
  const providerSection = page.match(/<section class="provider-section section"[\s\S]*?<\/section>/)?.[0];
  assert.ok(providerSection, `${locale}: missing provider cards section`);
  assert.match(providerSection, new RegExp(`<h2 id="providers-title">${expected.providerTitle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}<\\/h2>`));
  assert.match(providerSection, new RegExp(`<p class="provider-copy">${expected.providerCopy.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}<\\/p>`));
  assert.equal((providerSection.match(/<article class="provider-card"/g) || []).length, 5, `${locale}: one card per provider`);
  const osmapa = providerSection.match(/<article class="provider-card" data-provider-card="osmapa" hidden>[\s\S]*?<\/article>/)?.[0];
  assert.ok(osmapa, `${locale}: OSMapaPL stays hidden until the catalog lists it as active`);
  assert.ok(osmapa.includes("<h3>OSMapaPL</h3>"));
  assert.match(osmapa, /data-provider-count[^>]* hidden><\/p>/);
  const maprando = providerSection.match(/<article class="provider-card" data-provider-card="maprando">[\s\S]*?<\/article>/)?.[0];
  assert.ok(maprando, `${locale}: MapRando card`);
  assert.match(maprando, /class="provider-language-note"><span aria-hidden="true">ⓘ<\/span><span>[^<]+<\/span><\/p>/);
  assert.match(maprando, /data-provider-count[^>]* hidden><\/p>/);
  assert.match(maprando, /OpenStreetMap/);
  const bbbike = providerSection.match(/<article class="provider-card" data-provider-card="bbbike" hidden>[\s\S]*?<\/article>/)?.[0];
  assert.ok(bbbike, `${locale}: one BBBike card, hidden until the catalog lists BBBike`);
  assert.ok(bbbike.includes("<h3>BBBike</h3>"));
  assert.doesNotMatch(providerSection, /data-provider-type=/, `${locale}: BBBike variants share one card`);
  const otm = providerSection.match(/<article class="provider-card" data-provider-card="opentopomap">[\s\S]*?<\/article>/)?.[0];
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
  assert.match(providerSection, new RegExp(`<p class="provider-compare"><a class="text-link" href="${locale === "en" ? "" : `/${locale}`}/map-styles/"`));
  assert.match(page, /provider-list\.js\?v=20261026-osmapa-v1/);
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
  assert.match(page, /<div class="home-actions"><a class="download-action hero-download-action"[\s\S]*?<a class="text-link hero-compatibility-link"/);
  assert.doesNotMatch(page, /<p class="hero-lede">[^<]*Freizeitkarte/i, `${locale}: hero copy is provider-neutral`);
  assert.doesNotMatch(page, /back up|backup|sauvegarder|zálohovat|wykonać kopię|eseguire il backup/i, `${locale}: no backup marketing copy`);
  assert.doesNotMatch(page, /beta[ .]?8|bêta 8/i, `${locale}: no stale beta.8 copy`);
}

const englishHome = pageFor("en");
assert.match(englishHome, /<p class="hero-lede">Terento puts free maps from OpenStreetMap projects on Garmin watches and Edge bike computers\. Use the Mac app, or install straight from your desktop browser\. Free and open source\.<\/p>/);
assert.match(englishHome, /<h1 id="hero-title">Install free maps on your Garmin<\/h1>/);
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
assert.match(styles, /\.experience\.section\s*\{[^}]*padding:\s*clamp\(72px, 9vw, 116px\) 0 clamp\(40px, 5vw, 64px\)/s);
assert.match(styles, /\.product-showcase\s*\{[^}]*padding:\s*clamp\(68px, 7\.5vw, 100px\) 0/s);
assert.match(styles, /\.product-showcase-panel\s*\{[^}]*border:\s*1px solid var\(--border\)[^}]*border-radius:\s*24px[^}]*background:\s*var\(--surface\)/s);
assert.match(styles, /\.steps::before\s*\{[^}]*background:\s*var\(--border\)/s);
assert.match(styles, /\.steps::before\s*\{[^}]*display:\s*none/s);
assert.match(styles, /\.step,\s*\.step \+ \.step\s*\{[^}]*border-bottom:\s*0/s);
assert.match(styles, /\.map-feature-tabs\s*\{[^}]*border-radius:\s*14px/s);
assert.match(styles, /\.map-feature-tab\s*\{[^}]*border-radius:\s*10px/s);
assert.match(styles, /\.section-heading h2 span\s*\{[^}]*color:\s*var\(--sky\)[^}]*font-family:\s*var\(--font-ui\)/s);
assert.match(styles, /\.section-heading h2 \.workflow-title-bullet\s*\{[^}]*display:\s*none/s);
assert.match(styles, /\.section-heading h2 \.workflow-title-bullet\s*\{[^}]*display:\s*inline-block[^}]*font-size:\s*\.72em/s);
assert.match(styles, /\.section-heading h2 \.workflow-title-arrow\s*\{[^}]*display:\s*none/s);
assert.match(styles, /\.map-feature-panel\[hidden\]\s*\{[^}]*display:\s*none/s);
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
