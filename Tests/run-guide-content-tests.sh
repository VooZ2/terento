#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
node Tests/guide-content-tests.cjs
