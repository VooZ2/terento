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
// VERSIONING.md "Stable release": stable labels are X.Y.Z on main; prereleases
// are X.Y.Z-beta.N / X.Y.Z-rc.N on beta. One build counter is shared by every
// v*-buildN tag and only rises.
function parseLabel(releaseLabel) {
  const match = String(releaseLabel).match(/^((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))(?:-(beta|rc)\.([1-9]\d*))?$/);
  assert.ok(match, `unsupported release label: ${releaseLabel}`);
  return { base: match[1], family: match[2] || "stable", number: Number(match[3] || 0) };
}
function compareVersions(left, right) {
  const a = left.split(".").map(Number);
  const b = right.split(".").map(Number);
  for (let index = 0; index < 3; index += 1) if (a[index] !== b[index]) return a[index] - b[index];
  return 0;
}
function parseTag(tag) {
  const match = String(tag).match(/^v(.+)-build([1-9]\d*)$/);
  if (!match) return null;
  try {
    return { releaseLabel: match[1], build: Number(match[2]), ...parseLabel(match[1]) };
  } catch {
    return null;
  }
}
function nextPrereleaseLabels(previous) {
  if (previous.family === "beta") return [`${previous.base}-beta.${previous.number + 1}`, `${previous.base}-rc.1`];
  return [`${previous.base}-rc.${previous.number + 1}`];
}
// `published` is the main manifest; `tags` are the remote v*-buildN tags.
function candidateIdentity(candidate, published, tags = []) {
  if (!candidate) return published;
  assert.deepEqual(Object.keys(candidate).sort(), ["build", "releaseLabel", "version"]);
  const next = parseLabel(candidate.releaseLabel);
  assert.equal(candidate.version, next.base, "candidate marketing version must match its label");
  const current = parseLabel(published.releaseLabel);
  const tagged = tags.map(parseTag).filter(Boolean);
  const buildFloor = Math.max(published.build, ...tagged.map((tag) => tag.build));
  assert.ok(Number.isInteger(candidate.build) && candidate.build > buildFloor,
    "candidate build must be newer than the published build and every tagged build");
  if (next.family === "stable") {
    if (current.family === "stable") {
      // Same-label rebuild, or a newer patch, minor or major version.
      const [major, minor, patch] = current.base.split(".").map(Number);
      assert.ok([current.base, `${major}.${minor}.${patch + 1}`, `${major}.${minor + 1}.0`, `${major + 1}.0.0`]
        .includes(next.base), "a stable candidate must rebuild the published version or advance it by one step");
    } else {
      assert.equal(current.family, "rc", "only a release candidate becomes stable");
      assert.equal(next.base, current.base, "the stable release keeps its release candidate's version");
    }
    return candidate;
  }
  // Prerelease: never at or below a released stable version, whatever tags exist.
  assert.ok(compareVersions(next.base, current.base) > (current.family === "stable" ? 0 : -1),
    "a prerelease must be newer than the published stable release");
  assert.ok(!tagged.some((tag) => tag.family === "stable" && compareVersions(next.base, tag.base) <= 0),
    "a prerelease must be newer than every released stable version");
  // The predecessor is the highest build among prereleases of the same
  // marketing version (tags, plus a prerelease manifest).
  const prereleases = [...tagged, ...(current.family === "stable" ? [] : [{ ...published, ...current }])]
    .filter((item) => item.family !== "stable" && item.base === next.base)
    .sort((left, right) => left.build - right.build);
  const previous = prereleases.at(-1);
  if (!previous) {
    assert.ok(next.number === 1, "the first prerelease of a version is beta.1 or rc.1");
    assert.ok(compareVersions(next.base, current.base) > 0,
      "a new prerelease version must be newer than the published release");
    return candidate;
  }
  assert.ok(candidate.releaseLabel === previous.releaseLabel || nextPrereleaseLabels(previous).includes(candidate.releaseLabel),
    "candidate must retain the previous prerelease label or advance exactly one beta or release candidate");
  return candidate;
}
// Only a staged candidate needs the remote tags; reading them must not fail
// silently, or a stale local tag list could pick the wrong predecessor.
function remoteReleaseTags() {
  const output = require("node:child_process").execFileSync(
    "git", ["ls-remote", "--tags", "--refs", "origin", "refs/tags/v*"], { cwd: root, encoding: "utf8" });
  return output.split("\n").filter(Boolean).map((line) => {
    const match = line.match(/^[0-9a-f]{40}\trefs\/tags\/(v\S+)$/);
    assert.ok(match, `unexpected git ls-remote line: ${line}`);
    return match[1];
  });
}
const stagedCandidate = fs.existsSync(candidatePath) ? JSON.parse(fs.readFileSync(candidatePath, "utf8")) : null;
const artifactIdentity = candidateIdentity(stagedCandidate, release, stagedCandidate ? remoteReleaseTags() : []);
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
  { version: "1.0.0", releaseLabel: "1.0.0-rc.2", build: 33 },
  { version: "1.0.0", releaseLabel: "1.0.0-rc.1-local", build: 33 },
  { version: "1.0.0", releaseLabel: "1.0.0-RC.1", build: 33 },
  { version: "1.0.0", releaseLabel: "1.0.0-rc.1", build: 32 },
]) assert.throws(() => candidateIdentity(candidate, stagedBeta));
// The first release candidate follows the last beta and keeps the build counter.
const lastBeta = { version: "1.0.0", releaseLabel: "1.0.0-beta.18", build: 40 };
assert.equal(candidateIdentity({ version: "1.0.0", releaseLabel: "1.0.0-rc.1", build: 41 }, lastBeta).releaseLabel, "1.0.0-rc.1");
const stagedRc = { version: "1.0.0", releaseLabel: "1.0.0-rc.1", build: 41 };
for (const releaseLabel of ["1.0.0-rc.1", "1.0.0-rc.2", "1.0.0"]) {
  assert.equal(candidateIdentity({ version: "1.0.0", releaseLabel, build: 42 }, stagedRc).releaseLabel, releaseLabel);
}
for (const candidate of [
  { version: "1.0.0", releaseLabel: "1.0.0-beta.19", build: 42 },
  { version: "1.0.0", releaseLabel: "1.0.0-rc.3", build: 42 },
  { version: "1.0.0", releaseLabel: "1.0.0", build: 41 },
  { version: "1.0.0", releaseLabel: "1.0.0-rc.2", build: 41 },
  { version: "1.0.0", releaseLabel: "1.0.0-rc.2-local", build: 42 },
  { version: "1.0.0", releaseLabel: "1.0.0-local", build: 42 },
  { version: "1.0.1", releaseLabel: "1.0.1", build: 42 },
  { version: "1.0.0", releaseLabel: "1.0.0", build: "42" },
  { version: "1.1.0", releaseLabel: "1.0.0", build: 42 },
]) assert.throws(() => candidateIdentity(candidate, stagedRc));
// After 1.0.0 the main manifest stays stable: stable rebuilds and patches, and
// next-version prereleases from beta that are released only as GitHub prereleases.
const stable = { version: "1.0.0", releaseLabel: "1.0.0", build: 44 };
for (const [version, releaseLabel] of [["1.0.0", "1.0.0"], ["1.0.1", "1.0.1"], ["1.1.0", "1.1.0"], ["2.0.0", "2.0.0"],
  ["1.1.0", "1.1.0-beta.1"], ["1.1.0", "1.1.0-rc.1"], ["1.0.1", "1.0.1-rc.1"]]) {
  assert.equal(candidateIdentity({ version, releaseLabel, build: 45 }, stable).releaseLabel, releaseLabel);
}
for (const candidate of [
  { version: "1.0.2", releaseLabel: "1.0.2", build: 45 },
  { version: "1.2.0", releaseLabel: "1.2.0", build: 45 },
  { version: "0.9.0", releaseLabel: "0.9.0", build: 45 },
  { version: "1.1.0", releaseLabel: "1.1.0-beta.2", build: 45 },
  { version: "1.0.0", releaseLabel: "1.0.0-rc.4", build: 45 },
  { version: "1.0.0", releaseLabel: "1.0.0-beta.1", build: 45 },
  { version: "1.0.0", releaseLabel: "1.0.0", build: 44 },
]) assert.throws(() => candidateIdentity(candidate, stable));
// The build floor covers every tag: stable 44 plus a released beta build 50.
const afterBeta = ["v1.0.0-build44", "v1.1.0-beta.1-build50", "v1.0.0-rc.3-build43", "not-a-tag"];
assert.throws(() => candidateIdentity({ version: "1.0.1", releaseLabel: "1.0.1", build: 45 }, stable, afterBeta));
assert.equal(candidateIdentity({ version: "1.0.1", releaseLabel: "1.0.1", build: 51 }, stable, afterBeta).build, 51);
// The prerelease predecessor is the highest build of the same version, ordered by number (9 < 10).
const betaTags = ["v1.1.0-beta.1-build9", "v1.1.0-beta.2-build10", "v1.0.0-build8"];
const stableBuild8 = { version: "1.0.0", releaseLabel: "1.0.0", build: 8 };
for (const releaseLabel of ["1.1.0-beta.2", "1.1.0-beta.3", "1.1.0-rc.1"]) {
  assert.equal(candidateIdentity({ version: "1.1.0", releaseLabel, build: 11 }, stableBuild8, betaTags).releaseLabel, releaseLabel);
}
for (const releaseLabel of ["1.1.0-beta.1", "1.1.0-beta.4", "1.1.0-rc.2"]) {
  assert.throws(() => candidateIdentity({ version: "1.1.0", releaseLabel, build: 11 }, stableBuild8, betaTags));
}
assert.throws(() => candidateIdentity({ version: "1.1.0", releaseLabel: "1.1.0-beta.3", build: 10 }, stableBuild8, betaTags));
// Historical tags never reopen a released or older version for prereleases.
const historical = ["v1.0.0-rc.3-build43", "v1.0.0-build44", "v0.9.0-beta.1-build5"];
for (const [version, releaseLabel] of [["1.0.0", "1.0.0-rc.4"], ["0.9.0", "0.9.0-beta.2"], ["0.9.0", "0.9.0-rc.1"]]) {
  assert.throws(() => candidateIdentity({ version, releaseLabel, build: 45 }, stable, historical));
}
// A stale main manifest does not hide a released stable tag.
assert.throws(() => candidateIdentity({ version: "1.0.0", releaseLabel: "1.0.0-rc.4", build: 45 },
  { version: "1.0.0", releaseLabel: "1.0.0-rc.3", build: 43 }, historical));
