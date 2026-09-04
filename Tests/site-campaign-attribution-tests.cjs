"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const privacy = fs.readFileSync(path.join(root, "site", "privacy-consent.js"), "utf8");
const privacyPage = fs.readFileSync(path.join(root, "site", "privacy", "index.html"), "utf8");
const pilot = fs.readFileSync(path.join(root, "docs", "reddit-pilot.md"), "utf8");

for (const key of ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"]) {
  assert.match(privacy, new RegExp(`"${key}"`), `${key}: privacy script must preserve the allow-listed UTM key`);
}
assert.match(privacy, /terento-campaign-attribution/);
assert.match(privacy, /sessionStorage/);
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
assert.match(privacyPage, /There is no analytics consent popup/);
assert.doesNotMatch(privacyPage, /only after you consent|consented download events|If you do not consent, Umami is not loaded/);
assert.match(privacyPage, /campaign measurement, not personal profiling or targeted advertising/i);

assert.match(pilot, /100 €/);
assert.match(pilot, /20 dien/);
assert.match(pilot, /5 € per dien/);
assert.match(pilot, /utm_source=reddit/);
assert.match(pilot, /utm_medium=paid_social/);
assert.match(pilot, /utm_campaign=beta_downloads_202609/);
assert.match(pilot, /utm_content=creative_a/);
assert.match(pilot, /utm_content=creative_b/);
assert.match(pilot, /pagrindinis puslapis/);
assert.match(pilot, /r\/GarminWatches/);
assert.match(pilot, /Google Search/);

console.log("Campaign attribution and Reddit pilot contract tests passed.");
