#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
repo_root="$(cd "$project_root/../.." && pwd)"
libmtp_prefix="${LIBMTP_PREFIX:-/opt/homebrew/opt/libmtp}"
libusb_prefix="${LIBUSB_PREFIX:-/opt/homebrew/opt/libusb}"
swiftpm_config_dir="${SWIFTPM_CONFIG_DIR:-/tmp/terento-native-poc-swiftpm}"
module_cache_dir="${CLANG_MODULE_CACHE_PATH:-/tmp/terento-native-poc-module-cache}"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-troubleshooting-help-tests.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
binary_path="$build_dir/troubleshooting-help-tests"
swiftpm_arch="$(uname -m)"
platform_build_dir="$project_root/.build/${swiftpm_arch}-apple-macosx/debug"
bridge_object="$platform_build_dir/LibMTPBridge.build/MTPBridge.c.o"
bridge_module_dir="$platform_build_dir/LibMTPBridge.build"

export LIBMTP_PREFIX="$libmtp_prefix"
export LIBUSB_PREFIX="$libusb_prefix"
export CLANG_MODULE_CACHE_PATH="$module_cache_dir"
export SWIFTPM_CONFIG_DIR="$swiftpm_config_dir"

if [[ ! -f "$bridge_object" || ! -f "$bridge_module_dir/module.modulemap" ]]; then
  print "Building TerentoPoC so troubleshooting help tests can link LibMTPBridge…"
  swift build --build-system native --package-path "$project_root" --product TerentoPoC
fi

sources=()
while IFS= read -r source_file; do
  sources+=("$source_file")
done < <(
  find "$project_root/Sources/TerentoPoC" -name '*.swift' \
    ! -name 'TerentoPoCApp.swift' \
    ! -name 'ContentView.swift' \
    -print | sort
)

swiftc -D TERENTO_TESTING -target "${swiftpm_arch}-apple-macosx13.0" \
  -parse-as-library \
  -module-name TerentoTroubleshootingHelpTests \
  -I "$bridge_module_dir" \
  -L "$libmtp_prefix/lib" -lmtp \
  -L "$libusb_prefix/lib" -lusb-1.0 \
  "$bridge_object" \
  -Xlinker -rpath -Xlinker "$libmtp_prefix/lib" \
  -module-cache-path "$module_cache_dir" \
  "${sources[@]}" \
  "$project_root/Tests/TerentoPoCTests/TroubleshootingHelpTests.swift" \
  -o "$binary_path"

"$binary_path"

connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"
help_link="$project_root/Sources/TerentoPoC/Views/TerentoHelpLink.swift"
diagnostics="$project_root/Sources/TerentoPoC/Views/DiagnosticsView.swift"
app_source="$project_root/Sources/TerentoPoC/TerentoPoCApp.swift"

require() {
    local file="$1" text="$2" message="$3"
    if ! grep -Fq -- "$text" "$file"; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}

# The link is an Interactive Primary text link, not a filled button.
require "$help_link" 'Link(destination: topic.url)' 'Help is not a plain link to the mapped guide section'
require "$help_link" '.foregroundStyle(TerentoColors.interactive)' 'Help does not use Interactive Primary text'
require "$help_link" 'Label(title, systemImage: "questionmark.circle")' 'Help has no text and icon'
require "$help_link" 'var title = "Help"' 'Help link is not titled Help by default'
if grep -Fq 'PrimaryButton' "$help_link" || grep -Fq '.background(' "$help_link"; then
    print -u2 "FAIL: Help link must not be a second primary button"
    exit 1
fi
# No other file maps errors to guide URLs.
if grep -rn 'guides/troubleshooting' "$project_root/Sources/TerentoPoC" | grep -v 'Errors/TroubleshootingHelp.swift' | grep -q .; then
    print -u2 "FAIL: troubleshooting URLs must come only from TroubleshootingHelp.swift"
    exit 1
fi