assert.throws(() => candidateIdentity({ version: "0.9.0", releaseLabel: "0.9.0-beta.2", build: 44 },
  { version: "1.0.0", releaseLabel: "1.0.0-rc.3", build: 43 }, ["v0.9.0-beta.1-build5"]));
assert.equal(candidateIdentity({ version: "1.1.0", releaseLabel: "1.1.0-beta.1", build: 45 }, stable, historical).releaseLabel,
  "1.1.0-beta.1");
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
// A staged candidate may carry one draft section above the published release.
// The draft is explicitly marked; DRAFT/TODO markers never survive into a
// published section, and with no staged candidate none may remain at all.
function publishedReleaseNotes(text, published, candidate) {
  const publishedTitle = `# Terento v${published.releaseLabel} (build ${published.build})`;
  const lines = text.split(/\r?\n/);
  const markers = /<!--\s*(?:DRAFT|TODO)\b/;
  if (lines[0] === publishedTitle) {
    assert.doesNotMatch(text, markers, "published release notes must not keep DRAFT or TODO markers");
    return text;
  }
  assert.ok(candidate && candidate !== published,
    "release-note title must match the exact manifest release label and public build");
  assert.equal(lines[0], `# Terento v${candidate.releaseLabel} (build ${candidate.build})`,
    "a draft release-note section must name the staged candidate label and build");
  assert.match(lines.slice(1, 4).join("\n"), /<!--\s*DRAFT:/, "a draft release-note section must be marked as a draft");
  const publishedIndex = lines.indexOf(publishedTitle);
  assert.ok(publishedIndex > 0, "the published release-note section must follow the draft section");
  const publishedSection = lines.slice(publishedIndex).join("\n");
  assert.doesNotMatch(publishedSection, markers, "DRAFT or TODO markers must stay in the draft section");
  return publishedSection;
}
const stagedNotesCandidate = { version: "1.0.0", releaseLabel: "1.0.0-rc.1", build: 41 };
const stagedNotesPublished = { releaseLabel: "1.0.0-beta.18", build: 40 };
const draftNotes = "# Terento v1.0.0-rc.1 (build 41)\n\n<!-- DRAFT: unpublished -->\n<!-- TODO: note -->\n\n# Terento v1.0.0-beta.18 (build 40)\n\nPublished.\n";
assert.equal(publishedReleaseNotes(draftNotes, stagedNotesPublished, stagedNotesCandidate),
  "# Terento v1.0.0-beta.18 (build 40)\n\nPublished.\n");
