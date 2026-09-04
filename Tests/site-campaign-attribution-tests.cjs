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

console.log("Campaign attribution and Umami privacy contract tests passed.");
