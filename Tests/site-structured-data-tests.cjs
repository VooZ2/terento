const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const baseUrl = "https://terento.app";
const repositoryUrl = "https://github.com/VooZ2/terento";
const organizationId = `${baseUrl}/#organization`;
const softwareId = `${baseUrl}/#software`;
const locales = ["en", "de", "fr", "pl", "cs", "it"];
const localePath = (locale, suffix = "") => (locale === "en" ? `/${suffix}` : `/${locale}/${suffix}`);
const homeFile = (locale) => locale === "en"
  ? path.join(root, "site", "index.html")
  : path.join(root, "site", locale, "index.html");
const downloadFile = (locale) => path.join(root, "site", locale === "en" ? "download" : path.join(locale, "download"), "index.html");
const guideFile = (locale) => path.join(root, "site", locale === "en" ? "guides/install-garmin-maps-mac" : path.join(locale, "guides/install-garmin-maps-mac"), "index.html");

const release = JSON.parse(fs.readFileSync(path.join(root, "site", "updates", "macos-arm64.json"), "utf8"));

function readJsonLd(file) {
  const source = fs.readFileSync(file, "utf8");
  const blocks = [...source.matchAll(/<script\b[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi)];
  assert.equal(blocks.length, 1, `${file}: expected one JSON-LD block`);
  let data;
  assert.doesNotThrow(() => { data = JSON.parse(blocks[0][1].trim()); }, `${file}: JSON-LD must parse`);
  return { source, data };
}

function entity(data, type, file) {
  const graph = data["@graph"] || [data];
  const matches = graph.filter((item) => item["@type"] === type);
  assert.equal(matches.length, 1, `${file}: expected one ${type} entity`);
  return matches[0];
}

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
  assert(section, `${file}: visible FAQ section is required`);
  const entries = [...section[1].matchAll(/<details>\s*<summary>([\s\S]*?)<\/summary>\s*<p>([\s\S]*?)<\/p>\s*(?:<div class="faq-support-actions">[\s\S]*?<\/div>\s*)?<\/details>/gi)]
    .map((match) => ({ question: visibleText(match[1]), answer: visibleText(match[2]) }));
  assert.equal(entries.length, 5, `${file}: expected five visible FAQ entries`);
  return entries;
}

function assertCanonicalMetadata(source, canonical, file) {
  assert.equal((source.match(/rel="canonical"/g) || []).length, 1, `${file}: canonical count`);
  assert(source.includes(`href="${canonical}"`), `${file}: canonical URL`);
  assert.match(source, /<meta name="robots" content="index,follow">/);
  assert.equal((source.match(/hreflang=/g) || []).length, 7, `${file}: hreflang set changed`);
}

function assertApplication(app, locale, url, file) {
  assert.equal(app["@type"], "SoftwareApplication", `${file}: application type`);
  assert.equal(app["@id"], softwareId, `${file}: canonical application ID`);
  assert.equal(app.name, "Terento", `${file}: application name`);
  assert.equal(app.url, url, `${file}: application URL`);
  assert.equal(app.applicationCategory, "UtilitiesApplication", `${file}: application category`);
  assert(app.operatingSystem, `${file}: operating system`);
  assert(app.softwareRequirements, `${file}: software requirements`);
  assert(app.description, `${file}: application description`);
  assert.equal(app.softwareVersion, release.releaseLabel, `${file}: current software version`);
  assert.equal(app.downloadUrl, release.downloadURL, `${file}: current download URL`);
  assert.equal(app.releaseNotes, release.releaseNotesURL, `${file}: current release notes URL`);
  assert.deepEqual(app.offers, { "@type": "Offer", price: "0", priceCurrency: "EUR" }, `${file}: free offer`);
  assert.equal(app.inLanguage, locale, `${file}: application language`);
  assert.deepEqual(app.publisher, { "@id": organizationId }, `${file}: publisher reference`);
  assert(!JSON.stringify(app).includes("localhost"), `${file}: localhost must not enter JSON-LD`);
  assert(!JSON.stringify(app).includes("test.terento.app"), `${file}: test host must not enter JSON-LD`);
}

