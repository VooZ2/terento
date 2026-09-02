"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), "utf8");
const release = JSON.parse(read("site/updates/macos-arm64.json"));
const label = release.releaseLabel;
const betaMatch = label.match(/^1\.0\.0-beta\.(\d+)$/);

assert.ok(betaMatch, "update manifest must contain a numbered beta release label");
const betaNumber = betaMatch[1];
const numberedBeta = /b(?:eta|êta)[ .](\d+)/gi;

function assertOnlyCurrentBeta(relativePath) {
  const source = read(relativePath);
  const versions = [...source.matchAll(numberedBeta)].map((match) => match[1]);
  assert.ok(versions.length > 0, `${relativePath}: expected a current beta reference`);
  assert.ok(
    versions.every((version) => version === betaNumber),
    `${relativePath}: numbered beta references must match ${label}`,
  );
}

assertOnlyCurrentBeta("README.md");
assertOnlyCurrentBeta("RELEASE_NOTES.md");
assert.match(read("README.md"), new RegExp(`The latest public release is beta\\.${betaNumber}:`));
assert.match(read("README.md"), new RegExp(`Download Terento beta\\.${betaNumber}`));

const notes = read("RELEASE_NOTES.md");
assert.match(notes, new RegExp(`^# Terento v${label}$`, "m"));
assert.ok(notes.includes(release.sha256), "release notes must contain the manifest DMG SHA-256");

for (const locale of ["en", "de", "fr", "pl", "cs", "it"]) {
  const prefix = locale === "en" ? "" : `${locale}/`;
  assertOnlyCurrentBeta(`site/${prefix}index.html`);
}
assertOnlyCurrentBeta("site/localized-content.js");

assert.doesNotMatch(
  read("backend/catalog-api/src/terento_catalog/admin.py"),
  /opted-in b(?:eta|êta)[ .]\d+/i,
  "Admin copy must remain release-neutral",
);

console.log(`Release documentation matches ${label}.`);
