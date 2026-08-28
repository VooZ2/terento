#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")/.."
node Tests/faq-content-tests.cjs
