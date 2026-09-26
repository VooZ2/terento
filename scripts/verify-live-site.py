#!/usr/bin/env python3
"""Verify the public site content before any IndexNow submission."""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://terento.app"
SITEMAP_PATH = ROOT / "site" / "sitemap.xml"


def page_matches(expected: bytes, live: bytes) -> bool:
    """Compare exact HTML, undoing only observed Cloudflare email rewrites.

    Every decoded href must already occur in the expected source. Other edge
    injections, changed content and unexpected decoder shapes still fail closed.
    """
    if live == expected:
        return True
    restored = 0

    def restore_href(match: re.Match[bytes]) -> bytes:
        nonlocal restored
        try:
            encoded = bytes.fromhex(match.group(1).decode("ascii"))
            decoded = bytes(value ^ encoded[0] for value in encoded[1:])
        except (ValueError, IndexError):
            return match.group(0)
        href = b'href="mailto:' + decoded + b'"'
        if not decoded or href not in expected:
            return match.group(0)
        restored += 1
        return href

    normalized = re.sub(
        rb'href="/cdn-cgi/l/email-protection#([0-9a-fA-F]+)"',
        restore_href, live,
    )
    def restore_text(match: re.Match[bytes]) -> bytes:
        nonlocal restored
        try:
            encoded = bytes.fromhex(match.group(1).decode("ascii"))
            decoded = bytes(value ^ encoded[0] for value in encoded[1:])
        except (ValueError, IndexError):
            return match.group(0)
        if not decoded or decoded not in expected:
            return match.group(0)
        restored += 1
        return decoded

    normalized = re.sub(
        rb'<span class="__cf_email__" data-cfemail="([0-9a-fA-F]+)">'
        rb'\[email&#160;protected\]</span>', restore_text, normalized,
    )
    if not restored:
        return False
    # Match the observed decoder before </body> or the shell translation data.
    # Do not discard arbitrary script tags or normalize other HTML differences.
    normalized, decoder_count = re.subn(
        rb'<script data-cfasync="false" src="/cdn-cgi/scripts/5c5dd728/'
        rb'cloudflare-static/email-decode\.min\.js"></script>'
        rb'(?=</body>|<script type="application/json" id="shell-translations">)',
        b'', normalized,
    )
    return decoder_count == 1 and normalized == expected


def load_http():
    spec = importlib.util.spec_from_file_location("terento_ci_http", ROOT / "scripts" / "ci_http.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load CI HTTP helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fetch(http, label: str, url: str) -> bytes:
    code, body = http.request(
        label,
        ["--fail", "--connect-timeout", "5", "--max-time", "20", url],
    )
    if code:
        raise RuntimeError(f"{label} failed with transport/status code {code}")
    return body


def load_manifest(path: Path) -> dict[str, dict[str, object]]:
    import json

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("baseUrl") != BASE_URL or not isinstance(value.get("pages"), list):
        raise ValueError("invalid current site manifest")
    pages: dict[str, dict[str, object]] = {}
    for page in value["pages"]:
        if not isinstance(page, dict) or not isinstance(page.get("url"), str):
            raise ValueError("invalid current site manifest page")
        pages[page["url"]] = page
    return pages


def verify_key(http, key: str) -> None:
    if len(key) != 32 or any(character not in "0123456789abcdefABCDEF" for character in key):
        raise ValueError("configured IndexNow key does not match the required 32-hex format")
    body = fetch(http, "live IndexNow key file", f"{BASE_URL}/{key}.txt")
    if body != key.encode("ascii"):
        raise RuntimeError("live IndexNow key file does not contain the configured key")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-manifest", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--verify-key", action="store_true")
    parser.add_argument("--key-env", default="TERENTO_INDEXNOW_KEY")
    args = parser.parse_args()
    for name in ("current_manifest", "plan"):
        path = getattr(args, name)
        if not path.is_absolute():
            setattr(args, name, ROOT / path)

    try:
        import json

        http = load_http()
        current = load_manifest(args.current_manifest)
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        entries = plan.get("entries", []) if isinstance(plan, dict) else []
        expected_sitemap = SITEMAP_PATH.read_bytes()
        if fetch(http, "live sitemap", f"{BASE_URL}/sitemap.xml") != expected_sitemap:
            raise RuntimeError("live sitemap differs from the tested sitemap")

        checked = 0
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("kind") == "removed":
                continue
            url = entry.get("url")
            page = current.get(url)
            if not isinstance(url, str) or not isinstance(page, dict) or not isinstance(page.get("file"), str):
                raise RuntimeError("IndexNow plan contains a current URL without a local page")
            expected = (ROOT / page["file"]).read_bytes()
            if not page_matches(expected, fetch(http, "live changed public page", url)):
                raise RuntimeError(f"live page differs from the tested public page: {url}")
            checked += 1

        if args.verify_key:
            key = os.environ.get(args.key_env, "")
            if not key:
                raise RuntimeError("IndexNow key verification requested but the CI key is not configured")
            verify_key(http, key)

        print(f"Live sitemap matches; {checked} changed/new public page(s) match the tested output.")
        if args.verify_key:
            print("Live IndexNow key file matches the configured secret.")
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"live public-site verification failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
