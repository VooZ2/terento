const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), "utf8");
const styles = read("site/styles.css");
const styleVersion = "20260830-page-intros";
const localizedContentVersion = "20260830-download-links";

const cssBlock = (selector) => {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = styles.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`, "s"));
  assert.ok(match, `Missing CSS block for ${selector}`);
  return match[1];
};

assert.match(styles, /--internal-page-intro-padding-top:\s*clamp\(34px, 5vw, 64px\)/);
for (const selector of [".compatibility-hero", ".guide-intro", ".download-main"]) {
  assert.match(cssBlock(selector), /var\(--internal-page-intro-padding-top\)/, `${selector} must use the shared intro token`);
}
assert.match(cssBlock(".hero"), /padding:\s*clamp\(72px, 10vw, 144px\)/, "Home keeps its landing-hero spacing");
assert.doesNotMatch(cssBlock(".hero"), /internal-page-intro/);

assert.match(cssBlock(".shell"), /width:\s*min\(calc\(100% - 48px\), var\(--max-width\)\)/);
assert.doesNotMatch(cssBlock(".compatibility-hero-inner"), /max-width|margin(?:-inline)?:\s*auto|text-align:\s*center/);
assert.match(cssBlock(".compatibility-hero-inner"), /text-align:\s*left/);

const linkBlock = cssBlock(".download-info-link");
assert.match(linkBlock, /display:\s*inline-flex/);
assert.match(linkBlock, /width:\s*fit-content/);
assert.match(linkBlock, /max-width:\s*100%/);
assert.match(linkBlock, /margin-top:\s*auto/);
assert.doesNotMatch(linkBlock, /justify-content:\s*space-between|(?:^|\n)\s*width:\s*100%/);
assert.match(cssBlock(".download-info-link-tail"), /white-space:\s*nowrap/);
assert.match(cssBlock(".download-sections .download-item"), /display:\s*flex/);
assert.match(styles, /\.download-sections \.download-info-link\s*\{\s*margin-top:\s*0;/s);
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
  assert.equal((html.match(/class="download-sections"/g) || []).length, 1, `${locale} must use one three-column information grid`);
  assert.doesNotMatch(html, /class="download-grid"/);
  assert.doesNotMatch(html, /New to third-party maps\?|Neu bei Drittanbieter-Karten\?|Vous débutez avec les cartes tierces|Dopiero zaczynasz z mapami innych firm|Začínáte s mapami třetích stran|È la prima volta che installi mappe di terze parti/);

  const anchors = [...html.matchAll(/<a class="download-info-link" href="([^"]+)">([\s\S]*?)<\/a>/g)];
  assert.equal(anchors.length, 2, `${locale} must expose exactly two Download information links`);
  assert.deepEqual(anchors.map((match) => match[1]), [contract.guide, contract.compatibility]);
  assert.deepEqual(anchors.map((match) => visibleText(match[2])), [contract.guideLabel, contract.compatibilityLabel]);
  for (const match of anchors) {
    assert.match(match[2], /class="download-info-link-tail"/);
    assert.match(match[2], /class="download-info-link-arrow" aria-hidden="true">→<\/span>/);
    assert.doesNotMatch(match[1], /utm_/i);
  }
  if (locale !== "en") {
    assert.match(html, new RegExp(`/localized-content\\.js\\?v=${localizedContentVersion}`));
  }
}

assert.doesNotMatch(read("site/localized-content.js"), /download-compatibility-link/);
console.log("Public page intro and Download link layout contracts passed for all six locales.");
