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
require "$help_link" 'Label("Help", systemImage: "questionmark.circle")' 'Help has no text and icon'
if grep -Fq 'PrimaryButton' "$help_link" || grep -Fq '.background(' "$help_link"; then
    print -u2 "FAIL: Help link must not be a second primary button"
    exit 1
fi
# No other file maps errors to guide URLs.
if grep -rn 'guides/troubleshooting' "$project_root/Sources/TerentoPoC" | grep -v 'Errors/TroubleshootingHelp.swift' | grep -q .; then
    print -u2 "FAIL: troubleshooting URLs must come only from TroubleshootingHelp.swift"
    exit 1
fi

require "$connect_screen" 'TerentoHelpLink(topic: topic)
                            .padding(.top, 8)' 'Connect page does not show Help for connection states'
require "$connect_screen" 'TroubleshootingHelp.topic(detectionPhase: deviceEngine.detectionPhase)' 'connect help is not derived from the detection phase'
require "$connect_screen" 'deviceEngine.lastConnectOutcome.flatMap(TroubleshootingHelp.topic(for:))' 'failed connection help is not derived from the connect outcome'
require "$connect_screen" 'authorizationHelpTopic: TroubleshootingHelp.topic(for: deviceEngine.installationAuthorization)' 'Device verdict has no Help link'
require "$connect_screen" 'TerentoHelpLink(topic: .catalogFallback, size: 12)' 'local catalog notice has no Help link'
require "$connect_screen" 'TerentoHelpLink(topic: .appUpdateRequired, size: 12)' 'update-required catalog notice has no Help link'
require "$connect_screen" 'helpTopic: .mapReadFailed' 'map read failure has no Help link'
require "$connect_screen" 'TroubleshootingHelp.reviewTopic(' 'blocked review step has no Help link'
require "$connect_screen" 'helpTopic: installationFailureHelpTopic' 'installation failure dialog has no Help link'
require "$connect_screen" 'TroubleshootingHelp.topic(for: operation.phase)' 'Update/Remove progress has no Help link'
require "$connect_screen" 'TerentoHelpLink(topic: .updateRemoveFailed, size: 12)' 'failed Update/Remove has no Help link'
require "$diagnostics" 'TerentoHelpLink(topic: .sendReport)' 'Diagnostics failure report has no Help link'
require "$app_source" 'openExternalURL(TroubleshootingGuide.guideURL)' 'Help menu has no troubleshooting guide'

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
