#!/usr/bin/env python3
"""Fetch, validate, and publish the deterministic public compatibility snapshot."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_URL = "https://api.terento.app/compatibility/public/models.json?limit=500"
SNAPSHOT_PATH = ROOT / "site/compatibility/public-models.snapshot.json"
GENERATOR_PATH = ROOT / "scripts/build-compatibility-pages.py"

PUBLIC_FIELDS = (
    "model",
    "variant",
    "caseSizeMm",
    "displayType",
    "screenTechnology",
    "solar",
    "inReach",
    "family",
    "familyName",
    "imageUrl",
    "successfulInstallations",
    "lastSuccessfulInstallation",
)


def read_payload(path: Path | None) -> dict:
    if path:
        return json.loads(path.read_text(encoding="utf-8"))
    request = urllib.request.Request(API_URL, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def number(value: object, field: str, index: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"models[{index}].{field} must be a number")
    result = int(value)
    if result < 0:
        raise ValueError(f"models[{index}].{field} must not be negative")
    return result


def normalized_model(model: object, index: int) -> dict[str, object]:
    if not isinstance(model, dict):
        raise ValueError(f"models[{index}] must be an object")
    successful = number(
        model.get("successfulInstallations", model.get("successful_install_count", 0)),
        "successfulInstallations",
        index,
    )
    if successful < 1:
        return {}
    display_model = str(model.get("model", "")).strip()
    if not display_model:
        raise ValueError(f"models[{index}].model must not be empty")
    last_success = model.get("lastSuccessfulInstallation", model.get("last_successful_installation"))
    if last_success is not None and not isinstance(last_success, str):
        raise ValueError(f"models[{index}].lastSuccessfulInstallation must be a string or null")
    image = model.get("image") if isinstance(model.get("image"), dict) else {}
    normalized = {
        "model": display_model,
        "variant": model.get("variant"),
        "caseSizeMm": model.get("caseSizeMm", model.get("case_size_mm")),
        "displayType": model.get("displayType", model.get("display_type")),
        "screenTechnology": model.get("screenTechnology", model.get("screen_technology")),
        "solar": model.get("solar"),
        "inReach": model.get("inReach", model.get("inreach")),
        "family": str(model.get("family", "other")).strip() or "other",
        "familyName": str(model.get("familyName", model.get("family_name", model.get("family", "Other")))).strip() or "Other",
        "imageUrl": image.get("url") or model.get("imageUrl"),
        "successfulInstallations": successful,
        "lastSuccessfulInstallation": last_success,
    }
    return {field: normalized[field] for field in PUBLIC_FIELDS}


def model_sort_key(model: dict[str, object]) -> tuple[object, ...]:
    return (
        -int(model["successfulInstallations"]),
        str(model["model"]).casefold(),
        str(model.get("variant") or "").casefold(),
        str(model.get("family") or "").casefold(),
    )


def build_snapshot(payload: object, previous: dict | None) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        raise ValueError("compatibility response must contain a models array")
    models = [normalized for index, raw in enumerate(payload["models"]) if (normalized := normalized_model(raw, index))]
    models.sort(key=model_sort_key)
    if not models:
        raise ValueError("compatibility response contains no successful public models")
    factual = {"schemaVersion": 1, "models": models}
    if previous and previous.get("schemaVersion") == 1 and previous.get("models") == models:
        generated_at = previous.get("generatedAt")
    else:
        generated_at = payload.get("generatedAt")
        if not isinstance(generated_at, str) or not generated_at:
            raise ValueError("compatibility response must contain generatedAt")
    return {**factual, "generatedAt": generated_at}


def write_if_changed(snapshot: dict, path: Path) -> bool:
    rendered = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == rendered:
        return False
    path.write_text(rendered, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, help="read a local API fixture instead of using the live endpoint")
    parser.add_argument("--output", type=Path, default=SNAPSHOT_PATH, help="snapshot output path")
    parser.add_argument("--no-pages", action="store_true", help="only write and validate the snapshot")
    args = parser.parse_args()
    try:
        previous = json.loads(args.output.read_text(encoding="utf-8")) if args.output.exists() else None
        snapshot = build_snapshot(read_payload(args.input), previous)
        changed = write_if_changed(snapshot, args.output)
        if not args.no_pages:
            if args.output.resolve() != SNAPSHOT_PATH.resolve():
                raise ValueError("page generation requires the canonical snapshot output path")
            subprocess.run([sys.executable, str(GENERATOR_PATH)], cwd=ROOT, check=True)
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Compatibility snapshot {'updated' if changed else 'unchanged'}: {args.output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