# Help links appear only for problems: inside the installation failure dialog,
# in the Diagnostics window's send-report help, and inside the Connect page's
# help box (a live attention state, a final failure, or the "Still not showing
# up?" steps). Plain waiting, connecting and other normal, in-progress and
# inline states stay uncluttered.
require "$connect_screen" 'helpTopic: installationFailureHelpTopic' 'installation failure dialog has no Help link'
require "$connect_screen" 'TerentoHelpLink(topic: helpTopic)' 'error dialog does not render its Help link'
require "$diagnostics" 'TerentoHelpLink(topic: .sendReport)' 'Diagnostics failure report has no Help link'
python3 - "$project_root/Sources/TerentoPoC" <<'PYHELP'
from pathlib import Path
import re, sys
views = Path(sys.argv[1]) / 'Views'
uses = {}
for path in sorted(views.glob('*.swift')):
    if path.name == 'TerentoHelpLink.swift':
        continue
    count = path.read_text().count('TerentoHelpLink(')
    if count:
        uses[path.name] = count
assert uses == {'ConnectScreen.swift': 2, 'DiagnosticsView.swift': 1}, uses
screen = (views / 'ConnectScreen.swift').read_text()
start = screen.index('private struct TerentoConfirmationDialog: View {')
end = screen.index('\n}\n', start)
assert 'TerentoHelpLink(topic: helpTopic)' in screen[start:end], 'Help link outside the error dialog'
# Connect's other Help link sits in the help box, chosen by
# TroubleshootingHelp.connectHelpTopic (nil while plainly waiting or connecting).
box = screen[screen.index('private func connectHelpBox('):]
box = box[:box.index('\n    }\n')]
assert screen.count('TerentoHelpLink(topic: topic') == 1, 'Connect has more than one connection Help link'
assert 'if let topic = connectHelpTopic {' in box and 'TerentoHelpLink(topic: topic' in box, 'Connect Help link is not inside the help box'
assert 'TroubleshootingHelp.connectHelpTopic(' in screen, 'connection Help link does not use the central mapping'
assert 'support.garmin.com' not in screen, 'Connect still links the generic Garmin support page'
for removed in ['connectionHelpTopic', 'authorizationHelpTopic', 'TroubleshootingHelp.reviewTopic(',
                'TroubleshootingHelp.topic(for: operation.phase)', 'topic: .updateRemoveFailed',
                'topic: .catalogFallback', 'topic: .appUpdateRequired', 'helpTopic: .mapReadFailed']:
    assert removed not in screen, removed
sheet = (views / 'SupportReportSheet.swift').read_text()
assert 'TerentoHelpLink' not in sheet, 'Support report sheet must not show a Help link'
print('PASS: Help links appear only in the installation failure dialog, the Diagnostics send-report help and the Connect help box')
PYHELP
require "$app_source" 'openExternalURL(TroubleshootingGuide.helpMenuURL)' 'Help menu has no troubleshooting guide'

python3 - "$repo_root/Terento.xcodeproj/project.pbxproj" <<'PYPROJECT'
import json, subprocess, sys
project = json.loads(subprocess.check_output(["plutil", "-convert", "json", "-o", "-", sys.argv[1]]))
objects = project["objects"]
for suffix in ("/Errors/TroubleshootingHelp.swift", "/Views/TerentoHelpLink.swift"):
    refs = {key for key, obj in objects.items() if obj.get("path", "").endswith(suffix)}
    builds = {key for key, obj in objects.items() if obj.get("isa") == "PBXBuildFile" and obj.get("fileRef") in refs}
    targets = [obj for obj in objects.values() if obj.get("isa") == "PBXNativeTarget" and obj.get("name") == "Terento"]
    assert len(refs) == 1 and len(builds) == 1 and len(targets) == 1, suffix
    assert any(builds.intersection(objects[phase].get("files", [])) for phase in targets[0]["buildPhases"]), suffix
print("PASS: distributed Xcode target includes the troubleshooting help mapping and link")
PYPROJECT

print "PASS: troubleshooting help mapping, anchors and Help link wiring"
