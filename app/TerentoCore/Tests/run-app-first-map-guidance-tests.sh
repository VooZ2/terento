#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
repo_root="$(cd "$project_root/../.." && pwd)"
libmtp_prefix="${LIBMTP_PREFIX:-/opt/homebrew/opt/libmtp}"
libusb_prefix="${LIBUSB_PREFIX:-/opt/homebrew/opt/libusb}"
swiftpm_config_dir="${SWIFTPM_CONFIG_DIR:-/tmp/terento-native-poc-swiftpm}"
module_cache_dir="${CLANG_MODULE_CACHE_PATH:-/tmp/terento-native-poc-module-cache}"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-first-map-guidance-tests.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
binary_path="$build_dir/first-map-guidance-tests"
swiftpm_arch="$(uname -m)"
platform_build_dir="$project_root/.build/${swiftpm_arch}-apple-macosx/debug"
bridge_object="$platform_build_dir/LibMTPBridge.build/MTPBridge.c.o"
bridge_module_dir="$platform_build_dir/LibMTPBridge.build"

export LIBMTP_PREFIX="$libmtp_prefix"
export LIBUSB_PREFIX="$libusb_prefix"
export CLANG_MODULE_CACHE_PATH="$module_cache_dir"
export SWIFTPM_CONFIG_DIR="$swiftpm_config_dir"

if [[ ! -f "$bridge_object" || ! -f "$bridge_module_dir/module.modulemap" ]]; then
  print "Building TerentoPoC so first-map guidance tests can link LibMTPBridge…"
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
  -module-name TerentoFirstMapGuidanceTests \
  -I "$bridge_module_dir" \
  -L "$libmtp_prefix/lib" -lmtp \
  -L "$libusb_prefix/lib" -lusb-1.0 \
  "$bridge_object" \
  -Xlinker -rpath -Xlinker "$libmtp_prefix/lib" \
  -module-cache-path "$module_cache_dir" \
  "${sources[@]}" \
  "$project_root/Tests/TerentoPoCTests/FirstMapGuidanceTests.swift" \
  -o "$binary_path"

"$binary_path"


connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"
map_engine="$project_root/Sources/TerentoPoC/MapCatalog/MapEngine.swift"

require() {
    local file="$1" text="$2" message="$3"
    if ! grep -Fq -- "$text" "$file"; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}

require "$connect_screen" 'highlightsRecommendation: isFirstMapSelection,' 'first map selection does not highlight the recommendation'
require "$connect_screen" 'badge: showsRecommendation' 'recommendation has no text and icon badge'
require "$connect_screen" '(FirstMapGuidance.recommendedLabel, "star.fill")' 'recommendation badge has no icon'
require "$connect_screen" 'downloadEstimate: FirstMapGuidance.downloadEstimateText(' 'install selection rows do not show the download estimate'
if grep -Fq 'downloadEstimate: isFirstMapSelection' "$connect_screen"; then
    print -u2 "FAIL: the download size and time estimate must show on every install selection"
    exit 1
fi
require "$connect_screen" 'bytes: item.package.expectedDownloadSizeBytes,' 'download estimate does not use the catalog download size'
require "$connect_screen" 'recentBytesPerSecond: mapEngine.recentDownloadBytesPerSecond)' 'download estimate does not use the measured speed'
require "$connect_screen" 'if isFirstMapSelection, !plan.selectedItems.isEmpty {' 'keep-connected line is not shown for a first selection'
require "$map_engine" 'downloadSpeedHistory.record(bytesPerSecond: progress.bytesPerSecond,' 'measured download speed is not recorded'
# The recommendation highlights and sorts only; it never selects a map.
if [[ $(grep -c 'isRecommended' "$connect_screen") -ne 1 ]]; then
    print -u2 "FAIL: the Install maps screen must use isRecommended only for the highlight"
    exit 1
fi

python3 - "$repo_root/Terento.xcodeproj/project.pbxproj" <<'PYPROJECT'
import json, subprocess, sys
project = json.loads(subprocess.check_output(["plutil", "-convert", "json", "-o", "-", sys.argv[1]]))
objects = project["objects"]
for suffix in ("/MapCatalog/FirstMapGuidance.swift",):
    refs = {key for key, obj in objects.items() if obj.get("path", "").endswith(suffix)}
    builds = {key for key, obj in objects.items() if obj.get("isa") == "PBXBuildFile" and obj.get("fileRef") in refs}
    targets = [obj for obj in objects.values() if obj.get("isa") == "PBXNativeTarget" and obj.get("name") == "Terento"]
    assert len(refs) == 1 and len(builds) == 1 and len(targets) == 1, suffix
    assert any(builds.intersection(objects[phase].get("files", [])) for phase in targets[0]["buildPhases"]), suffix
print("PASS: distributed Xcode target includes the first-map guidance")
PYPROJECT

print "PASS: first-map recommendation and keep-connected wiring; download estimate on every install selection"
