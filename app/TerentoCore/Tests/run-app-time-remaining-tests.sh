#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
repo_root="$(cd "$project_root/../.." && pwd)"
libmtp_prefix="${LIBMTP_PREFIX:-/opt/homebrew/opt/libmtp}"
libusb_prefix="${LIBUSB_PREFIX:-/opt/homebrew/opt/libusb}"
swiftpm_config_dir="${SWIFTPM_CONFIG_DIR:-/tmp/terento-native-poc-swiftpm}"
module_cache_dir="${CLANG_MODULE_CACHE_PATH:-/tmp/terento-native-poc-module-cache}"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-time-remaining-tests.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
binary_path="$build_dir/time-remaining-tests"
swiftpm_arch="$(uname -m)"
platform_build_dir="$project_root/.build/${swiftpm_arch}-apple-macosx/debug"
bridge_object="$platform_build_dir/LibMTPBridge.build/MTPBridge.c.o"
bridge_module_dir="$platform_build_dir/LibMTPBridge.build"

export LIBMTP_PREFIX="$libmtp_prefix"
export LIBUSB_PREFIX="$libusb_prefix"
export CLANG_MODULE_CACHE_PATH="$module_cache_dir"
export SWIFTPM_CONFIG_DIR="$swiftpm_config_dir"

if [[ ! -f "$bridge_object" || ! -f "$bridge_module_dir/module.modulemap" ]]; then
  print "Building TerentoPoC so time-remaining tests can link LibMTPBridge…"
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
  -module-name TerentoTimeRemainingTests \
  -I "$bridge_module_dir" \
  -L "$libmtp_prefix/lib" -lmtp \
  -L "$libusb_prefix/lib" -lusb-1.0 \
  "$bridge_object" \
  -Xlinker -rpath -Xlinker "$libmtp_prefix/lib" \
  -module-cache-path "$module_cache_dir" \
  "${sources[@]}" \
  "$project_root/Tests/TerentoPoCTests/RemainingTimeEstimatorTests.swift" \
  -o "$binary_path"

"$binary_path"

connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"
map_engine="$project_root/Sources/TerentoPoC/MapCatalog/MapEngine.swift"
lifecycle="$project_root/Sources/TerentoPoC/Installation/MapLifecycleViewModel.swift"
label="$project_root/Sources/TerentoPoC/Views/TimeRemainingLabel.swift"

require() {
    local file="$1" text="$2" message="$3"
    if ! grep -Fq -- "$text" "$file"; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}

require "$map_engine" 'downloadTimeEstimator.update(completed: Double(progress.bytesDownloaded)' 'download estimate is not fed by measured download bytes'
require "$map_engine" 'installTimeEstimator.update(completed: Double(progress.bytesTransferred)' 'write estimate is not fed by measured write bytes'
require "$map_engine" 'finishingTimeEstimator.update(' 'read-back estimate is not fed by measured read-back bytes'
require "$map_engine" 'if phase != installationPhase { resetTimeRemaining() }' 'a phase change does not reset the estimate'
require "$lifecycle" 'LifecycleRemainingTimeUnits.units(action: action, phase: phase, progress: progress)' 'Update/Remove estimates are not limited to measured units'
require "$connect_screen" 'timeRemaining: mapEngine.downloadTimeRemaining' 'Downloading has no time estimate'
require "$connect_screen" 'timeRemaining: mapEngine.installTimeRemaining' 'Installing has no time estimate'
require "$connect_screen" 'timeRemaining: mapEngine.finishingTimeRemaining' 'Finishing has no time estimate'
require "$connect_screen" 'if state == .active, let timeRemaining {' 'time estimate is not limited to the active step'
require "$connect_screen" 'timeRemaining: lifecycleViewModel.timeRemaining(for: item.id)' 'Manage maps has no time estimate'
require "$label" 'Label(text, systemImage: "clock")' 'time estimate has no text and icon'
if grep -A3 'title: "Preparing",' "$connect_screen" | grep -Fq 'timeRemaining'; then
    print -u2 "FAIL: Preparing checkpoints must not show a time estimate"
    exit 1
fi

python3 - "$repo_root/Terento.xcodeproj/project.pbxproj" <<'PYPROJECT'
import json, subprocess, sys
project = json.loads(subprocess.check_output(["plutil", "-convert", "json", "-o", "-", sys.argv[1]]))
objects = project["objects"]
for suffix in ("/Installation/RemainingTimeEstimator.swift", "/Views/TimeRemainingLabel.swift"):
    refs = {key for key, obj in objects.items() if obj.get("path", "").endswith(suffix)}
    builds = {key for key, obj in objects.items() if obj.get("isa") == "PBXBuildFile" and obj.get("fileRef") in refs}
    targets = [obj for obj in objects.values() if obj.get("isa") == "PBXNativeTarget" and obj.get("name") == "Terento"]
    assert len(refs) == 1 and len(builds) == 1 and len(targets) == 1, suffix
    assert any(builds.intersection(objects[phase].get("files", [])) for phase in targets[0]["buildPhases"]), suffix
print("PASS: distributed Xcode target includes the time-remaining estimator and label")
PYPROJECT

print "PASS: measured time-remaining estimates and their progress wiring"
