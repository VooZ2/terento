#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
bridge="$project_root/Sources/LibMTPBridge/MTPBridge.c"
header="$project_root/Sources/LibMTPBridge/include/MTPBridge.h"

for function_name in \
    terento_mtp_read_existing_file_to_local \
    terento_mtp_install_map_file \
    terento_mtp_verify_managed_map_samples \
    terento_mtp_delete_managed_map \
    terento_mtp_delete_external_map; do
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

if ! grep -A100 '^int terento_mtp_delete_managed_map(' "$bridge" \
    | grep -q 'expected_size_bytes != 0 && remote_size != expected_size_bytes'; then
    print -u2 "FAIL: manual delete cannot resolve the exact stable target in its live session"
    exit 1
fi

if ! grep -A100 '^int terento_mtp_delete_external_map(' "$bridge" \
    | grep -q 'expected_size_bytes != 0 && remote_size != expected_size_bytes'; then
    print -u2 "FAIL: external delete cannot resolve the exact stable target in its live session"
    exit 1
fi

print "PASS: production map operations require a live-bound native profile"
print "PASS: production map operations do not use the lab PID lock"
print "PASS: Write Test remains locked to PID 0x51b8"
print "PASS: read-back and manual delete re-resolve session-local MTP handles"
