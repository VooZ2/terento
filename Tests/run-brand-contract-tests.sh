#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h}"
PYTHONDONTWRITEBYTECODE=1 python3 "$repo_root/Tests/brand-contract-tests.py"
