#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
bridge="$project_root/Sources/LibMTPBridge/MTPBridge.c"
header="$project_root/Sources/LibMTPBridge/include/MTPBridge.h"

for function_name in \
    terento_mtp_read_existing_file_to_local \
    terento_mtp_install_map_file_authorized \
    terento_mtp_verify_managed_map_samples \
    terento_mtp_delete_managed_map_authorized \
    terento_mtp_delete_external_map_authorized; do
    if ! grep -A3 "^int ${function_name}(" "$header" | grep -q 'TerentoMTPMapOperationProfile'; then
        print -u2 "FAIL: $function_name does not require the native operation profile"
        exit 1
    fi
done

first_lab_write_line="$(grep -n '^int terento_mtp_write_test_file(' "$bridge" | cut -d: -f1)"
while IFS=: read -r line _; do
    if (( line < first_lab_write_line )); then
        print -u2 "FAIL: production map code still calls validate_write_test_device"
        exit 1
    fi
done < <(grep -n 'validate_write_test_device(' "$bridge" | tail -n +2)

live_match_calls="$(grep -c 'validate_live_map_operation_device(' "$bridge")"
if (( live_match_calls < 5 )); then
    print -u2 "FAIL: production map operations are not all bound to live device facts"
    exit 1
fi

if ! grep -q 'TERENTO_WRITE_TEST_PRODUCT_ID 0x51b8' "$bridge"; then
    print -u2 "FAIL: lab Write Test is no longer locked to PID 0x51b8"
    exit 1
fi

if ! grep -q 'find_existing_file_by_stable_identity(' "$bridge" \
    || grep -A70 '^static int find_existing_file_by_stable_identity(' "$bridge" \
        | grep -q 'file->item_id != expected_item_id'; then
    print -u2 "FAIL: native read-back still carries an MTP handle across sessions"
    exit 1
fi

# Static integration checks complement the executable native authorization tests.
# Inspect complete function bodies: line-window greps hid checks as code grew.
python3 - "$bridge" "$header" <<'PYPROFILE'
from pathlib import Path
import re, sys
source, header = [Path(p).read_text() for p in sys.argv[1:]]
def body(name):
    match = re.search(r"(?:static )?int " + re.escape(name) + r"\s*\([^;{}]*\)\s*\{", source)
    assert match, name
    start = source.index('{', match.start())
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]
for base in ['terento_mtp_install_map_file', 'terento_mtp_delete_managed_map', 'terento_mtp_delete_external_map']:
    legacy = body(base)
    assert 'return TERENTO_MTP_MUTATION_REFUSED;' in legacy, base
    assert not re.search(r'LIBMTP_|open_single_garmin_device|terento_dispatch_mutation', legacy), base
    live = body(base + '_authorized')
    assert 'validate_live_map_operation_device(' in live, base
    assert '!authorization || !record' in live, base
    assert re.search(re.escape(base + '_authorized') + r'\s*\([^;]*TerentoMTPMutationAuthorization[^;]*TerentoMTPMutationRecord', header, re.S), base
for base in ['terento_mtp_delete_managed_map', 'terento_mtp_delete_external_map']:
    live = body(base + '_authorized')
    for check in ['remote_size != expected_size_bytes', 'expected_size_bytes == 0',
                  'storage_id != profile->expected_storage_id', 'match_count != 1',
                  'verify_deletion_content(', 'deletion_target_still_matches(',
                  'terento_dispatch_mutation(']:
        assert check in live, (base, check)
    assert live.index('verify_deletion_content(') < live.index('deletion_target_still_matches(') < live.index('terento_dispatch_mutation('), base
    assert 'actual_item_id != expected_item_id' not in live, base
assert '#define TERENTO_MAP_OPERATION_PROFILE_VERSION 2' in source
for field in ['physical_identifier_source', 'physical_identifier', 'expected_storage_id']:
    assert field in header and field in body('validate_map_operation_profile'), field
physical = body('physical_identifier_matches')
assert 'LIBMTP_Get_Serialnumber' in physical and 'read_garmin_device_xml' in physical
assert 'physical_identifier_matches(profile, device)' in body('validate_live_map_operation_device')
print('PASS: legacy mutation entrypoints refuse; authorized operations enforce physical binding, live storage, content and final identity checks')
PYPROFILE

if grep -A5 '^        \*matched_samples += 1;' "$bridge" \
    | grep -q 'LIBMTP_Release_Device(device)'; then
    print -u2 "FAIL: sampled Install verification still closes MTP between every sample region"
    exit 1
fi

if ! grep -A6 '^        \*matched_samples += 1;' "$bridge" \
    | grep -q 'Healthy reads retain one session across every sample'; then
    print -u2 "FAIL: sampled Install verification does not document its low-churn session boundary"
    exit 1
fi

print "PASS: production map operations require a live-bound native profile"
print "PASS: production map operations do not use the lab PID lock"
print "PASS: Write Test remains locked to PID 0x51b8"
print "PASS: read-back and authorized delete re-resolve session-local MTP handles; delete requires same-session content proof"
print "PASS: sampled Install verification reuses one read-only MTP session"

