"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const homeFiles = [
  path.join(root, "site", "index.html"),
  path.join(root, "site", "de", "index.html"),
  path.join(root, "site", "fr", "index.html"),
  path.join(root, "site", "pl", "index.html"),
  path.join(root, "site", "cs", "index.html"),
  path.join(root, "site", "it", "index.html"),
];

const read = (file) => fs.readFileSync(file, "utf8");
const styles = read(path.join(root, "site", "styles.css"));

for (const file of homeFiles) {
  const page = read(file);
  const experience = page.match(
    /<section class="experience section" id="about"[\s\S]*?<\/section>/
  )?.[0];
  assert.ok(experience, `${file}: missing Home experience section`);

  assert.match(experience, /<ol class="steps">/, `${file}: steps must use native ol`);
  assert.doesNotMatch(experience, /<div class="steps"/, `${file}: div steps wrapper remains`);
  assert.doesNotMatch(experience, /role="list(?:item)?"/, `${file}: redundant list ARIA role remains`);
  assert.doesNotMatch(experience, /<article class="step"/, `${file}: step must not be an article listitem`);

  const steps = [...experience.matchAll(/<li class="step">([\s\S]*?)<\/li>/g)];
  assert.equal(steps.length, 3, `${file}: expected exactly three workflow steps`);
  steps.forEach((step, index) => {
    const number = String(index + 1).padStart(2, "0");
    assert.match(
      step[1],
      new RegExp(`<p class="step-number" aria-hidden="true">${number}<\\/p>`),
      `${file}: visible step number ${number} must be decorative`
    );
    assert.match(step[1], /<h3>[^<]+<\/h3>/, `${file}: step ${number} is missing its title`);
  });
}

assert.doesNotMatch(styles, /<article class="step" role="listitem">/);
assert.match(styles, /\.steps\s*\{[^}]*margin:\s*72px 0 0;[^}]*padding:\s*0;[^}]*list-style:\s*none;/s);
assert.match(styles, /\.text-link\s*\{[^}]*color:\s*var\(--link-text\)/s);
assert.match(styles, /\.text-link:hover\s*\{[^}]*color:\s*var\(--link-text-hover\)/s);
assert.match(styles, /\.eyebrow\s*\{[^}]*color:\s*var\(--eyebrow-text\)/s);
assert.match(styles, /\.step-number\s*\{[^}]*color:\s*var\(--accent-text\)/s);
assert.match(styles, /\.consent-button\s*\{[^}]*border:\s*1px solid var\(--link-text\)/s);
assert.match(styles, /\.consent-button-primary,\s*\.consent-button-secondary\s*\{[^}]*color:\s*var\(--link-text\)/s);
assert.match(styles, /a:focus-visible,\s*button:focus-visible,\s*summary:focus-visible\s*\{[^}]*outline:\s*3px solid var\(--focus-ring\)/s);
assert.doesNotMatch(styles, /\.text-link\s*\{[^}]*opacity:/s);

const lightRoot = styles.match(/:root\s*\{([\s\S]*?)\n\}/)?.[1];
const darkRoot = styles.match(/@media \(prefers-color-scheme: dark\)\s*\{\s*:root\s*\{([\s\S]*?)\n  \}\n\}/)?.[1];
assert.ok(lightRoot, "missing light theme token block");
assert.ok(darkRoot, "missing dark theme token block");

const token = (block, name) => {
  const value = block.match(new RegExp(`--${name}:\\s*(#[0-9A-Fa-f]{6})`))?.[1];
  assert.ok(value, `missing hex token --${name}`);
  return value;
};

const luminance = (hex) => {
  const channels = [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16) / 255);
  const linear = channels.map((channel) => (
    channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
  ));
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
};

const contrast = (foreground, background) => {
  const foregroundLuminance = luminance(foreground);
  const backgroundLuminance = luminance(background);
  return (Math.max(foregroundLuminance, backgroundLuminance) + 0.05)
    / (Math.min(foregroundLuminance, backgroundLuminance) + 0.05);
};

const light = Object.fromEntries([
  "link-text", "link-text-hover", "accent-text", "muted-text", "eyebrow-text", "focus-ring",
  "off-white", "surface-muted",
].map((name) => [name, token(lightRoot, name)]));
const dark = Object.fromEntries([
  "link-text", "link-text-hover", "accent-text", "muted-text", "eyebrow-text", "focus-ring",
  "off-white", "surface-muted",
].map((name) => [name, token(darkRoot, name)]));

const assertContrast = (theme, foreground, background, minimum, label) => {
  const ratio = contrast(theme[foreground], theme[background]);
  assert.ok(
    ratio >= minimum,
    `${label}: ${theme[foreground]} on ${theme[background]} is only ${ratio.toFixed(2)}:1; expected ${minimum}:1`
  );
};

for (const [name, theme] of [["light", light], ["dark", dark]]) {
  assertContrast(theme, "link-text", "off-white", 4.5, `${name} Home hero link`);
  assertContrast(theme, "link-text-hover", "off-white", 4.5, `${name} text-link hover`);
  assertContrast(theme, "accent-text", "surface-muted", 4.5, `${name} step number`);
  assertContrast(theme, "eyebrow-text", "surface-muted", 4.5, `${name} How it works eyebrow`);
  assertContrast(theme, "muted-text", "surface-muted", 4.5, `${name} muted step description`);
  assertContrast(theme, "link-text", "surface-muted", 4.5, `${name} secondary consent action`);
  assertContrast(theme, "focus-ring", "off-white", 3, `${name} focus boundary on page`);
}

console.log("Home accessibility semantics and shared-token contrast tests passed.");
