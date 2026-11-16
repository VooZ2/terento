#!/usr/bin/env python3
"""Reject bare `! command` assertions in tracked `set -e` shell scripts.

POSIX `set -e` ignores the exit status of a pipeline negated with `!`, so a
line such as `! grep -q secret file` never stops the script, even when it
matches. Absence checks must use `if ...; then exit 1; fi` (2026-11-16: five
IndexNow runtime assertions, one of them the key-leak check, could not fail).
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SET_E = re.compile(r"^\s*set\s+-[a-zA-Z]*e", re.M)
BARE_NEGATION = re.compile(r"^\s*!\s+\S")


def main():
    paths = subprocess.check_output(["git", "ls-files", "*.sh"], cwd=ROOT, text=True).splitlines()
    errors = []
    for name in paths:
        file = ROOT / name
        if not file.is_file():
            continue
        text = file.read_text(encoding="utf-8", errors="replace")
        if not SET_E.search(text):
            continue
        continued = False
        for number, line in enumerate(text.splitlines(), 1):
            # A `!` after a backslash continuation is an argument (find ! -name).
            if not continued and BARE_NEGATION.match(line):
                errors.append(f"{name}:{number}: bare `!` statement is ignored by set -e: {line.strip()}")
            continued = line.rstrip().endswith("\\")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Shell negated-assertion check passed for {len(paths)} tracked script(s).")


if __name__ == "__main__":
    main()
