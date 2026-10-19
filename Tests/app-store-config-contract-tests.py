#!/usr/bin/env python3
"""Static contract for the AppStore build configuration (App Store plan, stage 1).

The macOS CI job builds the configuration and inspects the signed bundle
(Packaging/AppStore/verify-app-store-build.sh). This test runs anywhere and
checks the sources that decide that bundle: entitlements, Xcode settings,
container migration manifests, and that update, donation and diagnostics-upload
code is compiled out of the AppStore configuration but still present in the
DMG configuration.
"""

from __future__ import annotations

import plistlib
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "Terento.xcodeproj" / "project.pbxproj"
APP_STORE_DIR = ROOT / "Packaging" / "AppStore"
SWIFT_SOURCES = ROOT / "app" / "TerentoCore" / "Sources" / "TerentoPoC"

APP_ENTITLEMENTS = {
    "com.apple.security.app-sandbox": True,
    "com.apple.security.device.usb": True,
    "com.apple.security.files.user-selected.read-write": True,
    "com.apple.security.network.client": True,
}
HELPER_ENTITLEMENTS = {
    "com.apple.security.app-sandbox": True,
    "com.apple.security.inherit": True,
}
# Plan section 1a: migrate these DMG items unchanged; mixed JSON files are copied
# whole because the manifest cannot filter file content.
MIGRATED_ITEMS = [
    ".device-key-secret",
    "devices",
    "failed-install-recovery.json",
    "MutationEvidence",
    "installation-evidence.json",
    "update-evidence.json",
    "map-statistics-events.json",
]
NOT_MIGRATED = [
    "app-funnel-events.json",
    "compatibility-status.json",
    "DeviceAssets",
    "support-report-unsent.json",
]
FORBIDDEN_IN_APP_STORE = [
    "updates/macos-arm64.json",
    "buymeacoffee",
    "api.terento.app/compatibility/events",
    "api.terento.app/map-events",
    "api.terento.app/app-funnel/events",
    "api.terento.app/support/reports",
]
# Settings in which the AppStore target configuration may differ from Release.
APP_STORE_DIFFERENCES = {
    "CODE_SIGN_ENTITLEMENTS",
    "CODE_SIGN_IDENTITY",
    "ENABLE_HARDENED_RUNTIME",
    "SWIFT_ACTIVE_COMPILATION_CONDITIONS",
    "TERENTO_APP_STORE_SANDBOX",
    "TERENTO_CONTAINER_MIGRATION_MANIFEST",
}


def load_plist(path: Path):
    with path.open("rb") as handle:
        return plistlib.load(handle)


def configurations(project: str) -> dict[str, list[dict[str, str]]]:
    """Map configuration name to the parsed settings of each such block."""
    found: dict[str, list[dict[str, str]]] = {}
    pattern = re.compile(
        r"^\t\t[0-9A-Fa-f]{24} /\* (\w+) \*/ = \{\n\t\t\tisa = XCBuildConfiguration;\n"
        r"\t\t\tbuildSettings = \{\n(.*?)\n\t\t\t\};\n\t\t\tname = (\w+);",
        re.M | re.S,
    )
    for match in pattern.finditer(project):
        comment, body, name = match.groups()
        assert comment == name, f"configuration comment {comment} differs from name {name}"
        settings: dict[str, str] = {}
        for setting in re.finditer(r"^\t\t\t\t(\w+) = (\(.*?\)|[^;]*);", body, re.M | re.S):
            settings[setting.group(1)] = re.sub(r"\s+", " ", setting.group(2)).strip()
        found.setdefault(name, []).append(settings)
    return found


def target_configuration(project: str, name: str) -> dict[str, str]:
    blocks = [block for block in configurations(project)[name] if "PRODUCT_BUNDLE_IDENTIFIER" in block]
    assert len(blocks) == 1, f"expected one target configuration named {name}"
    return blocks[0]


def condition_is_true(expression: str, defined: set[str]) -> bool:
    python = re.sub(r"\b(canImport|os|arch|compiler|swift|targetEnvironment)\([^)]*\)", "False", expression)
    python = python.replace("&&", " and ").replace("||", " or ")
    python = re.sub(r"!(?!=)", " not ", python)
    python = re.sub(
        r"\b[A-Za-z_]\w*\b",
        lambda token: token.group(0)
        if token.group(0) in {"and", "or", "not", "False", "True"}
        else str(token.group(0) in defined),
        python,
    )
    return bool(eval(python, {"__builtins__": {}}, {}))  # noqa: S307 - sanitized boolean only


