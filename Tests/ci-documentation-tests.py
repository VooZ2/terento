#!/usr/bin/env python3
"""Validate local public documentation links and explicit current-release references."""
import json
import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent

PUBLIC_COPY_SOURCES = (
    "README.md",
    "site/localized-content.js",
    "site/metadata.json",
    "scripts/add-guide-links.py",
    "scripts/build-about-pages.py",
    "scripts/build-compatibility-pages.py",
    "scripts/build-guide-pages.py",
    "scripts/normalize-home-ia.py",
)
INVALID_PUBLIC_COPY = (
    re.compile(r"The Compatibility page is the official public list", re.I),
    re.compile(r"official[^.]{0,100}(?:single|only|unique) public list", re.I),
    re.compile(r"offizielle[^.]{0,120}einzige öffentliche Liste", re.I),
    re.compile(r"liste publique unique", re.I),
    re.compile(r"jedyną publiczną listą", re.I),
    re.compile(r"jediným veřejným seznamem", re.I),
    re.compile(r"unico elenco pubblico", re.I),
    re.compile(r"\*\*(?:Tested|Supported|Verified)\*\*\s*[—-]\s*\d", re.I),
)

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

    public_paths = [ROOT / name for name in PUBLIC_COPY_SOURCES]
    tracked_site_files = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "site"], cwd=ROOT,
    ).decode().split("\0")
    public_paths.extend(
        ROOT / name for name in tracked_site_files if name.endswith((".html", ".js"))
    )
    for file in public_paths:
        if not file.exists():
            continue
        source = file.read_text()
        for pattern in INVALID_PUBLIC_COPY:
            if pattern.search(source):
                errors.append(f"{file.relative_to(ROOT)}: known-invalid public compatibility copy: {pattern.pattern}")
    if errors:
        raise AssertionError("\n".join(errors))
    print(
        f"PASS: {len(paths)} tracked Markdown paths and {len(public_paths)} public copy files "
        "checked for links, release references, and known-invalid compatibility copy",
    )

if __name__ == "__main__":
    main()