for (const invalidNotes of [
  draftNotes.replace("<!-- DRAFT: unpublished -->\n", ""),
  draftNotes.replace("(build 41)", "(build 42)"),
  draftNotes.replace("Published.", "Published.\n<!-- TODO: leaked -->"),
  draftNotes.replace("# Terento v1.0.0-beta.18 (build 40)", "# Terento v1.0.0-beta.17 (build 39)"),
]) assert.throws(() => publishedReleaseNotes(invalidNotes, stagedNotesPublished, stagedNotesCandidate));
assert.throws(() => publishedReleaseNotes(draftNotes, stagedNotesPublished, stagedNotesPublished));
assert.throws(() => publishedReleaseNotes("# Terento v1.0.0-beta.18 (build 40)\n<!-- TODO: x -->\n", stagedNotesPublished, stagedNotesPublished));
publishedReleaseNotes(notes, release, artifactIdentity);

// From 1.0.0-rc.1 onward every section is: title, optional DRAFT/TODO
// comments, a short intro, then WHAT'S NEW?, WHAT'S FIXED? and KNOWN ISSUES
// as bullet lists (Packaging/README.md, "Release notes format").
const releaseNoteBlocks = ["## WHAT'S NEW?", "## WHAT'S FIXED?", "## KNOWN ISSUES"];
function assertReleaseNoteFormat(section, title) {
  const body = section.split(/\r?\n/).slice(1).join("\n").replace(/<!--[\s\S]*?-->/g, "");
  const headings = body.split("\n").filter((line) => /^#{1,6}\s/.test(line));
  assert.deepEqual(headings, releaseNoteBlocks, `${title}: release notes need exactly the three blocks in order`);
  const intro = body.slice(0, body.indexOf(releaseNoteBlocks[0])).trim();
  assert.ok(intro.length > 0, `${title}: release notes need a short intro`);
  assert.ok(intro.split(/\n\s*\n/).length <= 2, `${title}: the intro is at most two short paragraphs`);
  assert.doesNotMatch(intro, /^\s*[-*]\s/m, `${title}: the intro is prose, not a list`);
  releaseNoteBlocks.forEach((heading, index) => {
    const start = body.indexOf(heading) + heading.length;
    const end = index + 1 < releaseNoteBlocks.length ? body.indexOf(releaseNoteBlocks[index + 1]) : body.length;
    const lines = body.slice(start, end).split("\n").map((line) => line.trim()).filter(Boolean);
    assert.ok(lines.length > 0, `${title}: ${heading} needs at least one bullet`);
    assert.ok(lines.every((line) => /^- \S/.test(line)), `${title}: ${heading} is a bullet list`);
  });
}
function releaseNoteSections(text) {
  const sections = [];
  const pattern = /^# Terento v(\S+) \(build (\d+)\)$/gm;
  const matches = [...text.matchAll(pattern)];
  matches.forEach((match, index) => {
    const end = index + 1 < matches.length ? matches[index + 1].index : text.length;
    sections.push({ label: match[1], title: match[0], text: text.slice(match.index, end) });
  });
  return sections;
}
const formattedSample = "# Terento v1.0.0-rc.2 (build 42)\n\n<!-- DRAFT: x -->\n\nIntro.\n\n## WHAT'S NEW?\n\n- New.\n\n## WHAT'S FIXED?\n\n- No fixes in this release.\n\n## KNOWN ISSUES\n\n- Issue.\n";
assertReleaseNoteFormat(formattedSample, "sample");
for (const invalid of [
  formattedSample.replace("## WHAT'S FIXED?\n\n- No fixes in this release.\n\n", ""),
  formattedSample.replace("## KNOWN ISSUES", "## Known issues and limits"),
  formattedSample.replace("Intro.\n\n", ""),
  formattedSample.replace("- New.", "New."),
  formattedSample.replace("- New.", "- New.\n\n## Validation\n\n- Watch."),
  formattedSample.replace("## WHAT'S NEW?", "## WHAT'S FIXED?").replace("## WHAT'S FIXED?\n\n- No", "## WHAT'S NEW?\n\n- No"),
]) assert.throws(() => assertReleaseNoteFormat(invalid, "invalid sample"));
const formattedSections = releaseNoteSections(notes).filter((section) => !/-beta\.\d+$/.test(section.label));
assert.ok(formattedSections.length > 0 || !artifactIdentity || /-beta\./.test(artifactIdentity.releaseLabel),
  "a release candidate or stable section must exist in the new format");
for (const section of formattedSections) assertReleaseNoteFormat(section.text, section.title);
// Real-device release gates (VERSIONING.md "Stable release"): PASS, FAIL or an
// owner-dated DEFERRED that a stable release must list under KNOWN ISSUES.
function assertHardwareGates(gates, candidate, notesText) {
  assert.equal(gates.schemaVersion, 1);
  const isStable = parseLabel(candidate.releaseLabel).family === "stable";
  const section = releaseNoteSections(notesText).find((item) => item.label === candidate.releaseLabel);
  const knownIssues = section ? section.text.split("## KNOWN ISSUES")[1] || "" : "";
  for (const gate of gates.gates) {
    assert.ok(["PASS", "FAIL", "DEFERRED"].includes(gate.status), `${gate.id}: unknown gate status`);
    if (gate.status === "DEFERRED") {
      assert.equal(gate.decidedBy, "owner", `${gate.id}: only the owner may defer a gate`);
      assert.match(gate.decidedAt || "", /^\d{4}-\d{2}-\d{2}$/, `${gate.id}: a deferral needs its decision date`);
      assert.ok(gate.knownIssue, `${gate.id}: a deferral needs its KNOWN ISSUES line`);
    }
    if (!isStable) continue;
    assert.notEqual(gate.status, "FAIL", `${gate.id}: a failed gate blocks a stable release`);
    if (gate.status === "DEFERRED") {
      assert.ok(knownIssues.includes(gate.knownIssue), `${gate.id}: the stable release notes must list the deferred gate`);
    }
  }
}
const sampleGates = { schemaVersion: 1, gates: [{ id: "g", status: "DEFERRED", decidedBy: "owner", decidedAt: "2026-10-14", knownIssue: "Gate open." }] };
const stableNotes = "# Terento v1.0.0 (build 44)\n\nIntro.\n\n## WHAT'S NEW?\n\n- New.\n\n## WHAT'S FIXED?\n\n- Fix.\n\n## KNOWN ISSUES\n\n- Gate open.\n";
const stableCandidate = { version: "1.0.0", releaseLabel: "1.0.0", build: 44 };
assertHardwareGates(sampleGates, stableCandidate, stableNotes);
assertHardwareGates(sampleGates, { version: "1.0.0", releaseLabel: "1.0.0-rc.3", build: 43 }, "");
for (const [gates, text] of [
  [sampleGates, stableNotes.replace("- Gate open.", "- Other.")],
  [{ ...sampleGates, gates: [{ ...sampleGates.gates[0], status: "FAIL" }] }, stableNotes],
  [{ ...sampleGates, gates: [{ ...sampleGates.gates[0], status: "PENDING" }] }, stableNotes],
  [{ ...sampleGates, gates: [{ ...sampleGates.gates[0], decidedAt: "" }] }, stableNotes],
  [{ ...sampleGates, gates: [{ ...sampleGates.gates[0], decidedBy: "ci" }] }, stableNotes],
]) assert.throws(() => assertHardwareGates(gates, stableCandidate, text));
assertHardwareGates(JSON.parse(read("contracts/release-hardware-gates.json")), artifactIdentity, notes);
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
// The app trusts TerentoReleaseChannel and treats a missing value as beta, so
// the reviewed candidate label decides the channel (VERSIONING.md).
const expectedReleaseChannel = (releaseLabel) =>
  parseLabel(String(releaseLabel).replace(/-local$/, "")).family === "stable" ? "stable" : "beta";
for (const [releaseLabel, channel] of [["1.0.0", "stable"], ["1.0.0-local", "stable"], ["1.0.0-rc.3", "beta"],
  ["1.1.0-beta.1-local", "beta"]]) assert.equal(expectedReleaseChannel(releaseLabel), channel);
assert.throws(() => expectedReleaseChannel("1.0.0-RC.1"));
assertXcodeSetting("TERENTO_RELEASE_CHANNEL", expectedReleaseChannel(artifactIdentity.releaseLabel));

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
  read("scripts/templates/home-copy.json"),
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
  read("scripts/templates/home-copy.json"),
  /b(?:eta|êta)[ .]\d+/gi,
  "Generated Home and FAQ copy must remain release-neutral",
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
