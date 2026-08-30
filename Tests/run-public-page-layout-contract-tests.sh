#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
node Tests/public-page-layout-contract-tests.cjs
