#!/usr/bin/env python3
"""Refresh the public compatibility snapshot from the live evidence API."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "site/compatibility/public-models.snapshot.json"
API_URL = "https://api.terento.app/compatibility/public/models.json?limit=500"
STATUS_CODES = {"TESTING", "TESTED", "SUPPORTED", "VERIFIED"}


def fetch_payload() -> dict:
    request = urllib.request.Request(
        API_URL,
        headers={"Accept": "application/json", "User-Agent": "Terento compatibility snapshot updater"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("schemaVersion") != 1 or not isinstance(payload.get("generatedAt"), str):
        raise ValueError("compatibility API must return schemaVersion 1 and generatedAt")
    models = payload.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("compatibility API models must be a non-empty array")
    identities = set()
    for row in models:
        if not isinstance(row, dict):
            raise ValueError("compatibility API model rows must be objects")
        identity = str(row.get("compatibilityIdentity") or row.get("model") or "").strip()
        status = str(row.get("evidenceStatus") or row.get("status") or "").upper()
        attempted = row.get("attemptedInstallations", row.get("attempted", 0))
        successful = row.get("successfulInstallations", row.get("successful", 0))
        if not identity or identity in identities:
            raise ValueError(f"compatibility API has missing or duplicate identity: {identity!r}")
        if status not in STATUS_CODES:
            raise ValueError(f"compatibility API has unsupported status: {status!r}")
        if not isinstance(attempted, int) or not isinstance(successful, int) or attempted < 1 or successful < 1 or successful > attempted:
            raise ValueError(f"compatibility API has invalid evidence counts for {identity!r}")
        identities.add(identity)
    return payload


def evidence_signature(payload: dict) -> str:
    models = sorted(
        payload["models"],
        key=lambda row: str(row.get("compatibilityIdentity") or row.get("model") or "").casefold(),
    )
    return json.dumps(
        {"schemaVersion": payload["schemaVersion"], "models": models},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def main() -> None:
    fresh = fetch_payload()
    current = json.loads(SNAPSHOT.read_text(encoding="utf-8")) if SNAPSHOT.exists() else None
    if current and evidence_signature(current) == evidence_signature(fresh):
        print("Compatibility snapshot unchanged; evidence data has not changed.")
        return
    SNAPSHOT.write_text(json.dumps(fresh, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {SNAPSHOT.relative_to(ROOT)} with {len(fresh['models'])} evidence rows.")


if __name__ == "__main__":
    main()
