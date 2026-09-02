from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit


KINDS = {"WEEKLY_TEST", "RELEASE_GATE", "DEPLOYMENT"}
COMPONENTS = {"test-matrix", "release", "site", "catalog-api"}
STATUSES = {"HEALTHY", "WARNING", "FAILED", "UNKNOWN"}
IDENTIFIER = re.compile(r"[A-Za-z0-9._:-]{1,160}")
COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
SEMVER = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?")


class OperationalObservationError(ValueError):
    pass


def validate_observation(document: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "schemaVersion", "observationId", "kind", "component", "status",
        "observedAt", "sourceRunId", "sourceRunUrl", "commitSha",
        "releaseVersion", "buildNumber", "summary", "details",
    }
    if set(document) - allowed or document.get("schemaVersion") != 1:
        raise OperationalObservationError("invalid_observation_contract")

    observation_id = _identifier(document.get("observationId"), "observation_id")
    source_run_id = _identifier(document.get("sourceRunId"), "source_run_id")
    kind = str(document.get("kind") or "").strip().upper()
    component = str(document.get("component") or "").strip().lower()
    status = str(document.get("status") or "").strip().upper()
    if kind not in KINDS or component not in COMPONENTS or status not in STATUSES:
        raise OperationalObservationError("invalid_observation_classification")

    commit_sha = str(document.get("commitSha") or "").strip().lower()
    if not COMMIT_SHA.fullmatch(commit_sha):
        raise OperationalObservationError("invalid_commit_sha")

    run_url = str(document.get("sourceRunUrl") or "").strip()
    parsed_url = urlsplit(run_url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "github.com"
        or not parsed_url.path.startswith("/VooZ2/terento/actions/runs/")
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise OperationalObservationError("invalid_source_run_url")

    observed_at = _timestamp(document.get("observedAt"))
    release_version = _optional_text(document.get("releaseVersion"), 80)
    if release_version and not SEMVER.fullmatch(release_version):
        raise OperationalObservationError("invalid_release_version")
    build_number = _optional_text(document.get("buildNumber"), 40)
    if build_number and not build_number.isdigit():
        raise OperationalObservationError("invalid_build_number")
    summary = _optional_text(document.get("summary"), 1_000)
    details = document.get("details") or {}
    if not isinstance(details, dict) or len(details) > 32:
        raise OperationalObservationError("invalid_details")
    normalized_details: dict[str, str | int | float | bool | None] = {}
    for key, value in details.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", key):
            raise OperationalObservationError("invalid_detail_key")
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise OperationalObservationError("invalid_detail_value")
        if isinstance(value, str) and len(value) > 500:
            raise OperationalObservationError("invalid_detail_value")
        normalized_details[key] = value
    # Keep storage bounded independently from the HTTP body limit.
    if len(json.dumps(normalized_details, separators=(",", ":"))) > 8_000:
        raise OperationalObservationError("invalid_details")

    return {
        "observation_id": observation_id,
        "kind": kind,
        "component": component,
        "status": status,
        "observed_at": observed_at,
        "source_run_id": source_run_id,
        "source_run_url": run_url,
        "commit_sha": commit_sha,
        "release_version": release_version,
        "build_number": build_number,
        "summary": summary,
        "details": normalized_details,
    }


def _identifier(value: Any, field: str) -> str:
    candidate = str(value or "").strip()
    if not IDENTIFIER.fullmatch(candidate):
        raise OperationalObservationError(f"invalid_{field}")
    return candidate


def _timestamp(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise OperationalObservationError("invalid_observed_at") from None
    if parsed.tzinfo is None:
        raise OperationalObservationError("invalid_observed_at")
    normalized = parsed.astimezone(timezone.utc)
    if abs((datetime.now(timezone.utc) - normalized).total_seconds()) > 7 * 86400:
        raise OperationalObservationError("observed_at_out_of_range")
    return normalized


def _optional_text(value: Any, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise OperationalObservationError("invalid_text_value")
    candidate = value.strip()
    if not candidate:
        return None
    if len(candidate) > maximum or any(ord(character) < 32 and character not in "\n\t" for character in candidate):
        raise OperationalObservationError("invalid_text_value")
    return candidate

