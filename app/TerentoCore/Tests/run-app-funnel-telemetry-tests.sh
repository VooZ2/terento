#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
repo_root="$(cd "$project_root/../.." && pwd)"
libmtp_prefix="${LIBMTP_PREFIX:-/opt/homebrew/opt/libmtp}"
libusb_prefix="${LIBUSB_PREFIX:-/opt/homebrew/opt/libusb}"
swiftpm_config_dir="${SWIFTPM_CONFIG_DIR:-/tmp/terento-native-poc-swiftpm}"
module_cache_dir="${CLANG_MODULE_CACHE_PATH:-/tmp/terento-native-poc-module-cache}"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-app-funnel-tests.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
binary_path="$build_dir/app-funnel-tests"
swiftpm_arch="$(uname -m)"
platform_build_dir="$project_root/.build/${swiftpm_arch}-apple-macosx/debug"
bridge_object="$platform_build_dir/LibMTPBridge.build/MTPBridge.c.o"
bridge_module_dir="$platform_build_dir/LibMTPBridge.build"

export LIBMTP_PREFIX="$libmtp_prefix"
export LIBUSB_PREFIX="$libusb_prefix"
export CLANG_MODULE_CACHE_PATH="$module_cache_dir"
export SWIFTPM_CONFIG_DIR="$swiftpm_config_dir"

if [[ ! -f "$bridge_object" || ! -f "$bridge_module_dir/module.modulemap" ]]; then
  print "Building TerentoPoC so funnel tests can link LibMTPBridge…"
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
  -module-name TerentoAppFunnelTests \
  -I "$bridge_module_dir" \
  -L "$libmtp_prefix/lib" -lmtp \
  -L "$libusb_prefix/lib" -lusb-1.0 \
  "$bridge_object" \
  -Xlinker -rpath -Xlinker "$libmtp_prefix/lib" \
  -module-cache-path "$module_cache_dir" \
  "${sources[@]}" \
  "$project_root/Tests/TerentoPoCTests/AppFunnelTelemetryTests.swift" \
  -o "$binary_path"

python3 - "$repo_root/Terento.xcodeproj/project.pbxproj" <<'PYPROJECT'
import json, subprocess, sys
project = json.loads(subprocess.check_output(["plutil", "-convert", "json", "-o", "-", sys.argv[1]]))
objects = project["objects"]
for suffix in ("/Telemetry/AppFunnelTelemetry.swift", "/Telemetry/TelemetryDeliveryPolicy.swift"):
    refs = {key for key, obj in objects.items() if obj.get("path", "").endswith(suffix)}
    builds = {key for key, obj in objects.items() if obj.get("isa") == "PBXBuildFile" and obj.get("fileRef") in refs}
    targets = [obj for obj in objects.values() if obj.get("isa") == "PBXNativeTarget" and obj.get("name") == "Terento"]
    assert len(refs) == 1 and len(builds) == 1 and len(targets) == 1, suffix
    assert any(builds.intersection(objects[phase].get("files", [])) for phase in targets[0]["buildPhases"]), suffix
print("PASS: distributed Xcode target includes the funnel producer and delivery policy")
PYPROJECT

# Fresh Swift-encoded payloads for the backend app-funnel contract test.
export TERENTO_APP_FUNNEL_EVENT_FIXTURES="${TERENTO_APP_FUNNEL_EVENT_FIXTURES:-$build_dir/native-app-funnel-events.json}"
python3 - "$binary_path" <<'PYTEST'
import subprocess, sys
subprocess.run([sys.argv[1]], check=True, timeout=60)
PYTEST

source "$repo_root/Tests/backend-python-runtime.sh"
"$TERENTO_PYTHON_BIN" - "$TERENTO_APP_FUNNEL_EVENT_FIXTURES" "$repo_root/contracts/app-funnel-event.schema.json" <<'PYCHECK'
import json, pathlib, re, sys, uuid
from datetime import datetime

events = json.loads(pathlib.Path(sys.argv[1]).read_text())
outcomes = {
    "DEVICE_CONNECT": {"CONNECTED", "TIMEOUT_NO_USB", "TIMEOUT_USB_PRESENT", "BUSY", "MULTIPLE_DEVICES",
                       "NOT_MTP_MODE", "DISCONNECTED", "FAILED"},
    "AUTHORIZATION": {"APPROVED", "PENDING", "OUT_OF_SCOPE", "UNKNOWN_MODEL", "AMBIGUOUS",
                      "CATALOG_UNAVAILABLE", "UPDATE_REQUIRED"},
    "CATALOG": {"REMOTE", "REMOTE_PARTIAL", "BUNDLED_FALLBACK", "UPDATE_REQUIRED"},
    "INSTALL_BLOCKED": {"AUTHORIZATION", "DEVICE_STORAGE", "MAC_STORAGE", "CATALOG_UNVERIFIED",
                        "LOCAL_CAPABILITY", "OTHER"},
}
allowed = {"schemaVersion", "id", "sessionId", "occurredAt", "appBuild", "releaseLabel", "stage", "outcome",
           "baseModel", "droppedPackageCount"}
semver = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$")
seen = set()
for event in events:
    assert set(event) <= allowed, set(event) - allowed
    assert event["schemaVersion"] == 1 and not isinstance(event["schemaVersion"], bool)
    uuid.UUID(event["id"]); uuid.UUID(event["sessionId"])
    assert event["occurredAt"].endswith("Z") and datetime.fromisoformat(event["occurredAt"].replace("Z", "+00:00"))
    assert isinstance(event["appBuild"], str) and 0 < len(event["appBuild"]) <= 80
    assert semver.match(event["releaseLabel"]) and event["releaseLabel"].endswith("-local")
    assert event["outcome"] in outcomes[event["stage"]], event
    if "baseModel" in event:
        assert event["stage"] == "AUTHORIZATION" or (event["stage"], event["outcome"]) == ("DEVICE_CONNECT", "CONNECTED")
        assert isinstance(event["baseModel"], str) and 0 < len(event["baseModel"]) <= 80
    if "droppedPackageCount" in event:
        assert (event["stage"], event["outcome"]) == ("CATALOG", "REMOTE_PARTIAL")
        assert isinstance(event["droppedPackageCount"], int) and event["droppedPackageCount"] >= 0
    assert len(json.dumps(event).encode()) <= 4096
    seen.add((event["stage"], event["outcome"]))
assert seen == {(stage, outcome) for stage, values in outcomes.items() for outcome in values}, "fixtures cover every outcome"
schema_path = pathlib.Path(sys.argv[2])
if schema_path.exists():
    import jsonschema
    schema = json.loads(schema_path.read_text())
    for event in events:
        jsonschema.validate(event, schema)
    print("PASS: Swift funnel payloads validate against contracts/app-funnel-event.schema.json")
print(f"PASS: {len(events)} fresh Swift funnel payloads satisfy the shared schema-v1 rules")
PYCHECK

print "PASS: app funnel producer, durable queue and Swift-encoded payload tests"
