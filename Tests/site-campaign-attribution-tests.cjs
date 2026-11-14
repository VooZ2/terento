"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const privacy = fs.readFileSync(path.join(root, "site", "privacy-consent.js"), "utf8");
const privacyPage = fs.readFileSync(path.join(root, "site", "privacy", "index.html"), "utf8");

for (const key of ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"]) {
  assert.match(privacy, new RegExp(`"${key}"`), `${key}: privacy script must preserve the allow-listed UTM key`);
}
assert.doesNotMatch(privacy, /terento-campaign-attribution/);
assert.doesNotMatch(privacy, /sessionStorage|localStorage/);
assert.match(privacy, /window\.location\.origin/);
assert.match(privacy, /isDownloadArtifact/);
assert.match(privacy, /campaignSource/);
assert.match(privacy, /campaignMedium/);
assert.match(privacy, /campaignName/);
assert.match(privacy, /propagateCampaignParams\(campaignParams\)/);
assert.match(privacy, /instrumentConversionLinks\(campaignParams\)/);
assert.match(privacyPage, /download events/);
assert.match(privacyPage, /for all visitors/);
assert.match(privacyPage, /legitimate interests/);
assert.match(privacyPage, /There is no analytics consent banner/);
assert.doesNotMatch(privacyPage, /only after you consent|consented download events|If you do not consent, Umami is not loaded/);
// Execute the loader with browser storage inaccessible: analytics and URL
// attribution must still work, without leaking campaigns to unrelated links.
const vm = require("node:vm");
function run(search = "") {
  const location = new URL("https://terento.app/" + search);
  const makeLink = (href) => ({
    href, dataset: {}, classList: {contains: () => false}, closest: () => null,
    getAttribute() { return this.href; }, setAttribute(name, value) { this[name] = value; }
  });
  const links = ["/download/", "https://github.com/VooZ2/terento/releases/download/v1/app.dmg", "https://example.com/", "#section"].map(makeLink);
  const scripts = [];
  const document = {
    querySelector: () => scripts.find((script) => script.dataset.terentoUmami) || null,
    querySelectorAll: (selector) => selector.startsWith("a[") ? links : [],
    createElement: () => ({dataset: {}}), head: {append: (...items) => scripts.push(...items)}
  };
  const window = {location};
  for (const key of ["sessionStorage", "localStorage"]) Object.defineProperty(window, key, {get() {throw Error("No campaign storage allowed");}});
  const context = {window, document, URL};
  vm.runInNewContext(privacy, context);
  vm.runInNewContext(privacy, context);
  assert.equal(scripts.length, 2, "Umami (and its before-send filter) loads exactly once without a consent prerequisite");
  return links;
}
const links = run("?utm_source=github&utm_campaign=readme&utm_term=private%40email.com");
assert.match(links[0].href, /utm_source=github/);
assert.match(links[1].href, /utm_campaign=readme/);
assert.doesNotMatch(links[0].href, /utm_term/);
assert.equal(links[2].href, "https://example.com/");
assert.equal(links[3].href, "#section");
assert.equal(run()[0].href, "/download/", "A fresh visit does not inherit stored campaigns");
for (const source of ["chatgpt.com", "claude.ai", "gemini.google.com", "bing", "other-source"]) {
  const incoming = run(`?utm_source=${source}`);
  assert.equal(new URL(incoming[0].href, "https://terento.app").searchParams.get("utm_source"), source);
  assert.equal(incoming[1].dataset.umamiEventCampaignSource, source);
  assert.equal(incoming[2].href, "https://example.com/");
}

// The Umami tag counts only the public host and ignores #fragment changes;
// download-click names where the link was and which release it downloads.
function runAt(pathname, hrefs, linkProps = {}, version) {
  const location = new URL("https://terento.app" + pathname);
  const links = hrefs.map((href) => ({
    href, dataset: {...linkProps}, classList: {contains: () => false}, closest: () => null,
    getAttribute() { return this.href; }, setAttribute(name, value) { this[name] = value; }
  }));
  const scripts = [];
  const document = {
    querySelector: () => scripts.find((script) => script.dataset.terentoUmami) || null,
    querySelectorAll: (selector) => selector.startsWith("a[") ? links : [],
    createElement: () => ({dataset: {}}), head: {append: (...items) => scripts.push(...items)}
  };
  document.currentScript = {src: `https://terento.app/privacy-consent.js${version === undefined ? "?v=20261114-umami-monitoring" : version}`};
  vm.runInNewContext(privacy, {window: {location}, document, URL});
  return {links, scripts, script: scripts.find((script) => script.dataset.terentoUmami)};
}
const release = "https://github.com/VooZ2/terento/releases/download/v1.2.0-build47/Terento-1.2.0-macOS-arm64.dmg";
const downloadPage = runAt("/de/download/", [release, "https://github.com/VooZ2/terento/releases/download/v1.3.0-rc.1-build50/Terento-1.3.0-rc.1-macOS-arm64.zip"]);
assert.equal(downloadPage.script.dataset.domains, "terento.app", "localhost and copies of the site are not counted");
assert.equal(downloadPage.script.dataset.excludeHash, "true", "a #fragment change is not a page view");
// Monitoring: Web Vitals and errors, the release is this script's cache
// version, and the before-send filter is loaded first and in order.
const tag = downloadPage.script.dataset;
assert.equal(tag.performance, "true");
assert.equal(tag.errors, "true");
assert.equal(tag.environment, "production");
assert.equal(tag.release, "20261114-umami-monitoring");
assert.equal(tag.beforeSend, "terentoUmamiBeforeSend");
assert.equal(tag.websiteId, "d8097a98-ffe4-478e-b212-9f06b5bcccbe");
assert.equal(downloadPage.scripts.length, 2);
assert.equal(downloadPage.scripts[0].src, "/umami-before-send.js?v=20261114-umami-monitoring");
assert.equal(downloadPage.scripts[1].src, "https://stats.enduristas.lt/script.js");
assert.ok(downloadPage.scripts.every((script) => script.async === false), "filter and tracker run in order");
assert.equal(runAt("/", [], {}, "").script.dataset.release, "unversioned");
assert.equal(runAt("/", [], {}, "").scripts[0].src, "/umami-before-send.js");
assert.equal(runAt("/", [], {}, "?v=bad%20value").script.dataset.release, "unversioned");
assert.equal(downloadPage.links[0].dataset.umamiEvent, "download-click");
assert.equal(downloadPage.links[0].dataset.umamiEventLocation, "download-page");
assert.equal(downloadPage.links[0].dataset.umamiEventFile, "dmg");
assert.equal(downloadPage.links[0].dataset.umamiEventVersion, "1.2.0");
assert.equal(downloadPage.links[1].dataset.umamiEventVersion, "1.3.0-rc.1");
const elsewhere = runAt("/", [release, "https://example.com/files/app.dmg"]);
assert.equal(elsewhere.links[0].dataset.umamiEventLocation, "home-page", "the location is where the link is, not always the Download page");
assert.equal(elsewhere.links[1].dataset.umamiEventVersion, undefined, "no version is made up for an unknown file name");
const marked = runAt("/guides/install-garmin-maps-mac/", [release], {umamiEventLocation: "guide-steps"});
assert.equal(marked.links[0].dataset.umamiEventLocation, "guide-steps", "a link's own location wins");

console.log("Campaign attribution and Umami privacy contract tests passed.");
