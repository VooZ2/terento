"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const locales = new Map([
  ["en", {
    file: path.join(root, "site", "index.html"),
    h1: "Install maps on Garmin watches, simply",
    hero: "Install, update, and manage third-party maps from a native macOS app — without manual file transfers.",
    experienceLabel: "How it works",
    experienceTitle: "Connect → Install → Done",
    featureTabsLabel: "Map features",
    installLabel: "Install maps",
    manageLabel: "Manage maps",
    problem: "Installing third-party maps should be simple and fast — without extra software, separate download steps, or technical know-how.",
    problemSecondary: "Terento brings the whole process together in three simple steps.",
    installStep: "Choose maps from the catalog, or add your own compatible .img map.",
    doneLabel: "Done",
    doneStep: "Your maps are installed and ready to use on your watch.",
    installShowcase: "Choose maps from the catalog by region, or add your own compatible .img map.",
    manageShowcase: "See what's installed, update maps when newer releases are available, and remove third-party maps managed by Terento. Original Garmin maps remain protected.",
    providerEyebrow: "Available maps",
    providerTitle: "Explore available maps.",
    providerCopy: "Today, Terento connects you directly to Freizeitkarte and OpenTopoMap. Maps are downloaded from each provider's original source.",
    heroCompatibility: "Check compatibility",
    download: "Download",
  }],
  ["de", {
    file: path.join(root, "site", "de", "index.html"),
    h1: "Karten einfach auf Garmin-Uhren installieren",
    hero: "Installiere, aktualisiere und verwalte Drittanbieter-Karten mit einer nativen macOS-App — ohne manuelle Dateiübertragungen.",
    experienceLabel: "So funktioniert es",
    experienceTitle: "Verbinden → Installieren → Fertig",
    featureTabsLabel: "Kartenfunktionen",
    installLabel: "Karten installieren",
    manageLabel: "Karten verwalten",
    problem: "Die Installation von Drittanbieter-Karten sollte einfach und schnell sein — ohne zusätzliche Software, separate Download-Schritte oder technisches Vorwissen.",
    problemSecondary: "Terento bündelt den gesamten Ablauf in drei einfachen Schritten.",
    installStep: "Wähle Karten aus dem Katalog oder füge deine eigene kompatible .img-Karte hinzu.",
    doneLabel: "Fertig",
    doneStep: "Deine Karten sind installiert und auf deiner Uhr einsatzbereit.",
    installShowcase: "Wähle Karten aus dem Katalog nach Region oder füge deine eigene kompatible .img-Karte hinzu.",
    manageShowcase: "Sieh, was installiert ist, aktualisiere Karten, wenn neuere Versionen verfügbar sind, und entferne von Terento verwaltete Drittanbieter-Karten. Originale Garmin-Karten bleiben geschützt.",
    providerEyebrow: "Verfügbare Karten",
    providerTitle: "Verfügbare Karten entdecken.",
    providerCopy: "Heute verbindet Terento dich direkt mit Freizeitkarte und OpenTopoMap. Karten werden von der Originalquelle des jeweiligen Anbieters geladen.",
    heroCompatibility: "Kompatibilität prüfen",
    download: "Herunterladen",
  }],
  ["fr", {
    file: path.join(root, "site", "fr", "index.html"),
    h1: "Installez simplement des cartes sur les montres Garmin",
    hero: "Installez, mettez à jour et gérez des cartes tierces depuis une application macOS native — sans transferts manuels de fichiers.",
    experienceLabel: "Comment ça marche",
    experienceTitle: "Connecter → Installer → Terminé",
    featureTabsLabel: "Fonctions cartographiques",
    installLabel: "Installer des cartes",
    manageLabel: "Gérer les cartes",
    problem: "Installer des cartes tierces devrait être simple et rapide — sans logiciel supplémentaire, étapes de téléchargement séparées ni connaissances techniques.",
    problemSecondary: "Terento réunit tout le parcours en trois étapes simples.",
    installStep: "Choisissez des cartes dans le catalogue ou ajoutez votre propre carte .img compatible.",
    doneLabel: "Terminé",
    doneStep: "Vos cartes sont installées et prêtes à être utilisées sur votre montre.",
    installShowcase: "Choisissez des cartes dans le catalogue par région ou ajoutez votre propre carte .img compatible.",
    manageShowcase: "Consultez les cartes installées, mettez-les à jour lorsqu’une version plus récente est disponible et supprimez les cartes tierces gérées par Terento. Les cartes Garmin d’origine restent protégées.",
    providerEyebrow: "Cartes disponibles",
    providerTitle: "Découvrez les cartes disponibles.",
    providerCopy: "Aujourd’hui, Terento vous connecte directement à Freizeitkarte et OpenTopoMap. Les cartes sont téléchargées depuis la source d’origine de chaque fournisseur.",
    heroCompatibility: "Vérifier la compatibilité",
    download: "Télécharger",
  }],
  ["pl", {
    file: path.join(root, "site", "pl", "index.html"),
    h1: "Instaluj mapy na zegarkach Garmin — po prostu",
    hero: "Instaluj, aktualizuj i zarządzaj mapami innych firm z natywnej aplikacji macOS — bez ręcznego przesyłania plików.",
    experienceLabel: "Jak to działa",
    experienceTitle: "Połącz → Zainstaluj → Gotowe",
    featureTabsLabel: "Funkcje map",
    installLabel: "Instaluj mapy",
    manageLabel: "Zarządzaj mapami",
    problem: "Instalowanie map innych firm powinno być proste i szybkie — bez dodatkowego oprogramowania, osobnych etapów pobierania ani wiedzy technicznej.",
    problemSecondary: "Terento łączy cały proces w trzech prostych krokach.",
    installStep: "Wybierz mapy z katalogu albo dodaj własną zgodną mapę .img.",
    doneLabel: "Gotowe",
    doneStep: "Twoje mapy są zainstalowane i gotowe do użycia na zegarku.",
    installShowcase: "Wybieraj mapy z katalogu według regionu albo dodaj własną zgodną mapę .img.",
    manageShowcase: "Sprawdź, co jest zainstalowane, aktualizuj mapy, gdy dostępne są nowsze wydania, i usuwaj mapy innych firm zarządzane przez Terento. Oryginalne mapy Garmin pozostają chronione.",
    providerEyebrow: "Dostępne mapy",
    providerTitle: "Poznaj dostępne mapy.",
    providerCopy: "Dziś Terento łączy Cię bezpośrednio z Freizeitkarte i OpenTopoMap. Mapy są pobierane z oryginalnego źródła każdego dostawcy.",
    heroCompatibility: "Sprawdź kompatybilność",
    download: "Pobierz",
  }],
  ["cs", {
    file: path.join(root, "site", "cs", "index.html"),
    h1: "Instalujte mapy do hodinek Garmin jednoduše",
    hero: "Instalujte, aktualizujte a spravujte mapy třetích stran z nativní aplikace pro macOS — bez ručních přenosů souborů.",
    experienceLabel: "Jak to funguje",
    experienceTitle: "Připojit → Instalovat → Hotovo",
    featureTabsLabel: "Funkce map",
    installLabel: "Instalovat mapy",
    manageLabel: "Spravovat mapy",
    problem: "Instalace map třetích stran by měla být jednoduchá a rychlá — bez dalšího softwaru, samostatných kroků stahování a technických znalostí.",
    problemSecondary: "Terento celý proces spojuje do tří jednoduchých kroků.",
    installStep: "Vybírejte mapy z katalogu podle oblasti nebo přidejte vlastní kompatibilní mapu .img.",
    doneLabel: "Hotovo",
    doneStep: "Vaše mapy jsou nainstalované a připravené k použití v hodinkách.",
    installShowcase: "Vybírejte mapy z katalogu podle oblasti nebo přidejte vlastní kompatibilní mapu .img.",
    manageShowcase: "Prohlédněte si nainstalované mapy, aktualizujte je, když je k dispozici novější vydání, a odstraňte mapy třetích stran spravované aplikací Terento. Původní mapy Garmin zůstávají chráněné.",
    providerEyebrow: "Dostupné mapy",
    providerTitle: "Prozkoumejte dostupné mapy.",
    providerCopy: "Dnes vás Terento propojí přímo s poskytovateli Freizeitkarte a OpenTopoMap. Mapy se stahují z původního zdroje každého poskytovatele.",
    heroCompatibility: "Ověřit kompatibilitu",
    download: "Stáhnout",
  }],
  ["it", {
    file: path.join(root, "site", "it", "index.html"),
    h1: "Installa le mappe sugli smartwatch Garmin, in modo semplice",
    hero: "Installa, aggiorna e gestisci mappe di terze parti da un’app macOS nativa — senza trasferimenti manuali di file.",
    experienceLabel: "Come funziona",
    experienceTitle: "Connetti → Installa → Fatto",
    featureTabsLabel: "Funzioni delle mappe",
    installLabel: "Installa mappe",
    manageLabel: "Gestisci mappe",
    problem: "Installare mappe di terze parti dovrebbe essere semplice e veloce — senza software aggiuntivo, passaggi di download separati o competenze tecniche.",
    problemSecondary: "Terento riunisce l’intero processo in tre semplici passaggi.",
    installStep: "Scegli le mappe dal catalogo oppure aggiungi la tua mappa .img compatibile.",
    doneLabel: "Fatto",
    doneStep: "Le tue mappe sono installate e pronte per essere usate sullo smartwatch.",
    installShowcase: "Scegli le mappe dal catalogo per regione oppure aggiungi la tua mappa .img compatibile.",
    manageShowcase: "Visualizza le mappe installate, aggiornatele quando è disponibile una versione più recente e rimuovi le mappe di terze parti gestite da Terento. Le mappe Garmin originali restano protette.",
    providerEyebrow: "Mappe disponibili",
    providerTitle: "Scopri le mappe disponibili.",
    providerCopy: "Oggi Terento ti collega direttamente a Freizeitkarte e OpenTopoMap. Le mappe vengono scaricate dalla fonte originale di ciascun provider.",
    heroCompatibility: "Verifica la compatibilità",
    download: "Scarica",
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
  assert.match(page, /<link rel="stylesheet" href="\/styles\.css\?v=20260905-mobile-menu-language-v1">/, `${locale}: Home stylesheet cache bust`);
  assert.match(page, /<script defer src="\/home-features\.js\?v=20260904-home-workflow-tabs"><\/script>/, `${locale}: Home feature script cache bust`);
  assert.match(page, /your-garmin-1600\.png\?v=20260905-app-screens-v1/, `${locale}: updated Garmin screenshot cache bust`);
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
  const experience = page.match(/<section class="experience section" id="how-it-works"[\s\S]*?<\/section>/)?.[0];
  assert.ok(experience);
  assert.equal(experience.match(/<p class="eyebrow" id="experience-label">([^<]+)<\/p>/)?.[1], expected.experienceLabel);
  const experienceTitleMarkup = experience.match(/<h2 id="experience-title">([\s\S]*?)<\/h2>/)?.[1];
  assert.ok(experienceTitleMarkup);
  const experienceTitle = experienceTitleMarkup
    .replace(/<span class="workflow-title-arrow" aria-hidden="true">→<\/span><span class="workflow-title-bullet" aria-hidden="true">•<\/span>/g, " → ")
    .replace(/<[^>]+>/g, "")
    .replace(/\s+/g, " ")
    .trim();
  assert.equal(experienceTitle, expected.experienceTitle);
  assert.equal((experienceTitleMarkup.match(/class="workflow-title-arrow"/g) || []).length, 2);
  assert.equal((experienceTitleMarkup.match(/class="workflow-title-bullet"/g) || []).length, 2);
  const problem = experience.match(/<div class="problem-statement">\s*<p>([^<]+)<\/p>\s*<p>([^<]+)<\/p>/);
  assert.ok(problem);
  assert.equal(problem[1], expected.problem);
  assert.equal(problem[2], expected.problemSecondary);
  const steps = [...experience.matchAll(/<li class="step">([\s\S]*?)<\/li>/g)];
  assert.equal(steps.length, 3);
  assert.equal(steps[1][1].match(/<p>([^<]+)<\/p>\s*$/)?.[1], expected.installStep);
  assert.equal(steps[2][1].match(/<h3>([^<]+)<\/h3>/)?.[1], expected.doneLabel);
  assert.equal(steps[2][1].match(/<p>([^<]+)<\/p>\s*$/)?.[1], expected.doneStep);
  const mapFeature = page.match(/<section class="map-feature-section"[\s\S]*?(?=\s*<section class="provider-section section")/)?.[0];
  assert.ok(mapFeature, `${locale}: missing consolidated map feature section`);
  assert.match(mapFeature, new RegExp(`<div class="map-feature-tabs" data-map-feature-tabs role="tablist" aria-label="${expected.featureTabsLabel}">`));
  assert.match(mapFeature, new RegExp(`<button class="map-feature-tab"[^>]*id="install-maps-tab"[^>]*aria-selected="true"[^>]*>${expected.installLabel}<\/button>`));
  assert.match(mapFeature, new RegExp(`<button class="map-feature-tab"[^>]*id="manage-maps-tab"[^>]*aria-selected="false"[^>]*>${expected.manageLabel}<\/button>`));
  const installShowcase = page.match(/<div class="map-feature-panel" id="install-maps-panel"[\s\S]*?<section class="product-showcase product-showcase--muted"[\s\S]*?<\/section>\s*<\/div>/)?.[0];
  const manageShowcase = page.match(/<div class="map-feature-panel" id="manage-maps-panel"[\s\S]*?<section class="product-showcase product-showcase--muted product-showcase--reverse"[\s\S]*?<\/section>\s*<\/div>/)?.[0];
  assert.ok(installShowcase);
  assert.ok(manageShowcase);
  assert.equal(installShowcase.match(/<h2 id="install-maps-title">[^<]+<\/h2>\s*<p>([^<]+)<\/p>/)?.[1], expected.installShowcase);
  assert.equal(manageShowcase.match(/<h2 id="manage-maps-title">[^<]+<\/h2>\s*<p>([^<]+)<\/p>/)?.[1], expected.manageShowcase);
  assert.doesNotMatch(installShowcase, /showcase-number/);
  assert.doesNotMatch(manageShowcase, /showcase-number/);
  assert.equal((installShowcase.match(/<figure class="app-shot app-shot--feature">/g) || []).length, 1);
  assert.equal((manageShowcase.match(/<figure class="app-shot app-shot--feature">/g) || []).length, 1);
  assert.doesNotMatch(installShowcase, /ready-to-install|installing-maps/);
  assert.match(installShowcase, /class="shell product-showcase-panel"><div class="product-showcase-grid">/);
  assert.match(manageShowcase, /class="shell product-showcase-panel"><div class="product-showcase-grid">/);
  const providerSection = page.match(/<section class="provider-section section"[\s\S]*?<\/section>/)?.[0];
  assert.ok(providerSection, `${locale}: missing provider cards section`);
  assert.match(providerSection, new RegExp(`<p class="eyebrow">${expected.providerEyebrow.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}<\\/p>`));
  assert.match(providerSection, new RegExp(`<h2 id="providers-title">${expected.providerTitle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}<\\/h2>`));
  assert.match(providerSection, new RegExp(`<p class="provider-copy">${expected.providerCopy.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}<\\/p>`));
  assert.equal((providerSection.match(/class="provider-card"/g) || []).length, 2, `${locale}: expected two provider cards`);
  assert.match(providerSection, /data-provider-card="freizeitkarte"/);
  assert.match(providerSection, /data-provider-card="opentopomap"/);
  assert.equal((providerSection.match(/class="provider-benefits"/g) || []).length, 2, `${locale}: each provider card has a benefits list`);
  assert.equal((providerSection.match(/<li>/g) || []).length, 8, `${locale}: provider cards have four benefits each`);
  assert.match(providerSection, /data-count-template="[^"]*\{count\}[^"]*"/);
  assert.match(providerSection, /63/);
  assert.match(providerSection, /177/);
  const cardFragments = [...providerSection.matchAll(/<article class="provider-card"[\s\S]*?<\/article>/g)].map((match) => match[0]);
  cardFragments.forEach((card, index) => {
    assert.doesNotMatch(card, /license|licen[cs]|source|download/i, `${locale}: provider card ${index + 1} avoids technical/legal copy`);
  });
  assert.doesNotMatch(page, /class="scope-section"|class="scope-link"|id="scope-title"|>Beta scope<|Available today|Choose a map and get moving/i, `${locale}: removed Beta scope and stale provider copy`);
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
  assert.doesNotMatch(page, /<p class="hero-lede">[^<]*Freizeitkarte/i, `${locale}: hero copy is provider-neutral`);
  assert.doesNotMatch(page, /back up|backup|sauvegarder|zálohovat|wykonać kopię|eseguire il backup/i, `${locale}: no backup marketing copy`);
  assert.doesNotMatch(page, /beta[ .]?8|bêta 8/i, `${locale}: no stale beta.8 copy`);
}

const englishHome = pageFor("en");
assert.match(englishHome, /<p class="hero-lede">Install, update, and manage third-party maps from a native macOS app — without manual file transfers\.<\/p>/);
assert.match(englishHome, /<h1 id="hero-title">Install maps on Garmin watches, simply<\/h1>/);
assert.doesNotMatch(englishHome, /<p class="hero-lede">[^<]*Freizeitkarte/i);
assert.match(englishHome, /<meta name="description" content="Install and manage third-party maps on supported Garmin smartwatches with Terento, a free macOS app for Apple Silicon\.">/);
assert.match(englishHome, /<p class="eyebrow"><span class="status-dot" aria-hidden="true"><\/span>Open-source project · Beta<\/p>/);
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
assert.match(styles, /\.provider-cards\s*\{[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)/s);
assert.match(styles, /\.provider-card\s*\{[^}]*background:\s*var\(--surface\)/s);
assert.match(styles, /\.provider-benefits\s*\{[^}]*border-top:\s*1px solid var\(--border\)/s);
const localizedContent = fs.readFileSync(path.join(root, "site", "localized-content.js"), "utf8");
assert.doesNotMatch(localizedContent, /querySelector\("\.scope-copy"\)/s, "removed Home scope copy must not be updated by JavaScript");

console.log("Home copy, localized Hero, shared CTA, and CTA interaction-contract tests passed.");
