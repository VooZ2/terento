#!/usr/bin/env python3
"""Validate local public documentation links and explicit current-release references."""
import json
import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent

def main():
    current = json.loads((ROOT / "site/updates/macos-arm64.json").read_text())["releaseLabel"].split("-", 1)[-1]
    errors = []
    # Limit to tracked source: caches and downloaded historical clients are not documentation.
    import subprocess
    paths = subprocess.check_output(["git", "ls-files", "*.md"], cwd=ROOT, text=True).splitlines()
    for name in paths:
        file = ROOT / name
        if not file.exists():
            continue  # staged cleanup can remove a tracked file before commit
        source = file.read_text()
        if not name.startswith("history/") and "/Fixtures/" not in name:
            for label in re.findall(r"\bcurrent\s+(beta\.\d+)\b", source, flags=re.I):
                if label.lower() != current.lower():
                    errors.append(f"{name}: current release reference {label} differs from {current}")
        for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", source):
            target = target.split("#", 1)[0].split("?", 1)[0]
            if not target or re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", target):
                continue
            target = unquote(target.strip("<>"))
            destination = ROOT / "site" / target.lstrip("/") if target.startswith("/") else file.parent / target
            if not destination.exists():
                errors.append(f"{name}: missing local link {target}")
    if errors:
        raise AssertionError("\n".join(errors))
    print(f"PASS: {len(paths)} tracked Markdown paths checked for links and current release references")

if __name__ == "__main__":
    main()
