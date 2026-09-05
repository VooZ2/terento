"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const baseUrl = "https://terento.app";
const metadata = JSON.parse(fs.readFileSync(path.join(root, "site", "metadata.json"), "utf8"));
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");
const localePrefix = (locale) => locale === "en" ? "" : `${locale}/`;
const altByLocale = {
  en: "Terento showing a connected Garmin smartwatch on macOS",
  de: "Terento zeigt eine verbundene Garmin-Smartwatch unter macOS",
  fr: "Terento affiche une montre Garmin connectée sur macOS",
  pl: "Terento pokazuje podłączony zegarek Garmin w systemie macOS",
  cs: "Terento zobrazuje připojené hodinky Garmin v systému macOS",
  it: "Terento mostra uno smartwatch Garmin collegato su macOS",
};

for (const page of metadata.pages) {
  const source = read(page.file.replace(`${root}${path.sep}`, ""));
  const expectedRobots = page.indexable === false ? "noindex,follow" : "index,follow";
  assert.match(source, new RegExp(`<meta name="robots" content="${expectedRobots}">`), `${page.path}: robots directive`);
  assert.match(source, new RegExp(`<link rel="canonical" href="${baseUrl}${page.path}">`), `${page.path}: canonical`);
  const expectedAlt = altByLocale[page.locale];
  assert.match(source, new RegExp(`<meta property="og:image:alt" content="${expectedAlt.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}">`), `${page.path}: localized OG image alt`);
}

const sitemap = read("site/sitemap.xml");
assert.doesNotMatch(sitemap, /https:\/\/terento\.app\/(?:legal|privacy)\//, "noindex utility pages must not be in the sitemap");
for (const page of metadata.pages.filter((candidate) => candidate.indexable !== false)) {
  assert.match(sitemap, new RegExp(`<loc>${baseUrl.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}${page.path.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}</loc>`), `${page.path}: sitemap URL`);
}

assert.match(read("site/index.html"), /provider-list\.js\?v=20260904-home-provider-cards/);
assert.match(read("site/provider-list.js"), /https:\/\/api\.terento\.app\/maps\/catalog\.json/);
assert.match(read("site/reading-state.js"), /terento-reading-state/);

console.log("Website metadata, sitemap, provider catalog, and reading-state contracts passed.");
