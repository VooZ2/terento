"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), "utf8");
const release = JSON.parse(read("site/updates/macos-arm64.json"));
const label = release.releaseLabel;
const releaseTag = release.releaseTag || `v${label}`;
const semanticVersion = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$/;
const versionMatch = label.match(semanticVersion);

assert.ok(versionMatch, "update manifest must contain a semantic release label");
assert.equal(release.version, `${versionMatch[1]}.${versionMatch[2]}.${versionMatch[3]}`);
assert.ok(Number.isInteger(release.build) && release.build > 0, "distributed build must be positive");
assert.ok(["beta", "stable"].includes(release.channel), "release channel must be beta or stable");
assert.match(releaseTag, /^v[0-9A-Za-z][0-9A-Za-z.-]*$/, "release tag must be an explicit safe Git tag");
assert.equal(
  release.channel === "stable",
  versionMatch[4] === undefined,
  "stable releases must not have a prerelease label and prereleases must use the beta channel",
);
const publicLabel = versionMatch[4] || label;

const readme = read("README.md");
assert.ok(readme.includes(`The latest public release is **${publicLabel} (build ${release.build})**`));
assert.match(readme, /The Compatibility page is the official public list/);
assert.match(readme, /\*\*Tested\*\* — 1–2[\s\S]*\*\*Supported\*\* — 3–4[\s\S]*\*\*Verified\*\* — 5 or more/);

const siteLinks = [...readme.matchAll(/https:\/\/terento\.app[^\s)"<>]*/g)];
assert.ok(siteLinks.length > 0, "README must link to the public site");
const linkLocations = new Set();
for (const [href] of siteLinks) {
  const url = new URL(href.replaceAll("&amp;", "&"));
  for (const [key, value] of Object.entries({
    utm_source: "github", utm_medium: "referral", utm_campaign: "repository",
  })) {
    assert.deepEqual(url.searchParams.getAll(key), [value], `${href}: invalid ${key}`);
  }
  const locations = url.searchParams.getAll("utm_content");
  assert.equal(locations.length, 1, `${href}: must have one attribution location`);
  assert.match(locations[0], /^readme_[a-z0-9_]+$/);
  assert.ok(!linkLocations.has(locations[0]), `${href}: duplicate attribution location`);
  linkLocations.add(locations[0]);
  const sitePath = path.join(root, "site", url.pathname, "index.html");
  assert.ok(fs.existsSync(sitePath), `${href}: destination page must exist`);
}
const screenshotPaths = [...readme.matchAll(/<img\s+src="([^"]+)"/g)];
assert.ok(screenshotPaths.length > 0, "README must show application screenshots");
for (const [, asset] of screenshotPaths) {
  assert.ok(asset.startsWith("site/assets/app/masters/"), "README must reuse website screenshots");
  assert.ok(fs.existsSync(path.join(root, asset)), `${asset}: missing README screenshot`);
}

const notes = read("RELEASE_NOTES.md");
assert.match(notes, new RegExp(`^# Terento v${label}$`, "m"));
assert.ok(notes.includes(release.sha256), "release notes must contain the manifest DMG SHA-256");
assert.equal(
  release.downloadURL,
  `https://github.com/VooZ2/terento/releases/download/${releaseTag}/Terento-${label}-macOS-arm64.dmg`,
);
assert.equal(release.releaseURL, `https://github.com/VooZ2/terento/releases/tag/${releaseTag}`);
assert.equal(release.releaseNotesURL, release.releaseURL);
assert.match(read("README.md"), /Freizeitkarte[\s\S]*OpenTopoMap/);
assert.match(notes, /Freizeitkarte[\s\S]*OpenTopoMap/);
assert.doesNotMatch(
  notes,
  /(?:passes|pass)\s+\d+(?:\/\d+)?\s+tests?/i,
  "release notes must not contain a hand-maintained test count",
);

const project = read("Terento.xcodeproj/project.pbxproj");
const xcodeValues = (setting) => [
  ...project.matchAll(new RegExp(`\\b${setting} = (?:"([^"]+)"|([^;]+));`, "g")),
].map((match) => (match[1] || match[2]).trim());
const assertXcodeSetting = (setting, expected) => {
  const values = xcodeValues(setting);
  assert.ok(values.length > 0, `Xcode must define ${setting}`);
  assert.deepEqual(
    [...new Set(values)],
    [String(expected)],
    `Every Xcode ${setting} value must match the update manifest`,
  );
};
assertXcodeSetting("TERENTO_RELEASE_LABEL", label);
assertXcodeSetting("CURRENT_PROJECT_VERSION", release.build);
assertXcodeSetting("MARKETING_VERSION", release.version);

for (const locale of ["en", "de", "fr", "pl", "cs", "it"]) {
  const prefix = locale === "en" ? "" : `${locale}/`;
  const downloadPage = read(`site/${prefix}download/index.html`);
  assert.ok(downloadPage.includes(`v${label}`), `site/${prefix}download must show ${label}`);
  assert.ok(downloadPage.includes(release.downloadURL), `site/${prefix}download must use the manifest URL`);
  const guide = read(`site/${prefix}guides/install-garmin-maps-mac/index.html`);
  assert.match(
    guide,
    new RegExp(`\"dateModified\": \"${release.publishedAt}T00:00:00Z\"`),
    `site/${prefix}guides/install-garmin-maps-mac/index.html: guide review date must match the release date`,
  );
}
assert.doesNotMatch(
  read("site/localized-content.js"),
  /b(?:eta|êta)[ .]\d+/gi,
  "Runtime-localized Home and FAQ copy must remain release-neutral",
);

assert.doesNotMatch(
  read("backend/catalog-api/src/terento_catalog/admin.py"),
  /opted-in b(?:eta|êta)[ .]\d+/i,
  "Admin copy must remain release-neutral",
);

const nativeDependencyBuild = read("Packaging/NativeDependencies/build.sh");
assert.match(nativeDependencyBuild, /install_name_tool[\s\S]*-change[\s\S]*@rpath\/libusb-1\.0\.0\.dylib/);
assert.match(nativeDependencyBuild, /Developer-machine dependency found/);
assert.match(nativeDependencyBuild, /otool -L "\$dylib_path" \| sed '1d'/);

console.log(`Release documentation matches ${label}.`);
