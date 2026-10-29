#!/usr/bin/env python3
"""Static contract for the AppStore build configuration (App Store plan, stage 1).

The macOS CI job builds the configuration and inspects the signed bundle
(Packaging/AppStore/verify-app-store-build.sh). This test runs anywhere and
checks the sources that decide that bundle: entitlements, Xcode settings,
container migration manifests, that update, donation and support-report code
is compiled out of the AppStore configuration but still present in the DMG
configuration, and that the AppStore configuration sends other diagnostics only
after an explicit opt-in.
"""

from __future__ import annotations

import plistlib
import os
import re
import subprocess
import tempfile
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
    "api.terento.app/support/reports",
]
DMG_ONLY = {"RELEASE", "TERENTO_BUNDLED_MTP"}
APP_STORE_ONLY = DMG_ONLY | {"TERENTO_APP_STORE"}
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
        # A symbolic link at the output, seed or container is refused before
        # any write, and the output is a new folder on every run.
        guard = script.index('for path in "$output" "$seed" "$container"; do')
        self.assertIn('[ ! -L "$path" ] || die', script[guard:guard + 200])
        first_write = min(script.index('rm -rf "$seed"'), script.index('mkdir -m 700 "$seed"'), script.index('rm -rf "$output"'))
        self.assertLess(guard, first_write)
        self.assertNotIn("mkdir -p", script)
        fresh = script.index('rm -rf "$output"\nmkdir -m 700 "$output"\n')
        self.assertLess(fresh, script.index("xcodebuild \\"))

    def test_local_test_refuses_paths_that_reach_real_data(self) -> None:
        """Runs the script's path checks (they run before the macOS check)."""
        script = APP_STORE_DIR / "build-local-sandbox-test.sh"

        def run(layout) -> str:
            with tempfile.TemporaryDirectory() as home_name:
                home = Path(home_name)
                support = home / "Library" / "Application Support"
                (support / "Terento").mkdir(parents=True)
                (support / "Terento" / "devices").write_text("real", encoding="utf-8")
                layout(home, support)
                result = subprocess.run(["sh", str(script)], env={**os.environ, "HOME": str(home)},
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual((support / "Terento" / "devices").read_text(encoding="utf-8"), "real")
                self.assertNotEqual(result.returncode, 0)
                return result.stderr

        def nothing(home: Path, support: Path) -> None:
            pass

        def containers_into_real_data(home: Path, support: Path) -> None:
            (home / "Library" / "Containers").symlink_to(support / "Terento")
            (support / "Terento" / "app.terento.mac.sandboxtest").mkdir()

        def output_link(home: Path, support: Path) -> None:
            (home / "TerentoSandboxTest").symlink_to(support / "Terento")

        def output_holds_real_data(home: Path, support: Path) -> None:
            moved = home / "TerentoSandboxTest" / "data"
            moved.mkdir(parents=True)
            (support / "Terento" / "devices").rename(moved / "devices")
            (support / "Terento").rmdir()
            (support / "Terento").symlink_to(moved)

        def other_support_folder(home: Path, support: Path) -> None:
            elsewhere = home / "elsewhere"
            elsewhere.mkdir()
            (support / "TerentoSandboxTestSeed").mkdir()
            (home / "Library" / "Containers").symlink_to(elsewhere)

        self.assertIn("leads into the real Terento data", run(containers_into_real_data))
        self.assertIn("is a symbolic link", run(output_link))
        self.assertIn("contains the real Terento data", run(output_holds_real_data))
        # APFS ignores case, so paths are compared in lower case.
        self.assertIn("tr '[:upper:]' '[:lower:]'", script.read_text(encoding="utf-8"))
        # Safe layouts pass the checks; on macOS the script would go on to build.
        if os.uname().sysname != "Darwin":
            for layout in (nothing, other_support_folder):
                self.assertIn("Run this on macOS", run(layout), layout.__name__)

    def test_testflight_script_exports_and_checks_without_uploading(self) -> None:
        script = (APP_STORE_DIR / "archive-for-testflight.sh").read_text(encoding="utf-8")
        self.assertIn("-configuration AppStore", script)
        self.assertIn('. "$repo_root/Packaging/release-config.sh"', script)
        self.assertIn("<string>app-store-connect</string>", script)
        self.assertIn("<key>destination</key>\n    <string>export</string>", script)
        self.assertNotIn("<string>upload</string>", script)
        self.assertNotRegex(script, r"altool|notarytool|--upload")
        self.assertIn('output="$HOME/TerentoAppStoreArchive"', script)
        # The exported package, not only the archive, is checked.
        checks = script.index('/usr/sbin/pkgutil --expand-full "$pkg" "$check"')
        for needle in ('embedded.provisionprofile', 'container-migration.plist',
                       '"$output/helper-entitlements.plist"',
                       "TerentoFinishingWorker-AppStore.entitlements"):
            self.assertGreater(script.index(needle, checks), checks, needle)
        self.assertTrue(os.access(APP_STORE_DIR / "archive-for-testflight.sh", os.X_OK))
        # A repeat upload keeps the Release build number as its first part.
        self.assertIn('build_override="CURRENT_PROJECT_VERSION=$release_build.$sequence"', script)
        self.assertIn("    $build_override \\\n    archive", script)
        self.assertIn("Print :ITSAppUsesNonExemptEncryption", script[checks:])
        # Only the AppStore build phase adds the key; the DMG Info.plist stays as it is.
        embed = (APP_STORE_DIR / "embed-sandbox-helper.sh").read_text(encoding="utf-8")
        self.assertIn('"Add :ITSAppUsesNonExemptEncryption bool false"', embed)
        self.assertLess(embed.index('!= "YES" ]; then\n    exit 0'), embed.index('"Add :ITSAppUsesNonExemptEncryption'))
        self.assertNotIn("ITSAppUsesNonExemptEncryption", (ROOT / "app" / "Terento" / "Info.plist").read_text(encoding="utf-8"))

    def test_ci_scan_covers_all_bundle_code(self) -> None:
        verify = (APP_STORE_DIR / "verify-app-store-build.sh").read_text(encoding="utf-8")
        # Debug builds keep app code in Terento.debug.dylib and the libraries
        # live in Frameworks, so both folders are scanned file by file.
        self.assertIn('find "$app/Contents/MacOS" "$app/Contents/Frameworks" -type f >"$work/bundle-code.txt"', verify)
        self.assertIn('"$control_app/Contents/MacOS/"*', verify)

    def test_docs_say_migration_copies(self) -> None:
        readme = (APP_STORE_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn('"The\noperating system will copy the file"', readme)
        self.assertIn("The originals stay where they were.", readme)
        self.assertNotRegex(readme, r"(?i)\bmoves?\b.{0,40}\bcontainer\b")

    def test_helper_exits_unless_the_app_is_its_parent(self) -> None:
        app_store = {"RELEASE", "TERENTO_BUNDLED_MTP", "TERENTO_APP_STORE"}
        launcher = active_source((SWIFT_SOURCES / "MTPTransport" / "BoundedNativeProcess.swift").read_text(encoding="utf-8"), app_store)
        self.assertIn('helperEnvironment["TERENTO_PARENT_PID"] = String(getpid())', launcher)
        worker = active_source((SWIFT_SOURCES / "Installation" / "MTPMapInstallationTransport.swift").read_text(encoding="utf-8"), app_store)
        guard = worker.index('ProcessInfo.processInfo.environment["TERENTO_PARENT_PID"]')
        self.assertIn("getppid() == parent else { _exit(1) }", worker[guard:guard + 300])
        # The parent check runs before the request is read, and the watchdog
        # that ends the helper with the app is started.
        self.assertLess(worker.index("exitWhenParentExits()\n"), worker.index("FileHandle.standardInput.read"))
        watchdog = worker.index("let watchdog = Thread {")
        self.assertIn("while getppid() == parent { usleep(200_000) }\n            _exit(1)", worker[watchdog:watchdog + 200])
        self.assertIn("watchdog.start()", worker[watchdog:watchdog + 300])
        # The helper copy never starts as a second app without the worker arguments.
        self.assertLess(worker.index("if !isWorker, URL(fileURLWithPath: CommandLine.arguments[0]).lastPathComponent == sandboxHelperName { return true }"),
                        worker.index("guard isWorker else { return false }"))
        # The app never signals a helper by PID at quit (a reused PID could
        # belong to another process); the watchdog alone ends the helper.
        app = active_source((SWIFT_SOURCES / "TerentoPoCApp.swift").read_text(encoding="utf-8"), app_store)
        self.assertNotIn("BoundedNativeChildren", launcher + app)
        self.assertNotIn("terminateAll", launcher + app)

    def test_sharing_is_opt_in_and_ignores_migrated_choices(self) -> None:
        for path, consent, dmg_version, queue in (
            ("Compatibility/InstallationEvidence.swift", "VersionedEvidenceConsent", 4, "file.pendingUploadEventIDs"),
            ("Statistics/MapStatisticsEvent.swift", "VersionedMapStatisticsConsent", 2, "file.pendingEvents"),
        ):
            source = (SWIFT_SOURCES / path).read_text(encoding="utf-8")
            app_store, dmg = active_source(source, APP_STORE_ONLY), active_source(source, DMG_ONLY)
            # Notice numbers never overlap, so a copied DMG choice is recognisable.
            self.assertIn("static let currentNoticeVersion = 100", app_store)
            self.assertIn(f"static let currentNoticeVersion = {dmg_version}", dmg)
            self.assertIn("return consent?.choice == .accepted && consent?.noticeVersion == currentNoticeVersion", app_store)
            self.assertIn("return consent?.choice != .declined", dmg)
            # Every opt-out test in the store and controller goes through the policy.
            self.assertNotIn("consent()?.choice != .declined", app_store)
            self.assertNotIn("guard file.consent?.choice != .declined,\n                  !file", app_store)
            # Start-up migration: only a refusal survives; every queue is dropped.
            migration = app_store[app_store.index("func migrateConsentToCurrentNotice() throws {"):]
            migration = migration[:migration.index("\n    }\n")]
            self.assertIn("consent.choice == .declined ? " + consent + "(", migration)
            self.assertIn(") : nil", migration)
            self.assertIn(queue + ".removeAll()", migration)
            self.assertIn("try? store.migrateConsentToCurrentNotice()", app_store)
            self.assertIn(f"{consent}.permitsSharing(", app_store)
        app = active_source((SWIFT_SOURCES / "TerentoPoCApp.swift").read_text(encoding="utf-8"), APP_STORE_ONLY)
        self.assertIn("VersionedEvidenceConsent.permitsSharing(evidenceStore.consent())", app)

    def test_app_store_events_are_labelled(self) -> None:
        metadata = (SWIFT_SOURCES / "Telemetry" / "TerentoTelemetryMetadata.swift").read_text(encoding="utf-8")
        self.assertIn("return appStoreEventReleaseLabel(releaseLabel)", active_source(metadata, APP_STORE_ONLY))
        self.assertIn('label + (label.contains("+") ? ".appstore" : "+appstore")', metadata)
        for path in ("Compatibility/InstallationEvidence.swift", "Statistics/MapStatisticsEvent.swift",
                     "Telemetry/AppFunnelTelemetry.swift"):
            source = (SWIFT_SOURCES / path).read_text(encoding="utf-8")
            self.assertIn("= TerentoTelemetryMetadata.eventReleaseLabel", source, path)
            self.assertNotIn("= TerentoTelemetryMetadata.releaseLabel", source, path)

    def test_sharing_prompt_and_review_request_are_app_store_only(self) -> None:
        source = (SWIFT_SOURCES / "Views" / "ConnectScreen.swift").read_text(encoding="utf-8")
        app_store, dmg = active_source(source, APP_STORE_ONLY), active_source(source, DMG_ONLY)
        for needle in ("InstallSharingDialog(", "requestReview()", '"Share install results with Terento"'):
            self.assertIn(needle, app_store)
            self.assertNotIn(needle, dmg)
        # Unticked until the person ticks it (no pre-ticked consent).
        self.assertIn("@State private var share = false", app_store)
        self.assertIn("evidenceController.decideConsent(share ? .accepted : .declined)", app_store)
        self.assertIn("mapStatisticsController.decideConsent(share ? .accepted : .declined)", app_store)
        self.assertIn("if share { evidenceController.shareOperation(evidenceOperationID) }", app_store)
        self.assertIn("mayRequest: !asksAboutSharing", app_store)
        self.assertIn('Image("CircleCheck")', app_store)
        icon = (ROOT / "app/Terento/Assets.xcassets/CircleCheck.imageset/circle-check.svg").read_text(encoding="utf-8")
        self.assertIn("Font Awesome Free 7.3.1", icon)
        self.assertIn("CircleCheck.imageset/circle-check.svg", (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8"))
        about = active_source((SWIFT_SOURCES / "Views" / "AboutTerentoView.swift").read_text(encoding="utf-8"), APP_STORE_ONLY)
        self.assertIn("TerentoAppLinks.appStoreReview", about)
        links = (SWIFT_SOURCES / "Views" / "AppLinks.swift").read_text(encoding="utf-8")
        self.assertIn("https://apps.apple.com/app/id6828556832?action=write-review", active_source(links, APP_STORE_ONLY))

    def test_uploads_update_check_and_donation_are_compiled_out(self) -> None:
        dmg, app_store = DMG_ONLY, APP_STORE_ONLY
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
