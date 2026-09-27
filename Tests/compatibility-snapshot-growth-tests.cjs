"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const repositoryRoot = path.resolve(__dirname, "..");
const sourceFiles = [
  "site/index.html",
  "site/metadata.json",
  "site/compatibility/index.html",
  "site/de/compatibility/index.html",
  "site/fr/compatibility/index.html",
  "site/pl/compatibility/index.html",
  "site/cs/compatibility/index.html",
  "site/it/compatibility/index.html",
  "site/compatibility/compatibility-data.js",
  "site/compatibility/compatibility-locales.js",
  "site/compatibility/compatibility.js",
  "scripts/build-compatibility-pages.py",
  "scripts/update-compatibility-snapshot.py",
];

function copySourceFiles(testRoot) {
  for (const relative of sourceFiles) {
    const destination = path.join(testRoot, relative);
    fs.mkdirSync(path.dirname(destination), { recursive: true });
    fs.copyFileSync(path.join(repositoryRoot, relative), destination);
  }
}

function run(command, args, options) {
  const result = spawnSync(command, args, { ...options, encoding: "utf8" });
  assert.equal(result.status, 0, `${command} ${args.join(" ")}\n${result.stdout}\n${result.stderr}`);
}

function createGeneratedSite(additionalModels) {
  const testRoot = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "terento-compatibility-growth-")));
  copySourceFiles(testRoot);

  const baseline = JSON.parse(fs.readFileSync(path.join(repositoryRoot, "site/compatibility/public-models.snapshot.json"), "utf8"));
  const payload = {
    generatedAt: baseline.generatedAt,
    models: [...baseline.models, ...additionalModels],
  };
  const payloadPath = path.join(testRoot, "compatibility-payload.json");
  fs.writeFileSync(payloadPath, JSON.stringify(payload));

  run("python3", [
    path.join(testRoot, "scripts/update-compatibility-snapshot.py"),
    "--input", payloadPath,
    "--output", path.join(testRoot, "site/compatibility/public-models.snapshot.json"),
    "--no-pages",
  ], { cwd: testRoot, env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
  run("python3", [path.join(testRoot, "scripts/build-compatibility-pages.py")], {
    cwd: testRoot,
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" },
  });
  const generatedSnapshot = JSON.parse(fs.readFileSync(path.join(testRoot, "site/compatibility/public-models.snapshot.json"), "utf8"));
  assert.equal(generatedSnapshot.models.length, baseline.models.length + additionalModels.length, "generated snapshot preserves factual growth");
  return { testRoot, baselineCount: baseline.models.length, expandedCount: generatedSnapshot.models.length };
}

const additionalModels = JSON.parse(fs.readFileSync(path.join(repositoryRoot, "Tests/fixtures/compatibility-snapshot-growth-models.json"), "utf8"));
const { testRoot, baselineCount, expandedCount } = createGeneratedSite(additionalModels);
try {
  run(process.execPath, [path.join(repositoryRoot, "Tests/shared-compatibility-data-tests.cjs")], {
    cwd: repositoryRoot,
    env: { ...process.env, TERENTO_COMPATIBILITY_TEST_ROOT: testRoot },
  });
  console.log(`PASS: shared compatibility assertions remain green after generated snapshot growth (${baselineCount} -> ${expandedCount} models)`);
} finally {
  fs.rmSync(testRoot, { recursive: true, force: true });
}
