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
  "scripts/build-markdown-pages.py",
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
  ], { cwd: testRoot, env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
  run("python3", [path.join(testRoot, "scripts/build-markdown-pages.py"), "--check",
    ...["", "de/", "fr/", "pl/", "cs/", "it/"].flatMap(prefix => ["--page", `/${prefix}compatibility/`])], {
    cwd: testRoot,
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" },
  });
  const before = sourceFiles.filter(file => file.endsWith("index.html") && file.includes("compatibility/"))
    .flatMap(file => [file, file.replace("index.html", "index.md")])
    .map(file => [file, fs.readFileSync(path.join(testRoot, file), "utf8")]);
  run("python3", [path.join(testRoot, "scripts/update-compatibility-snapshot.py"),
    "--input", payloadPath], { cwd: testRoot });
  for (const [file, contents] of before) {
    assert.equal(fs.readFileSync(path.join(testRoot, file), "utf8"), contents, `repeat refresh changed ${file}`);
  }
  const generatedSnapshot = JSON.parse(fs.readFileSync(path.join(testRoot, "site/compatibility/public-models.snapshot.json"), "utf8"));
  assert.equal(generatedSnapshot.models.length, baseline.models.length + additionalModels.length, "generated snapshot preserves factual growth");
  return { testRoot, baselineCount: baseline.models.length, expandedCount: generatedSnapshot.models.length };
}

function checkInstallationSplitValidation() {
  // The script reports output paths relative to its repository root, so run a copy.
  const directory = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "terento-compatibility-split-")));
  fs.mkdirSync(path.join(directory, "scripts"));
  fs.copyFileSync(path.join(repositoryRoot, "scripts/update-compatibility-snapshot.py"), path.join(directory, "scripts/update-compatibility-snapshot.py"));
  const snapshotFor = (model) => {
    const payloadPath = path.join(directory, "payload.json");
    const outputPath = path.join(directory, "snapshot.json");
    fs.rmSync(outputPath, { force: true });
    fs.writeFileSync(payloadPath, JSON.stringify({ generatedAt: "2026-10-11T10:00:00Z", models: [{ model: "fēnix 8 · 47 mm, AMOLED", family: "fenix", familyName: "fēnix", ...model }] }));
    const result = spawnSync("python3", [path.join(directory, "scripts/update-compatibility-snapshot.py"), "--input", payloadPath, "--output", outputPath, "--no-pages"], { encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
    return result.status === 0 ? JSON.parse(fs.readFileSync(outputPath, "utf8")).models[0] : result.stderr;
  };
  try {
    const split = snapshotFor({ successfulInstallations: 46, appSuccessfulInstallations: 40, webSuccessfulInstallations: 6, lastSuccessfulInstallation: "2026-10-11T09:00:00Z" });
    assert.deepEqual([split.successfulInstallations, split.appSuccessfulInstallations, split.webSuccessfulInstallations], [46, 40, 6]);
    assert.deepEqual(Object.keys(split).slice(-4), ["successfulInstallations", "appSuccessfulInstallations", "webSuccessfulInstallations", "lastSuccessfulInstallation"]);
    const legacy = snapshotFor({ successfulInstallations: 5 });
    assert.deepEqual([legacy.appSuccessfulInstallations, legacy.webSuccessfulInstallations], [5, 0], "older payloads count every success as app");
    for (const [label, model] of [
      ["only one split field", { successfulInstallations: 5, webSuccessfulInstallations: 1 }],
      ["split does not add up", { successfulInstallations: 5, appSuccessfulInstallations: 4, webSuccessfulInstallations: 2 }],
      ["negative split", { successfulInstallations: 5, appSuccessfulInstallations: 6, webSuccessfulInstallations: -1 }],
      ["fractional split", { successfulInstallations: 5, appSuccessfulInstallations: 4.5, webSuccessfulInstallations: 0.5 }],
      ["boolean split", { successfulInstallations: 1, appSuccessfulInstallations: true, webSuccessfulInstallations: 0 }],
    ]) {
      const error = snapshotFor(model);
      assert.equal(typeof error, "string", `${label}: rejected`);
      assert.match(error, /SuccessfulInstallations|successful installations/, `${label}: names the split`);
    }
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
  console.log("PASS: snapshot keeps and validates the app/web successful-installation split");
}

checkInstallationSplitValidation();

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
