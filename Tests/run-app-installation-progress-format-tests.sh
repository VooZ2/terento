#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h}"
connect_screen="$repo_root/app/TerentoCore/Sources/TerentoPoC/Views/ConnectScreen.swift"

speed_lines="$(rg -n 'formatBytesPerSecond\([^)]*\)' "$connect_screen")"

if [[ "$speed_lines" == *' /s'* ]]; then
    print -u2 "FAIL: download speeds contain a space before /s"
    exit 1
fi

expected_count="$(rg -oF '))/s' "$connect_screen" | wc -l | tr -d ' ')"
if [[ "$expected_count" -ne 2 ]]; then
    print -u2 "FAIL: expected 2 live compact progress speed labels, found $expected_count"
    exit 1
fi

print "PASS: installation progress speeds use compact <unit>/s formatting"
