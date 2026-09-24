from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any


INSTALLATION_POLICY_SCHEMA_VERSION = 3
INSTALLATION_POLICY_VERSION = 3


def installation_base_model(model: str) -> str:
    """Derive the model identity from the catalog model label, not the SKU identity.

    The catalog's ``model`` groups variants; ``canonical_model`` may include
    Solar, Sapphire, or no-Wi-Fi SKU details. Match complete normalized tokens,
    never prefixes or device families.
    """
    normalized = unicodedata.normalize("NFKD", model).casefold()
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
    normalized = re.sub(r"^garmin\s+", "", normalized)
    normalized = re.split(
        r"\b(?:\d{2,3}\s*mm|sapphire|solar|amoled|mip|microled|inreach|leather|titanium|stainless|silicone)\b",
        normalized, maxsplit=1,
    )[0].strip()
    if not normalized or normalized.startswith("unknown"):
        raise ValueError("catalog model has no reliable base identity")
    return normalized


def installation_authorization_for_row(row: dict[str, Any]) -> tuple[str, str]:
    """Return the write policy derived from one exact catalog row.

    ``support_status`` is deliberately not read here. It is operator/admin
    metadata for compatibility review, not a native map-write permission.
    The policy is derived only from the catalog's active flag and nullable
    map capability value, and unknown capability always fails closed.
    """
    if row.get("active") is not True:
        return "OUT_OF_SCOPE", "BLOCKED"
    if row.get("map_capable") is True:
        return "IN_SCOPE", "APPROVED"
    if row.get("map_capable") is False:
        return "OUT_OF_SCOPE", "BLOCKED"
    return "UNKNOWN", "PENDING"


def summarize_installation_catalog(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count all Garmin policy rows by the stored nullable map capability."""
    summary = {
        "total": len(rows),
        "mapCapableTrue": 0,
        "mapCapableFalse": 0,
        "mapCapableNull": 0,
        "activeMapCapableTrueApproved": 0,
        "activeMapCapableFalseBlocked": 0,
        "activeMapCapableNullPending": 0,
    }
    for row in rows:
        value = row.get("map_capable")
        if value is True:
            summary["mapCapableTrue"] += 1
        elif value is False:
            summary["mapCapableFalse"] += 1
        else:
            summary["mapCapableNull"] += 1

        scope, authorization = installation_authorization_for_row(row)
        if row.get("active") is True and value is True and scope == "IN_SCOPE" and authorization == "APPROVED":
            summary["activeMapCapableTrueApproved"] += 1
        elif row.get("active") is True and value is False and authorization == "BLOCKED":
            summary["activeMapCapableFalseBlocked"] += 1
        elif row.get("active") is True and value is None and authorization == "PENDING":
            summary["activeMapCapableNullPending"] += 1
    return summary


def build_installation_policy(
    rows: list[dict[str, Any]], updated_at: datetime
) -> dict[str, Any]:
    devices: list[dict[str, Any]] = []
    for row in rows:
        map_capable = row.get("map_capable")
        scope, authorization = installation_authorization_for_row(row)

        devices.append(
            {
                "id": row["device_id"],
                "manufacturer": _text(row.get("manufacturer")),
                "model": _text(row.get("model")),
                "baseModel": installation_base_model(row["model"]),
                "canonicalModel": _text(row.get("canonical_model")),
                "variant": _text(row.get("variant")),
                "caseSizeMm": row.get("case_size_mm"),
                "displayType": _text(row.get("display_type")),
                "screenTechnology": row.get("screen_technology"),
                "solar": row.get("solar"),
                "inReach": row.get("inreach"),
                "active": bool(row.get("active")),
                "mapCapable": map_capable if isinstance(map_capable, bool) else None,
                "scope": scope,
                "installationAuthorization": authorization,
            }
        )

    devices.sort(key=lambda item: item["id"])
    return {
        "schemaVersion": INSTALLATION_POLICY_SCHEMA_VERSION,
        "policyVersion": INSTALLATION_POLICY_VERSION,
        "updatedAt": _format_timestamp(updated_at),
        "manufacturer": "Garmin",
        "devices": devices,
    }


def serialize_installation_policy(policy: dict[str, Any]) -> bytes:
    return json.dumps(policy, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def installation_policy_etag(body: bytes) -> str:
    return f'"{hashlib.sha256(body).hexdigest()}"'


def _text(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
