#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
libmtp_prefix="${LIBMTP_PREFIX:-/opt/homebrew/opt/libmtp}"
libusb_prefix="${LIBUSB_PREFIX:-/opt/homebrew/opt/libusb}"
swiftpm_config_dir="${SWIFTPM_CONFIG_DIR:-/tmp/terento-native-poc-swiftpm}"
module_cache_dir="${CLANG_MODULE_CACHE_PATH:-/tmp/terento-native-poc-module-cache}"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-installation-operation-diagnostics-tests.XXXXXX")"
binary_path="$build_dir/installation-operation-diagnostics-tests"
swiftpm_arch="$(uname -m)"
platform_build_dir="$project_root/.build/${swiftpm_arch}-apple-macosx/debug"
bridge_object="$platform_build_dir/LibMTPBridge.build/MTPBridge.c.o"
bridge_module_dir="$platform_build_dir/LibMTPBridge.build"

export LIBMTP_PREFIX="$libmtp_prefix"
export LIBUSB_PREFIX="$libusb_prefix"
export CLANG_MODULE_CACHE_PATH="$module_cache_dir"
export SWIFTPM_CONFIG_DIR="$swiftpm_config_dir"

if [[ ! -f "$bridge_object" || ! -f "$bridge_module_dir/module.modulemap" ]]; then
  print "Building TerentoPoC so ViewModel tests can link LibMTPBridge…"
  # These harnesses link the native SwiftPM object/module layout explicitly.
  swift build --build-system native --package-path "$project_root" --product TerentoPoC
fi

sources=()
while IFS= read -r source_file; do
  sources+=("$source_file")
done < <(
  find "$project_root/Sources/TerentoPoC" -name '*.swift' \
    ! -name 'TerentoPoCApp.swift' \
    ! -name 'ConnectScreen.swift' \
    ! -name 'ContentView.swift' \
    -print | sort
)

swiftc -D TERENTO_TESTING \
  -parse-as-library \
  -module-name TerentoInstallationOperationDiagnosticsTests \
  -I "$bridge_module_dir" \
  -L "$libmtp_prefix/lib" \
  -lmtp \
  -L "$libusb_prefix/lib" \
  -lusb-1.0 \
  "$bridge_object" \
  -Xlinker -rpath \
  -Xlinker "$libmtp_prefix/lib" \
  -module-cache-path "$module_cache_dir" \
  "${sources[@]}" \
  "$project_root/Tests/TerentoPoCTests/InstallationOperationDiagnosticsTests.swift" \
  -o "$binary_path"

python3 - "$project_root/../../Terento.xcodeproj/project.pbxproj" <<'PYPROJECT'
import json, subprocess, sys
project = json.loads(subprocess.check_output(["plutil", "-convert", "json", "-o", "-", sys.argv[1]]))
objects = project["objects"]
refs = {key for key, obj in objects.items() if obj.get("path", "").endswith("/InstallationOperationDiagnostics.swift")}
builds = {key for key, obj in objects.items() if obj.get("isa") == "PBXBuildFile" and obj.get("fileRef") in refs}
targets = [obj for obj in objects.values() if obj.get("isa") == "PBXNativeTarget" and obj.get("name") == "Terento"]
assert len(refs) == 1 and len(builds) == 1 and len(targets) == 1
assert any(builds.intersection(objects[phase].get("files", [])) for phase in targets[0]["buildPhases"])
print("PASS: distributed Xcode target includes the operation diagnostic producer")
PYPROJECT

export TERENTO_DIAGNOSTIC_FIXTURE_OUTPUT="$build_dir/native-events.json"
python3 - "$binary_path" <<'PYTEST'
import subprocess, sys
subprocess.run([sys.argv[1]], check=True, timeout=30)
PYTEST

"$project_root/../../Tests/run-backend-operation-diagnostic-contract-tests.sh"

print "PASS: operation diagnostic behavior and actual Swift-to-API payload tests"