for (const locale of locales) {
  const home = homeFile(locale);
  const homeData = readJsonLd(home);
  const homeUrl = `${baseUrl}${localePath(locale)}`;
  assertCanonicalMetadata(homeData.source, homeUrl, home);
  assert.equal(homeData.data["@context"], "https://schema.org", `${home}: schema context`);
  const graph = homeData.data["@graph"];
  assert(Array.isArray(graph), `${home}: Home must use one @graph`);
  assert.equal(graph.length, 4, `${home}: graph should remain compact`);

  const organization = entity(homeData.data, "Organization", home);
  assert.deepEqual(organization, {
    "@type": "Organization",
    "@id": organizationId,
    name: "Terento",
    url: `${baseUrl}/`,
    logo: `${baseUrl}/assets/logo-sky.svg`,
    sameAs: [repositoryUrl],
  }, `${home}: organization identity`);

  const applicationEntity = entity(homeData.data, "SoftwareApplication", home);
  assertApplication(applicationEntity, locale, homeUrl, home);

  const website = entity(homeData.data, "WebSite", home);
  assert.equal(website["@id"], `${homeUrl}#website`, `${home}: website ID`);
  assert.equal(website.url, homeUrl, `${home}: website URL`);
  assert.equal(website.inLanguage, locale, `${home}: website language`);
  assert.deepEqual(website.publisher, { "@id": organizationId }, `${home}: website publisher`);

  const faq = entity(homeData.data, "FAQPage", home);
  assert.equal(faq["@id"], `${homeUrl}#faq`, `${home}: FAQ ID`);
  assert.equal(faq.url, `${homeUrl}#faq`, `${home}: FAQ URL`);
  assert.equal(faq.inLanguage, locale, `${home}: FAQ language`);
  assert.equal(faq.mainEntity.length, 5, `${home}: FAQ count`);
  assert.deepEqual(
    faq.mainEntity.map((question) => ({ question: question.name, answer: question.acceptedAnswer.text })),
    visibleFaq(homeData.source, home),
    `${home}: FAQ JSON-LD must match visible FAQ exactly`
  );
  assert.match(faq.mainEntity[1].acceptedAnswer.text, /map file|Kartendatei|fichier cartographique|plik mapy|mapový soubor|file cartografico/i, `${home}: BaseCamp schema answer uses user-facing map-file language`);
  assert.doesNotMatch(faq.mainEntity[3].acceptedAnswer.text, /beta|bêta|version|release|wersj|verz|versi/i, `${home}: provider schema answer describes Terento without release wording`);
  assert.match(faq.mainEntity[2].acceptedAnswer.text, /protected|geschützt|protég|chronione|chráněné|protette/i, `${home}: safety answer protects Garmin/system maps`);
  assert.match(faq.mainEntity[3].name, /provider|anbieter|fournisseur|dostawc|poskytovatel/i, `${home}: provider FAQ question`);
  assert.match(homeData.source, /data-provider-list[\s\S]*Freizeitkarte[\s\S]*OpenTopoMap/, `${home}: provider directory names current providers`);
  assert.doesNotMatch(homeData.source, /back up|backup|sauvegarder|zálohovat|wykonać kopię|eseguire il backup/i, `${home}: no backup promise in source`);

  const download = downloadFile(locale);
  const downloadData = readJsonLd(download);
  const downloadUrl = `${baseUrl}${localePath(locale, "download/")}`;
  assertCanonicalMetadata(downloadData.source, downloadUrl, download);
  assert.equal(downloadData.data["@context"], "https://schema.org", `${download}: schema context`);
  assertApplication(entity(downloadData.data, "SoftwareApplication", download), locale, downloadUrl, download);
  assert.equal((downloadData.data["@graph"] || []).length, 0, `${download}: no duplicate graph entities`);
  assert.equal((downloadData.source.match(/type=["']application\/ld\+json["']/gi) || []).length, 1, `${download}: one JSON-LD block`);
}

for (const locale of locales) {
  const guide = guideFile(locale);
  const guideData = readJsonLd(guide);
  const graph = guideData.data["@graph"] || [];
  const guideOrganization = entity(guideData.data, "Organization", guide);
  assert.equal(guideOrganization.name, "Terento", `${guide}: organization name`);
  assert.equal(guideOrganization.url, `${baseUrl}/`, `${guide}: organization URL`);
  const guideArticle = entity(guideData.data, "Article", guide);
  assert.equal(guideArticle.datePublished, "2026-08-28T00:00:00Z", `${guide}: ISO publication datetime`);
  assert.equal(guideArticle.dateModified, `${release.publishedAt}T00:00:00Z`, `${guide}: ISO modified datetime`);
  assert.equal(graph.filter((item) => item["@type"] === "Article").length, 1, `${guide}: Article entity`);
  assert.equal(graph.filter((item) => item["@type"] === "BreadcrumbList").length, 1, `${guide}: BreadcrumbList entity`);
  assert.equal(graph.filter((item) => item["@type"] === "FAQPage").length, 0, `${guide}: Guide must not publish FAQPage schema`);
  assert.doesNotMatch(guideData.source, /<section class="guide-faq"\b|id="faq"/i, `${guide}: Guide FAQ section removed`);
}

const compatibilityPages = [
  ["en", path.join(root, "site", "compatibility", "index.html")],
  ...locales.filter((locale) => locale !== "en").map((locale) => [locale, path.join(root, "site", locale, "compatibility", "index.html")]),
];
for (const [locale, compatibility] of compatibilityPages) {
  const compatibilitySource = fs.readFileSync(compatibility, "utf8");
  assert.equal((compatibilitySource.match(/application\/ld\+json/gi) || []).length, 0, `${compatibility}: no compatibility schema block`);
  assert.equal((compatibilitySource.match(/hreflang=/g) || []).length, 7, `${compatibility}: reciprocal hreflang set`);
  assert.match(compatibilitySource, /data-page="compatibility"/);
  assert.match(compatibilitySource, /data-umami-event="download-cta-click"/);
  assert.match(compatibilitySource, /data-umami-event-location="compatibility-community-testing"/);
  assert.match(compatibilitySource, new RegExp(`href="/${locale === "en" ? "" : `${locale}/`}download/"`));
}

console.log("Structured-data JSON-LD, release-source, locale, and visible-FAQ drift tests passed.");
