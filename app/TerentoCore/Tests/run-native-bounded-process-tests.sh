#!/bin/zsh
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
build="$(mktemp -d "${TMPDIR:-/tmp}/terento-finishing-trace-tests.XXXXXX")"
trap 'rm -rf "$build"' EXIT
cat > "$build/native.c" <<'C'
#include "FinishingTrace.h"
int main(void) {
    TerentoFinishingTrace trace = terento_trace_start();
    terento_trace_event(&trace, "verify_begin", 0, 0, 7);
    terento_trace_verified(&trace, 65536, 65536);
    for (int i = 0; i < 100; i++) terento_trace_verified(&trace, 131072, 131072);
    TerentoReadTiming timing = {0};
    terento_read_timing_add(&timing, 0.020, 0.001, 65536, 65535);
    terento_read_timing_add(&timing, 0.500, 0.002, 131071, 65535);
    terento_read_timing_add(&timing, 0.030, 0.001, 196606, 65535);
    terento_trace_read_timing(&trace, "region_timing", 2, &timing);
    terento_trace_read_timing(&trace, "read_timing", -1, &timing);
    terento_trace_event(&trace, "read_failed", 131072, -1, 0);
    terento_trace_finish(&trace);
    return 0;
}
C
for mode in debug release; do
    flags=()
    [[ "$mode" == debug ]] && flags=(-DDEBUG=1)
    cc "${flags[@]}" -I "$project_root/Sources/LibMTPBridge" "$build/native.c" -o "$build/native-$mode"
    TERENTO_FINISHING_TRACE=1 "$build/native-$mode" 2> "$build/native-$mode.log"
done
TERENTO_FINISHING_TRACE_FILE="$build/public.trace" "$build/native-release" 2> "$build/public-stderr.log"
[[ ! -s "$build/public-stderr.log" ]]
grep -q "event=read_failed.*last_verified_end=131072 verified_bytes=131072" "$build/public.trace"
# Chunk timing: three chunks, the slowest at its own offset, watch and local time apart.
grep -q "event=region_timing region=2 chunks=3 bytes=196605 total_ms=550 slowest_ms=500 slowest_offset=131071 local_ms=4 mbps=0.36$" "$build/public.trace"
grep -q "event=read_timing chunks=3 bytes=196605 total_ms=550 slowest_ms=500 slowest_offset=131071 local_ms=4 mbps=0.36$" "$build/public.trace"
if grep -q "event=read_timing region=" "$build/public.trace"; then exit 1; fi
TERENTO_FINISHING_TRACE=0 "$build/native-debug" 2> "$build/off.log"
[[ ! -s "$build/native-release.log" && ! -s "$build/off.log" ]]
[[ "$(grep -c 'event=read_checkpoint' "$build/native-debug.log")" == 1 ]]
grep -q 'event=read_failed.*last_verified_end=131072 verified_bytes=131072' "$build/native-debug.log"
for mode in debug release; do
    flags=()
    [[ "$mode" == debug ]] && flags=(-D DEBUG)
    swiftc "${flags[@]}" "$project_root/Sources/TerentoPoC/MTPTransport/BoundedNativeProcess.swift" \
      "$project_root/Tests/TerentoPoCTests/BoundedNativeProcessTests.swift" -o "$build/swift-$mode"
    if ! TERENTO_FINISHING_TRACE=1 "$build/swift-$mode" 2> "$build/swift-$mode.log"; then
        cat "$build/swift-$mode.log" >&2
        exit 1
    fi
done
[[ ! -s "$build/swift-release.log" ]]
grep -q 'event=worker_deadline' "$build/swift-debug.log"
grep -q 'event=worker_cancelled' "$build/swift-debug.log"
grep -q 'event=worker_exited' "$build/swift-debug.log"
if ! TERENTO_FINISHING_TRACE=0 "$build/swift-debug" 2> "$build/swift-off.log"; then
    cat "$build/swift-off.log" >&2
    exit 1
fi
[[ ! -s "$build/swift-off.log" ]]

bridge_source="$project_root/Sources/LibMTPBridge/MTPBridge.c"
trace_source="$project_root/Sources/TerentoPoC/MTPTransport/BoundedNativeProcess.swift"
for event in session_open_begin session_open_end file_list_begin file_list_end \
    session_close_begin session_close_end native_cleanup_begin native_cleanup_end; do
    grep -Fq "\"$event\"" "$bridge_source"
    grep -Fq "\"$event\"" "$trace_source"
done
# The sampled read-back reports chunk timing per region and in total.
for event in region_timing read_timing; do
    grep -Fq "\"$event\"" "$bridge_source"
    grep -Fq "\"$event\"" "$trace_source"
done
[[ "$(grep -n '"session_open_begin"' "$bridge_source" | head -n 1 | cut -d: -f1)" -lt \
   "$(grep -n '"session_open_end"' "$bridge_source" | head -n 1 | cut -d: -f1)" ]]
[[ "$(grep -n '"file_list_begin"' "$bridge_source" | head -n 1 | cut -d: -f1)" -lt \
   "$(grep -n '"file_list_end"' "$bridge_source" | head -n 1 | cut -d: -f1)" ]]
[[ "$(grep -n '"session_close_begin"' "$bridge_source" | head -n 1 | cut -d: -f1)" -lt \
   "$(grep -n '"session_close_end"' "$bridge_source" | head -n 1 | cut -d: -f1)" ]]
# Inventory bounds stay finite: a 60 s floor, scaled by observed objects, capped at 600 s.
grep -Fq 'static let inventoryBaseTimeout: TimeInterval = 60' \
    "$project_root/Sources/TerentoPoC/Installation/MTPMapInstallationTransport.swift"
grep -Fq 'static let inventoryMaximumTimeout: TimeInterval = 600' \
    "$project_root/Sources/TerentoPoC/Installation/MTPMapInstallationTransport.swift"
grep -Fq 'return inventoryTimeout(expectedObjectCount: request.expectedObjectCount)' \
    "$project_root/Sources/TerentoPoC/Installation/MTPMapInstallationTransport.swift"
print 'PASS: normal-build private native trace and strict Swift diagnostics pass; Debug stderr remains opt-in; checkpoints throttled; exact failure counters retained; deadline/cancellation still reap workers'
