#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
node Tests/release-documentation-tests.cjs
