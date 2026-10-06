#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
repo_root="$(cd "$project_root/../.." && pwd)"
libmtp_prefix="${LIBMTP_PREFIX:-/opt/homebrew/opt/libmtp}"
libusb_prefix="${LIBUSB_PREFIX:-/opt/homebrew/opt/libusb}"
swiftpm_config_dir="${SWIFTPM_CONFIG_DIR:-/tmp/terento-native-poc-swiftpm}"
module_cache_dir="${CLANG_MODULE_CACHE_PATH:-/tmp/terento-native-poc-module-cache}"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-support-report-tests.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
binary_path="$build_dir/support-report-tests"
swiftpm_arch="$(uname -m)"
platform_build_dir="$project_root/.build/${swiftpm_arch}-apple-macosx/debug"
bridge_object="$platform_build_dir/LibMTPBridge.build/MTPBridge.c.o"
bridge_module_dir="$platform_build_dir/LibMTPBridge.build"

export LIBMTP_PREFIX="$libmtp_prefix"
export LIBUSB_PREFIX="$libusb_prefix"
export CLANG_MODULE_CACHE_PATH="$module_cache_dir"
export SWIFTPM_CONFIG_DIR="$swiftpm_config_dir"

if [[ ! -f "$bridge_object" || ! -f "$bridge_module_dir/module.modulemap" ]]; then
  print "Building TerentoPoC so support report tests can link LibMTPBridge…"
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
  -module-name TerentoSupportReportTests \
  -I "$bridge_module_dir" \
  -L "$libmtp_prefix/lib" -lmtp \
  -L "$libusb_prefix/lib" -lusb-1.0 \
  "$bridge_object" \
  -Xlinker -rpath -Xlinker "$libmtp_prefix/lib" \
  -module-cache-path "$module_cache_dir" \
  "${sources[@]}" \
  "$project_root/Tests/TerentoPoCTests/SupportReportTests.swift" \
  -o "$binary_path"

export TERENTO_SUPPORT_REPORT_PAYLOADS="$build_dir/support-report-payloads.json"
(
  cd "$project_root"
  "$binary_path"
)


source "$repo_root/Tests/backend-python-runtime.sh"
"$TERENTO_PYTHON_BIN" - "$TERENTO_SUPPORT_REPORT_PAYLOADS" "$repo_root/contracts/support-report.schema.json" "$repo_root/contracts/fixtures" <<'PYCHECK'
import json, pathlib, sys
from jsonschema import Draft202012Validator
payloads = json.loads(pathlib.Path(sys.argv[1]).read_text())
validator = Draft202012Validator(json.loads(pathlib.Path(sys.argv[2]).read_text()))
fixtures = pathlib.Path(sys.argv[3])
for payload in payloads:
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    assert not errors, [f"{list(e.path)}: {e.message}" for e in errors]
    assert len(json.dumps(payload).encode()) <= 64 * 1024
    assert "Unavailable" not in json.dumps(payload)
for name in ("support-report.valid", "support-report.valid-minimal", "support-report.valid-local-update"):
    validator.validate(json.loads((fixtures / f"{name}.json").read_text()))
for name in ("support-report.invalid-disallowed-field", "support-report.invalid-local-path"):
    assert list(validator.iter_errors(json.loads((fixtures / f"{name}.json").read_text()))), name
print(f"PASS: {len(payloads)} Swift-encoded support reports validate against contracts/support-report.schema.json")
PYCHECK

connect_screen="$project_root/Sources/TerentoPoC/Views/ConnectScreen.swift"
diagnostics="$project_root/Sources/TerentoPoC/Views/DiagnosticsView.swift"
app_source="$project_root/Sources/TerentoPoC/TerentoPoCApp.swift"
sheet="$project_root/Sources/TerentoPoC/Views/SupportReportSheet.swift"
log="$project_root/Sources/TerentoPoC/Diagnostics/TerentoDiagnosticLog.swift"

require() {
    local file="$1" text="$2" message="$3"
    if ! grep -Fq -- "$text" "$file"; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}

require "$connect_screen" 'onSendSupportReport: { sendInstallationSupportReport(for: selectedInstallationPlan) }' 'failure dialog has no Send report to Terento'
require "$connect_screen" 'secondaryLabel: "Report issue"' 'the GitHub option must stay in the failure dialog'
require "$connect_screen" 'Label("Send report to Terento", systemImage: "paperplane")' 'Send report to Terento is not a text link with an icon'
require "$diagnostics" 'openWindow(id: "support-report")' 'Diagnostics has no Send report to Terento'
require "$diagnostics" 'DiagnosticsActionButton(title: "Report latest failure")' 'Diagnostics lost the GitHub report option'
require "$app_source" 'Button("Send Report to Terento…")' 'Help menu has no Send report to Terento'
require "$app_source" 'Window("Send Report to Terento", id: "support-report")' 'support report window is missing'
require "$app_source" 'Button("Report an Issue")' 'Help menu lost the GitHub option'
require "$sheet" 'Text(controller.payload.previewText)' 'the sheet does not show exactly what will be sent'
require "$sheet" 'Text("Don'"'"'t include personal information.")' 'the description has no personal-information hint'
require "$sheet" 'Label("Report \(reference) sent", systemImage: "checkmark.circle.fill")' 'the sent reference is not shown with text and icon'
require "$sheet" 'controller.isFailed ? "Try again" : "Send"' 'a failed send offers no Try again'
require "$log" 'failureSupportReportURL' 'saved failures do not keep their structured fields'

python3 - "$repo_root/Terento.xcodeproj/project.pbxproj" <<'PYPROJECT'
import json, subprocess, sys
project = json.loads(subprocess.check_output(["plutil", "-convert", "json", "-o", "-", sys.argv[1]]))
objects = project["objects"]
for suffix in ("/Diagnostics/SupportReport.swift", "/Diagnostics/SupportReportSender.swift", "/Views/SupportReportSheet.swift"):
    refs = {key for key, obj in objects.items() if obj.get("path", "").endswith(suffix)}
    builds = {key for key, obj in objects.items() if obj.get("isa") == "PBXBuildFile" and obj.get("fileRef") in refs}
    targets = [obj for obj in objects.values() if obj.get("isa") == "PBXNativeTarget" and obj.get("name") == "Terento"]
    assert len(refs) == 1 and len(builds) == 1 and len(targets) == 1, suffix
    assert any(builds.intersection(objects[phase].get("files", [])) for phase in targets[0]["buildPhases"]), suffix
print("PASS: distributed Xcode target includes the support report client")
PYPROJECT

print "PASS: support report client, schema conformance and entry points"