# Execute the actual C filename guard without loading libmtp or touching USB.
# Existing Swift lifecycle fakes cannot catch a stricter native boundary.
python3 - "$bridge" <<'PYTEST'
import pathlib, subprocess, sys, tempfile
source = pathlib.Path(sys.argv[1]).read_text()
start = source.index("static int validate_stage42_target(")
end = source.index("static int validate_external_map_target(", start)
function = source[start:end]
program = r"""
#include <assert.h>
#include <ctype.h>
#include <stddef.h>
#include <string.h>
static void set_error(char *message, size_t capacity, const char *detail) {
    (void)message; (void)capacity; (void)detail;
}
""" + function + r"""
int main(void) {
    const char *valid[] = {
        "terento_freizeitkarte_ltu.img",
        "terento_opentopomap_ltu_contours.img",
        "terento_freizeitkarte_ltu_2026-09.img",
        "terento_maprando_lituanie_2026-09-02.img",
        "terento_maprando_lituanie_2028-02-29.img"
    };
    const char *invalid[] = {
        "terento_maprando_lituanie_2026-02-29.img",
        "terento_maprando_lituanie_2026-13-01.img",
        "terento_maprando_lituanie_2026-09-00.img",
        "terento_maprando_lituanie_2026-09-02_extra.img",
        "terento_maprando_lituanie_2026-09-02.img.extra",
        "terento_map-rando_lituanie_2026-09-02.img",
        "terento_maprando_lituanie_2026-9-2.img",
        "terento_maprando_lituanie_2026-09--02.img",
        "terento_2026-09-02.img",
        "../terento_maprando_lituanie_2026-09-02.img",
        "terento_maprando/../lituanie.img", "gmappmap.img"
    };
    for (size_t i = 0; i < sizeof(valid) / sizeof(valid[0]); i++)
        assert(validate_stage42_target(valid[i], NULL, 0) == 0);
    for (size_t i = 0; i < sizeof(invalid) / sizeof(invalid[0]); i++)
        assert(validate_stage42_target(invalid[i], NULL, 0) != 0);
    assert(validate_stage42_target(NULL, NULL, 0) != 0);
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="terento-native-target-") as directory:
    c = pathlib.Path(directory) / "target.c"
    binary = pathlib.Path(directory) / "target"
    c.write_text(program)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(c), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print("PASS: native managed targets accept exact monthly/daily update suffixes and reject invalid dates/paths")
PYTEST

# Exercise the exact production coverage planner without libmtp or USB.
coverage_build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-sample-coverage.XXXXXX")"
trap 'rm -rf "$coverage_build_dir"' EXIT
cc -std=c11 -Wall -Wextra -Werror \
    -I "$project_root/Sources/LibMTPBridge" \
    "$project_root/Tests/TerentoPoCTests/SampleCoverageTests.c" \
    -o "$coverage_build_dir/coverage"
"$coverage_build_dir/coverage"

# Check the pinned native diagnostic patch without compiling or opening USB.
python3 - "$project_root/../../Packaging/NativeDependencies/patch-partial-read-diagnostics.pl" <<'PYPATCH'
import pathlib, subprocess, sys, tempfile
patch = sys.argv[1]
source = '''    ret = ptp_android_getpartialobject64(params, id, offset, maxbytes, data, size);
  }
  if (ret == PTP_RC_OK)
      return 0;
  return -1;
'''
with tempfile.TemporaryDirectory(prefix="terento-ptp-patch-") as directory:
    path = pathlib.Path(directory) / "libmtp.c"
    path.write_text("/* before */\n" + source + "/* after */\n")
    subprocess.run(["/usr/bin/perl", patch, str(path)], check=True)
    expected = path.read_text()
    assert expected == ("/* before */\n" + source.replace(
        "  return -1;", '  add_ptp_error_to_errorstack(device, ret, "Terento partial read response");\n  return -1;') + "/* after */\n")
    subprocess.run(["/usr/bin/perl", patch, str(path)], check=True)
    assert path.read_text() == expected
    for invalid in (source + source, source.replace("maxbytes, data, size", "other, data, size")):
        path.write_text(invalid)
        result = subprocess.run(["/usr/bin/perl", patch, str(path)], capture_output=True)
        assert result.returncode != 0 and path.read_text() == invalid
print("PASS: PTP diagnostics patch changes only failed response, is idempotent and rejects source drift")
PYPATCH

# Exercise the pinned session patch and generated cleanup against fake USB.
python3 "$project_root/Tests/TerentoPoCTests/USBLifecyclePatchTests.py" \
    "$project_root/../../Packaging/NativeDependencies/patch-usb-session-lifecycle.pl"

python3 "$project_root/Tests/TerentoPoCTests/USBRecoveryPatchTests.py" \
    "$project_root/../../Packaging/NativeDependencies/patch-usb-recovery.py"

python3 "$project_root/Tests/TerentoPoCTests/USBDeviceReferenceTests.py" \
    "$project_root/../../Packaging/NativeDependencies/patch-usb-device-references.py"