def active_source(text: str, defined: set[str]) -> str:
    """Swift source with inactive #if branches removed."""
    stack: list[tuple[bool, bool]] = []  # (branch active, some branch taken)
    active_lines: list[str] = []
    for line in text.splitlines():
        directive = re.match(r"\s*#(if|elseif|else|endif)\b(.*)", line)
        enclosing = all(active for active, _ in stack)
        if directive:
            kind, expression = directive.group(1), directive.group(2).strip()
            if kind == "if":
                value = condition_is_true(expression, defined)
                stack.append((value, value))
            elif kind == "elseif":
                _, taken = stack.pop()
                value = not taken and condition_is_true(expression, defined)
                stack.append((value, taken or value))
            elif kind == "else":
                _, taken = stack.pop()
                stack.append((not taken, True))
            else:
                stack.pop()
            continue
        if enclosing:
            active_lines.append(line)
    assert not stack, "unbalanced #if"
    return "\n".join(active_lines)


class AppStoreConfigurationContract(unittest.TestCase):
    def setUp(self) -> None:
        self.project = PROJECT.read_text(encoding="utf-8")

    def test_entitlements_are_exact(self) -> None:
        self.assertEqual(load_plist(ROOT / "app/Terento/Terento-AppStore.entitlements"), APP_ENTITLEMENTS)
        self.assertEqual(
            load_plist(ROOT / "app/Terento/TerentoFinishingWorker-AppStore.entitlements"), HELPER_ENTITLEMENTS
        )
        # The DMG/GitHub build keeps its empty entitlements.
        self.assertEqual(load_plist(ROOT / "app/Terento/Terento.entitlements"), {})

    def test_app_store_configuration_mirrors_release(self) -> None:
        release = target_configuration(self.project, "Release")
        app_store = target_configuration(self.project, "AppStore")
        for key in sorted(set(release) | set(app_store)):
            if key not in APP_STORE_DIFFERENCES:
                self.assertEqual(app_store.get(key), release.get(key), f"AppStore must match Release for {key}")
        self.assertEqual(app_store["CODE_SIGN_ENTITLEMENTS"], '"app/Terento/Terento-AppStore.entitlements"')
        self.assertIn("TERENTO_APP_STORE", app_store["SWIFT_ACTIVE_COMPILATION_CONDITIONS"].strip('"').split())
        self.assertEqual(app_store["TERENTO_APP_STORE_SANDBOX"], "YES")
        self.assertEqual(app_store["CODE_SIGN_INJECT_BASE_ENTITLEMENTS"], "NO")
        self.assertEqual(app_store["PRODUCT_BUNDLE_IDENTIFIER"], "app.terento.mac")
        self.assertEqual(app_store["TERENTO_CONTAINER_MIGRATION_MANIFEST"], '""')
        self.assertEqual(len(configurations(self.project)["AppStore"]), 2, "project and target need AppStore")
        for list_name in ('PBXProject "Terento"', 'PBXNativeTarget "Terento"'):
            configuration_list = re.search(
                r"/\* Build configuration list for " + re.escape(list_name) + r" \*/ = \{(.*?)\};",
                self.project,
                re.S,
            )
            self.assertIsNotNone(configuration_list)
            self.assertIn("/* AppStore */", configuration_list.group(1))

    def test_dmg_configurations_are_unchanged(self) -> None:
        for name in ("Debug", "Release"):
            settings = target_configuration(self.project, name)
            self.assertEqual(settings["CODE_SIGN_ENTITLEMENTS"], "app/Terento/Terento.entitlements")
            self.assertNotIn("TERENTO_APP_STORE", settings["SWIFT_ACTIVE_COMPILATION_CONDITIONS"])
            self.assertNotIn("TERENTO_APP_STORE_SANDBOX", settings)
        release_config = (ROOT / "Packaging/release-config.sh").read_text(encoding="utf-8")
        self.assertIn('RELEASE_CONFIGURATION="Release"', release_config)
        self.assertIn('RELEASE_ENTITLEMENTS="app/Terento/Terento.entitlements"', release_config)

    def test_helper_phase_runs_last_and_only_for_app_store(self) -> None:
        phases = re.search(r"buildPhases = \((.*?)\);", self.project, re.S).group(1)
        names = re.findall(r"/\* (.*?) \*/", phases)
        self.assertEqual(names[-2:], ["Frameworks", "Embed App Store sandbox helper"])
        script = (APP_STORE_DIR / "embed-sandbox-helper.sh").read_text(encoding="utf-8")
        self.assertIn('if [ "${TERENTO_APP_STORE_SANDBOX:-NO}" != "YES" ]; then\n    exit 0\nfi', script)
        self.assertIn('helper_name="TerentoFinishingWorker"', script)
        self.assertIn('[ "${ACTION:-build}" = "install" ]', script)
        worker = (SWIFT_SOURCES / "Installation/MTPMapInstallationTransport.swift").read_text(encoding="utf-8")
        self.assertIn('static let sandboxHelperName = "TerentoFinishingWorker"', worker)

    def test_production_migration_lists_exact_dmg_items(self) -> None:
        manifest = load_plist(APP_STORE_DIR / "container-migration.plist")
        self.assertEqual(set(manifest), {"Move"})
        self.assertEqual(manifest["Move"], [f"${{ApplicationSupport}}/Terento/{item}" for item in MIGRATED_ITEMS])
        for item in NOT_MIGRATED:
            self.assertFalse(any(item in path for path in manifest["Move"]), item)

    def test_local_test_migration_never_reads_real_data(self) -> None:
        manifest = load_plist(APP_STORE_DIR / "container-migration.sandboxtest.plist")
        self.assertEqual(set(manifest), {"Move"})
        self.assertEqual(
            manifest["Move"],
            [
                [
                    f"${{ApplicationSupport}}/TerentoSandboxTestSeed/{item}",
                    f"${{ApplicationSupport}}/Terento/{item}",
                ]
                for item in MIGRATED_ITEMS
            ],
        )
        script = (APP_STORE_DIR / "build-local-sandbox-test.sh").read_text(encoding="utf-8")
        self.assertIn('test_bundle_id="app.terento.mac.sandboxtest"', script)
        self.assertIn('PRODUCT_BUNDLE_IDENTIFIER="$test_bundle_id"', script)
        self.assertIn('TERENTO_CONTAINER_MIGRATION_MANIFEST="$test_manifest"', script)
        self.assertNotIn("container-migration.plist\"", script.replace("Resources/container-migration.plist", ""))
        # The output folder is fixed: an override could point the build and
        # the printed cleanup command at the real DMG data.
        self.assertIn('output="$HOME/TerentoSandboxTest"', script)
        self.assertNotIn("TERENTO_SANDBOX_TEST_OUTPUT", script)

    def test_helper_exits_unless_the_app_is_its_parent(self) -> None:
        app_store = {"RELEASE", "TERENTO_BUNDLED_MTP", "TERENTO_APP_STORE"}
        launcher = active_source((SWIFT_SOURCES / "MTPTransport" / "BoundedNativeProcess.swift").read_text(encoding="utf-8"), app_store)
        self.assertIn('helperEnvironment["TERENTO_PARENT_PID"] = String(getpid())', launcher)
        worker = active_source((SWIFT_SOURCES / "Installation" / "MTPMapInstallationTransport.swift").read_text(encoding="utf-8"), app_store)
        guard = worker.index('ProcessInfo.processInfo.environment["TERENTO_PARENT_PID"]')
        self.assertIn("getppid() == parent else { _exit(1) }", worker[guard:guard + 300])
        # The parent check runs before the request is read.
        self.assertLess(worker.index("exitWhenParentExits()\n"), worker.index("FileHandle.standardInput.read"))

    def test_app_store_build_queues_no_interrupted_download_events(self) -> None:
        source = (SWIFT_SOURCES / "Statistics" / "MapStatisticsEvent.swift").read_text(encoding="utf-8")
        app_store = active_source(source, {"RELEASE", "TERENTO_APP_STORE"})
        dmg = active_source(source, {"RELEASE"})
        self.assertIn("let queueInterrupted = false", app_store)
        self.assertIn("let queueInterrupted = file.consent?.choice != .declined", dmg)

    def test_uploads_update_check_and_donation_are_compiled_out(self) -> None:
        dmg = {"RELEASE", "TERENTO_BUNDLED_MTP"}
        app_store = dmg | {"TERENTO_APP_STORE"}
        dmg_text = []
        for source in sorted(SWIFT_SOURCES.rglob("*.swift")):
            text = source.read_text(encoding="utf-8")
            app_store_text = active_source(text, app_store)
            for needle in FORBIDDEN_IN_APP_STORE:
                self.assertFalse(needle in app_store_text, f"{source.relative_to(ROOT)} keeps {needle!r}")
            dmg_text.append(active_source(text, dmg))
        dmg_source = "\n".join(dmg_text)
        for needle in FORBIDDEN_IN_APP_STORE:
            self.assertTrue(needle in dmg_source, f"DMG build lost {needle!r}; the check would prove nothing")

    def test_preprocessor_evaluator(self) -> None:
        sample = "a\n#if !X\nb\n#else\nc\n#endif\n#if X && Y\nd\n#elseif canImport(Z)\ne\n#endif"
        self.assertEqual(active_source(sample, {"X"}), "a\nc")
        self.assertEqual(active_source(sample, {"X", "Y"}), "a\nc\nd")
        self.assertEqual(active_source(sample, set()), "a\nb")


if __name__ == "__main__":
    unittest.main()
