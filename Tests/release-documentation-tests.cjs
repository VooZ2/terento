"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), "utf8");
const release = JSON.parse(read("site/updates/macos-arm64.json"));
// A reviewed candidate can be merged and signed before its installer exists.
// Published URLs/checksums continue to describe the actually available build.
const candidatePath = path.join(root, "Packaging/release-candidate.json");
function candidateIdentity(candidate, published) {
  if (!candidate) return published;
  assert.deepEqual(Object.keys(candidate).sort(), ["build", "releaseLabel", "version"]);
  assert.equal(candidate.version, published.version, "candidate must preserve the marketing version");
  const beta = published.releaseLabel.match(/^(\d+\.\d+\.\d+)-beta\.([1-9]\d*)$/);
  assert.ok(beta, "candidate staging requires a published numbered beta");
  const nextLabel = `${beta[1]}-beta.${Number(beta[2]) + 1}`;
  assert.ok(candidate.releaseLabel === published.releaseLabel || candidate.releaseLabel === nextLabel,
    "candidate must retain the beta label or advance exactly one beta");
  assert.ok(Number.isInteger(candidate.build) && candidate.build > published.build,
    "candidate build must be newer than the published build");
  return candidate;
}
const artifactIdentity = candidateIdentity(
  fs.existsSync(candidatePath) ? JSON.parse(fs.readFileSync(candidatePath, "utf8")) : null, release,
);
assert.equal(candidateIdentity(null, release), release);
for (const invalid of [
  { ...release, build: release.build + 1 },
  { version: release.version, releaseLabel: release.releaseLabel, build: release.build },
  { version: release.version, releaseLabel: release.releaseLabel, build: release.build - 1 },
  { version: release.version, releaseLabel: `${release.releaseLabel}-local`, build: release.build + 1 },
]) assert.throws(() => candidateIdentity(invalid, release));
const stagedBeta = { version: "1.0.0", releaseLabel: "1.0.0-beta.12", build: 32 };
for (const releaseLabel of ["1.0.0-beta.12", "1.0.0-beta.13"]) {
  assert.equal(candidateIdentity({ version: "1.0.0", releaseLabel, build: 33 }, stagedBeta).releaseLabel, releaseLabel);
}
for (const candidate of [
  { version: "1.0.0", releaseLabel: "1.0.0-beta.11", build: 33 },
  { version: "1.0.0", releaseLabel: "1.0.0-beta.14", build: 33 },
  { version: "1.0.0", releaseLabel: "1.0.0", build: 33 },
  { version: "1.1.0", releaseLabel: "1.1.0-beta.13", build: 33 },
  { version: "1.0.0", releaseLabel: "1.0.0-beta.13-local", build: 33 },
  { version: "1.0.0", releaseLabel: "1.0.0-beta.13", build: 32 },
]) assert.throws(() => candidateIdentity(candidate, stagedBeta));
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
assert.ok(readme.includes(publicLabel), "README must identify the public beta label");
assert.match(readme, new RegExp(`build\\s+${release.build}\\b`, "i"), "README must identify the public build");
const compatibilitySection = readme.match(
  /## Requirements and compatibility[\s\S]*?(?=\n## Download and beta status)/,
)?.[0] || "";
assert.match(compatibilitySection, /successful-\s*installation\s+directory/i);
assert.match(
  compatibilitySection,
  /exact Garmin models and variants with at least one[\s\S]*successful shared installation/i,
);
assert.match(compatibilitySection, /list grows[\s\S]*installations are shared/i);
assert.match(compatibilitySection, /missing from the list does not mean it[\s\S]*unsupported/i);
assert.match(compatibilitySection, /Garmin smartwatches with map support/i);
assert.doesNotMatch(compatibilitySection, /official public list|single public list/i);
assert.doesNotMatch(
  compatibilitySection,
  /\*\*(?:Tested|Supported|Verified)\*\*\s*[—-]\s*\d/i,
  "README must not publish device support tiers",
);

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
assert.equal(notes.split(/\r?\n/, 1)[0], `# Terento v${label} (build ${release.build})`,
  "release-note title must match the exact manifest release label and public build");
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
    `Every Xcode ${setting} value must match the reviewed artifact identity`,
  );
};
const configurationBody = (name) => [...project.matchAll(new RegExp(`^\\s*[^\\n]*\\/\\* ${name} \\*\\/ = \\{([\\s\\S]*?)\\};\\s*name = ${name};`, "gm"))]
  .map((match) => match[1])
  .find((body) => body.includes("TERENTO_RELEASE_LABEL")) || "";
