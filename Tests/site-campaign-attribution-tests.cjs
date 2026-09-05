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
    querySelector: () => scripts[0] || null,
    querySelectorAll: (selector) => selector.startsWith("a[") ? links : [],
    createElement: () => ({dataset: {}}), head: {append: (script) => scripts.push(script)}
  };
  const window = {location};
  for (const key of ["sessionStorage", "localStorage"]) Object.defineProperty(window, key, {get() {throw Error("No campaign storage allowed");}});
  const context = {window, document, URL};
  vm.runInNewContext(privacy, context);
  vm.runInNewContext(privacy, context);
  assert.equal(scripts.length, 1, "Umami loads exactly once without a consent prerequisite");
  return links;
}
const links = run("?utm_source=github&utm_campaign=readme&utm_term=private%40email.com");
assert.match(links[0].href, /utm_source=github/);
assert.match(links[1].href, /utm_campaign=readme/);
assert.doesNotMatch(links[0].href, /utm_term/);
assert.equal(links[2].href, "https://example.com/");
assert.equal(links[3].href, "#section");
assert.equal(run()[0].href, "/download/", "A fresh visit does not inherit stored campaigns");

console.log("Campaign attribution and Umami privacy contract tests passed.");
