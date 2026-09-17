"""Pure classification rules for Terento's retained statistics streams.

This module intentionally has no database or HTTP dependencies.  The SQL
read models mirror these rules, while these functions provide deterministic
fixtures and regression coverage for the meanings exposed by the admin UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


SUCCESS = "success"
FAILURE = "failure"
NOT_STARTED = "not_started"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class ClassifiedResult:
    key: tuple[str, ...]
    classification: str
    provider: str | None
    region: str | None
    map_id: str | None
    timestamp: Any = None
    event: dict[str, Any] | None = None


@dataclass(frozen=True)
class FreshInstallSummary:
    successes: int
    failures: int
    completed: int
    success_rate: float | None
    results: tuple[ClassifiedResult, ...]


def _value(event: dict[str, Any], camel: str, snake: str) -> Any:
    return event.get(camel, event.get(snake))


def result_key(event: dict[str, Any]) -> tuple[str, ...]:
    """Return the identity of one map result, never of the whole batch."""
    operation_id = _value(event, "operationId", "operation_id")
    result_index = _value(event, "mapResultIndex", "map_result_index")
    event_id = _value(event, "id", "event_id")
    if operation_id is not None and result_index is not None:
        return ("result", str(operation_id), str(result_index))
    if event_id is not None:
        return ("event", str(event_id))
    # Test data and pre-contract historical rows may not have an event ID.
    # Keep such rows visible, but do not collapse distinct custom images by
    # provider and region alone.
    return (
        "unidentified",
        str(operation_id or "unknown-operation"),
        str(result_index if result_index is not None else id(event)),
    )


def _is_legacy(event: dict[str, Any]) -> bool:
    return _value(event, "schemaVersion", "schema_version") in (1, 2) or (
        _value(event, "schemaVersion", "schema_version") is None
        and _value(event, "appBuild", "app_build") is None
        and _value(event, "releaseLabel", "release_label") is None
    )


def classify_fresh_result(event: dict[str, Any]) -> str:
    """Classify one compatibility event as a fresh-map result.

    A final failed event is a failed fresh install only when writing really
    started.  A missing write fact is accepted only for legacy records where
    that field did not exist; current unknown data is excluded rather than
    guessed into the denominator.
    """
    phase = str(_value(event, "phaseOutcome", "phase_outcome") or "").upper()
    finishing = str(
        _value(event, "automaticFinishingResult", "automatic_finishing_result") or ""
    ).upper()
    if phase == "SUCCEEDED" and finishing == "VERIFIED":
        return SUCCESS
    if phase == "FAILED":
        write_started = _value(event, "writeStarted", "write_started")
        if write_started is True or (write_started is None and _is_legacy(event)):
            return FAILURE
        return NOT_STARTED if write_started is False else UNKNOWN
    if phase == "NOT_STARTED":
        return NOT_STARTED
    return UNKNOWN


def _deduplicate_results(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate replayed result payloads while retaining contradictions.

    The ingestion primary key normally removes exact replay duplicates.  The
    pure read model also handles fixtures that repeat a logical result with a
    different transport envelope.  Any contradictory classification for the
    same logical result (including success/not-started and started-failure /
    not-started) remains unknown so the aggregate never invents a count.
    """
    by_event_id: dict[str, dict[str, Any]] = {}
    for event in events:
        event_id = _value(event, "id", "event_id")
        if event_id is not None:
            by_event_id.setdefault(str(event_id), event)
        else:
            by_event_id[f"anonymous:{id(event)}"] = event

    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for event in by_event_id.values():
        groups.setdefault(result_key(event), []).append(event)

    result: list[dict[str, Any]] = []
    for group in groups.values():
        classes = {classify_fresh_result(event) for event in group}
        if len(classes) > 1:
            base = dict(max(group, key=lambda item: str(_value(item, "timestamp", "occurred_at") or "")))
            base["__classification_override"] = UNKNOWN
            result.append(base)
        else:
            result.append(max(group, key=lambda item: str(_value(item, "timestamp", "occurred_at") or "")))
    return result