const debugReleaseLabel = configurationBody("Debug").match(/TERENTO_RELEASE_LABEL = "([^"]+)";/)?.[1];
const distributedReleaseLabel = configurationBody("Release").match(/TERENTO_RELEASE_LABEL = "([^"]+)";/)?.[1];
assert.match(debugReleaseLabel || "", semanticVersion, "Debug builds must carry a semantic release label");
assert.match(debugReleaseLabel || "", /-local$/, "Debug builds must be purgeable local telemetry");
assert.equal(distributedReleaseLabel, artifactIdentity.releaseLabel, "Release builds must match the reviewed artifact label");
assert.equal(debugReleaseLabel, `${artifactIdentity.releaseLabel}-local`, "Debug must match the candidate with local telemetry identity");
assert.doesNotMatch(label, /-local$/, "Public update manifests must never use a local release label");
assert.doesNotMatch(distributedReleaseLabel || "", /-local$/, "Public Release builds must never use a local release label");
assert.notEqual(distributedReleaseLabel, "development", "Public Release builds must never use development telemetry identity");
assertXcodeSetting("CURRENT_PROJECT_VERSION", artifactIdentity.build);
assertXcodeSetting("MARKETING_VERSION", artifactIdentity.version);

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
  const compatibilityMarkers = {
    en: [
      /at least one successful shared installation/i,
      /list grows as more successful installations are shared/i,
      /missing model does not mean it is unsupported/i,
    ],
    de: [
      /mindestens einer erfolgreich geteilten Installation/i,
      /Liste wächst/i,
      /Modell fehlt.*nicht.*unterstützt/i,
    ],
    fr: [
      /au moins une installation réussie partagée/i,
      /liste s’allonge/i,
      /absence d’un modèle.*ne signifie pas/i,
    ],
    pl: [
      /co najmniej jedną udaną.*udostępnioną instalacją/i,
      /Lista rośnie/i,
      /Brak modelu nie oznacza/i,
    ],
    cs: [
      /alespoň jednou úspěšnou sdílenou instalací/i,
      /Seznam se rozšiřuje/i,
      /model není.*neznamená/i,
    ],
    it: [
      /almeno un’installazione riuscita condivisa/i,
      /L’elenco cresce/i,
      /modello non è nell’elenco.*non significa/i,
    ],
  }[locale];
  for (const marker of compatibilityMarkers) {
    assert.match(guide, marker, `site/${prefix}guides/install-garmin-maps-mac: compatibility copy drift`);
  }
  assert.doesNotMatch(
    guide,
    /official(?:ly)?[^.]{0,80}(?:single|only|unique) public list|offizielle[^.]{0,100}einzige öffentliche Liste|liste publique unique|jedyną publiczną listą|jediným veřejným seznamem|unico elenco pubblico/i,
    `site/${prefix}guides/install-garmin-maps-mac: obsolete public-list wording`,
  );
}
const publicHelp = [
  read("README.md"),
  read("site/localized-content.js"),
  ...["", "de/", "fr/", "pl/", "cs/", "it/"].map(
    (prefix) => read(`site/${prefix}guides/install-garmin-maps-mac/index.html`),
  ),
].join("\n");
assert.doesNotMatch(
  publicHelp,
  /Beta scope|Available today|Choose a map and get moving/i,
  "public help must not retain retired UI copy",
);
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
assert.match(nativeDependencyBuild, /assert_required_mtp_transport_behaviors "\$libmtp_source"/);
assert.match(nativeDependencyBuild, /12-byte split header detection/);
assert.match(nativeDependencyBuild, /packet-aligned transfer detection/);
assert.match(nativeDependencyBuild, /zero-length terminating write/);

assert.match(nativeDependencyBuild, /ac_cv_func_pipe2=no/);
assert.match(nativeDependencyBuild, /libusb-\$LIBUSB_BUILD_POLICY/);
assert.match(nativeDependencyBuild, /Unsupported pipe2 import/);
assert.match(nativeDependencyBuild, /usb-runtime-smoke/);

const nativeDependencyDocumentation = read("Packaging/NativeDependencies/README.md");
assert.match(nativeDependencyDocumentation, /12-byte split-header detection/);
assert.match(nativeDependencyDocumentation, /zero-length terminating USB write/);

const packagingDocumentation = read("Packaging/README.md");
assert.match(packagingDocumentation, /new major macOS release/);
assert.match(packagingDocumentation, /future-OS result[\s\S]*pending/);

console.log(`Release documentation matches ${label}.`);

for (const name of ["Debug", "Release"]) {
  const body = configurationBody(name);
  for (const setting of ["GCC_PREPROCESSOR_DEFINITIONS", "SWIFT_ACTIVE_COMPILATION_CONDITIONS"]) {
    const matches = [...body.matchAll(new RegExp(`\\b${setting} = ([^;]+);`, "g"))];
    assert.equal(matches.length, 1, `${name} must define ${setting} exactly once`);
    assert.ok(matches[0][1].includes("TERENTO_BUNDLED_MTP"), `${name} must enable bundled USB context cleanup in ${setting}`);
  }
}
