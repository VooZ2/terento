from __future__ import annotations

import re
from typing import Any


_CANONICAL_KEYS = {
    "acquisition": "acquisition",
    "transport": "transport",
    "verification": "verification",
    "transferverification": "verification",
    "storage": "storage",
    "devicedisconnected": "device_disconnected",
    "sourcevalidation": "source_validation",
    "unknown": "unknown",
}

_LABELS = {
    "acquisition": "Map acquisition",
    "transport": "Device transport",
    "verification": "Transfer verification",
    "storage": "Storage",
    "device_disconnected": "Device disconnected",
    "source_validation": "Source validation",
    "unknown": "Unknown",
}


def _reason_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().casefold())


def normalize_failure_reason(
    error_category: Any = None,
    *,
    failure_stage: Any = None,
    failure_code: Any = None,
) -> str:
    """Normalize existing diagnostic fields without changing stored evidence."""
    category_token = _reason_token(error_category)
    category = _CANONICAL_KEYS.get(category_token)
    if category is None:
        for suffix in ("failed", "failure", "errors", "error"):
            if category_token.endswith(suffix):
                category = _CANONICAL_KEYS.get(category_token.removesuffix(suffix))
                if category is not None:
                    break
    if category and category != "unknown":
        return category

    stage_token = _reason_token(failure_stage)
    code_token = _reason_token(failure_code)
    if stage_token == "sourcevalidation" or "sourcevalidation" in code_token:
        return "source_validation"
    if stage_token in {"download", "extract"} or "downloadfailed" in code_token:
        return "acquisition"
    if stage_token == "write" or (
        "device" in code_token and "disconnect" in code_token
    ):
        return "device_disconnected" if "disconnect" in code_token else "transport"
    if stage_token == "verify" or "mismatch" in code_token or "verification" in code_token:
        return "verification"
    if "space" in code_token or "storage" in code_token:
        return "storage"
    return category or "unknown"


def failure_reason_label(value: Any) -> str:
    key = normalize_failure_reason(value)
    return _LABELS.get(key, "Installation failure")
