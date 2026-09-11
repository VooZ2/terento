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
print 'PASS: normal-build private native trace and strict Swift diagnostics pass; Debug stderr remains opt-in; checkpoints throttled; exact failure counters retained; deadline/cancellation still reap workers'