def summarize_fresh_installs(events: Iterable[dict[str, Any]]) -> FreshInstallSummary:
    classified: list[ClassifiedResult] = []
    for event in _deduplicate_results(events):
        classification = event.get("__classification_override") or classify_fresh_result(event)
        classified.append(
            ClassifiedResult(
                key=result_key(event),
                classification=classification,
                provider=_value(event, "provider", "provider_id"),
                region=_value(event, "region", "canonical_region_id"),
                map_id=_value(event, "mapId", "map_package_id"),
                timestamp=_value(event, "timestamp", "occurred_at"),
                event=event,
            )
        )
    successes = sum(item.classification == SUCCESS for item in classified)
    failures = sum(item.classification == FAILURE for item in classified)
    completed = successes + failures
    return FreshInstallSummary(
        successes=successes,
        failures=failures,
        completed=completed,
        success_rate=successes / completed if completed else None,
        results=tuple(classified),
    )


def _terminal_event_type(event: dict[str, Any]) -> str:
    return str(_value(event, "eventType", "event_type") or "").upper()


def summarize_acquisitions(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Count terminal provider acquisitions; lifecycle phases are excluded."""
    terminal_types = {"DOWNLOAD_SUCCEEDED", "DOWNLOAD_FAILED"}
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for event in events:
        event_type = _terminal_event_type(event)
        if event_type not in terminal_types or str(_value(event, "providerId", "provider_id") or "").lower() == "custom":
            continue
        acquisition_id = _value(event, "acquisitionId", "acquisition_id")
        if acquisition_id is not None:
            key = ("acquisition", str(acquisition_id))
        else:
            key = (
                "legacy-acquisition",
                str(_value(event, "operationId", "operation_id") or _value(event, "id", "event_id") or id(event)),
                str(_value(event, "mapId", "map_package_id") or "unknown-map"),
            )
        groups.setdefault(key, []).append(event)
    successful = failed = 0
    for group in groups.values():
        types = {_terminal_event_type(event) for event in group}
        if len(types) != 1:
            continue
        if "DOWNLOAD_SUCCEEDED" in types:
            successful += 1
        elif "DOWNLOAD_FAILED" in types:
            failed += 1
    total = successful + failed
    return {
        "successful": successful,
        "failed": failed,
        "completed": total,
        "success_rate": successful / total if total else None,
    }


def summarize_updates(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Count only terminal update outcomes; fresh installs are untouched."""
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for event in events:
        event_type = _terminal_event_type(event)
        if event_type not in {"MAP_UPDATE_SUCCEEDED", "MAP_UPDATE_FAILED"}:
            continue
        event_id = _value(event, "id", "event_id")
        operation_id = _value(event, "operationId", "operation_id")
        map_id = _value(event, "mapId", "map_package_id")
        if event_id is not None:
            key = ("update-event", str(event_id))
        elif operation_id is not None and map_id is not None:
            key = ("update-result", str(operation_id), str(map_id))
        else:
            key = ("unidentified-update", str(id(event)))
        groups.setdefault(key, []).append(event)

    successful = failed = 0
    for group in groups.values():
        outcomes = {
            (_terminal_event_type(event), str(_value(event, "outcome", "outcome") or "").upper())
            for event in group
        }
        if len(outcomes) != 1:
            continue
        event_type, outcome = next(iter(outcomes))
        if event_type == "MAP_UPDATE_SUCCEEDED" and outcome == "SUCCEEDED":
            successful += 1
        elif event_type == "MAP_UPDATE_FAILED" and outcome == "FAILED":
            failed += 1
    completed = successful + failed
    return {
        "successful": successful,
        "failed": failed,
        "completed": completed,
        "success_rate": successful / completed if completed else None,
    }
