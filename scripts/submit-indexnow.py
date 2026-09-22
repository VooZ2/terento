#!/usr/bin/env python3
"""Plan and optionally submit Terento's post-deploy IndexNow notifications.

The script deliberately has no default network mode.  ``--dry-run`` only
prints a plan, ``--record-published`` advances the local state without an
IndexNow request, ``--report-only`` creates a safe workflow observation without
an IndexNow request, and ``--send`` is the explicit real-submission mode.
``--manual-url`` narrows that mode to one explicitly selected, currently
indexable public URL for an operator-triggered bootstrap submission; it never
runs by itself on a normal deployment.
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen


ROOT = Path(__file__).resolve().parents[1]
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
BASE_URL = "https://terento.app"
HOST = "terento.app"
SCHEMA_VERSION = 1
MAX_URLS = 10_000
REQUEST_TIMEOUT = 10
OVERALL_TIMEOUT = 60
MAX_ATTEMPTS = 3
KEY_RE = re.compile(r"^[0-9a-fA-F]{32}$")
TRANSIENT_STATUSES = {429, 500, 502, 503, 504, 520, 521, 522, 523, 524, 525, 526}
REPORT_RESULTS = {
    "submitted", "validation_pending", "no_changes", "pending_retry",
    "action_required", "not_initialized", "bootstrap",
    "live_verification_failed", "partial_success",
}
REPORT_SUMMARIES = {
    "submitted": "IndexNow notification was accepted with HTTP 200.",
    "validation_pending": "IndexNow accepted the notification with HTTP 202; validation is pending.",
    "no_changes": "No eligible URL changes were found for IndexNow.",
    "pending_retry": "IndexNow notification was not accepted; pending URLs were retained for retry.",
    "action_required": "IndexNow requires configuration or request correction.",
    "not_initialized": "IndexNow is not initialized for a production publication.",
    "bootstrap": "IndexNow baseline was initialized without submitting URLs.",
    "live_verification_failed": "Live public-site verification failed before IndexNow notification.",
    "partial_success": "The IndexNow submission was only partially accepted.",
}


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, msg, headers, new_url):  # type: ignore[override]
        return None


NO_REDIRECT_OPENER = build_opener(NoRedirectHandler)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != HOST or parsed.query or parsed.fragment:
        raise ValueError(f"invalid public URL: {url}")
    if not parsed.path.startswith("/") or (parsed.path != "/" and not parsed.path.endswith("/")):
        raise ValueError(f"public URL must preserve canonical trailing slash: {url}")


def validate_manifest(value: object) -> dict[str, dict[str, object]]:
    if not isinstance(value, dict) or value.get("schemaVersion") != SCHEMA_VERSION or value.get("baseUrl") != BASE_URL:
        raise ValueError("invalid site content manifest")
    pages = value.get("pages")
    if not isinstance(pages, list):
        raise ValueError("site content manifest pages must be a list")
    result: dict[str, dict[str, object]] = {}
    for page in pages:
        if not isinstance(page, dict):
            raise ValueError("site content manifest page must be an object")
        path = page.get("path")
        url = page.get("url")
        fingerprint = page.get("fingerprint")
        if not isinstance(path, str) or not isinstance(url, str) or not isinstance(fingerprint, str):
            raise ValueError("manifest page is missing path, url or fingerprint")
        validate_url(url)
        if url != f"{BASE_URL}{path}" or path in result:
            raise ValueError(f"manifest URL/path is not canonical or is duplicated: {path}")
        if not isinstance(page.get("indexable"), bool):
            raise ValueError(f"manifest page indexability is not boolean: {path}")
        result[path] = dict(page)
    return result


def empty_state() -> dict[str, object]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "bootstrap",
        "published": None,
        "indexNow": {"accepted": [], "pending": []},
    }


def load_state(path: Path) -> tuple[dict[str, object], bool]:
    try:
        value = load_json(path)
    except (OSError, json.JSONDecodeError):
        return empty_state(), True
    if not isinstance(value, dict) or value.get("schemaVersion") != SCHEMA_VERSION:
        return empty_state(), True
    published = value.get("published")
    if value.get("status") != "published" or not isinstance(published, dict) or not isinstance(published.get("pages"), list):
        return empty_state(), True
    try:
        validate_manifest({"schemaVersion": SCHEMA_VERSION, "baseUrl": BASE_URL, "pages": published["pages"]})
    except ValueError:
        return empty_state(), True
    index_now = value.get("indexNow")
    if not isinstance(index_now, dict):
        return empty_state(), True
    if not isinstance(index_now.get("accepted"), list) or not isinstance(index_now.get("pending"), list):
        return empty_state(), True
    return value, False


def page_snapshot(page: dict[str, object]) -> dict[str, object]:
    fields = ("path", "url", "file", "locale", "indexable", "fingerprint", "lastmod")
    return {key: page[key] for key in fields if key in page}


def current_pages_from_manifest(path: Path) -> dict[str, dict[str, object]]:
    return validate_manifest(load_json(path))


def published_pages(state: dict[str, object]) -> dict[str, dict[str, object]]:
    published = state.get("published")
    if not isinstance(published, dict):
        return {}
    pages = published.get("pages")
    if not isinstance(pages, list):
        return {}
    return {str(page["path"]): dict(page) for page in pages if isinstance(page, dict) and isinstance(page.get("path"), str)}


def pending_records(state: dict[str, object]) -> list[dict[str, object]]:
    index_now = state.get("indexNow")
    pending = index_now.get("pending") if isinstance(index_now, dict) else []
    return [dict(record) for record in pending if isinstance(record, dict) and isinstance(record.get("url"), str)]


def accepted_records(state: dict[str, object]) -> list[dict[str, object]]:
    index_now = state.get("indexNow")
    accepted = index_now.get("accepted") if isinstance(index_now, dict) else []
    return [dict(record) for record in accepted if isinstance(record, dict) and isinstance(record.get("url"), str)]


def merge_accepted_records(state: dict[str, object], accepted: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for record in [*accepted_records(state), *accepted]:
        url = record.get("url")
        fingerprint = record.get("fingerprint", "")
        if not isinstance(url, str) or not isinstance(fingerprint, str):
            continue
        key = (url, fingerprint)
        if key in seen:
            continue
        seen.add(key)
        merged.append(dict(record))
    return merged


def build_plan(current: dict[str, dict[str, object]], state: dict[str, object], bootstrap: bool) -> dict[str, object]:
    if bootstrap:
        return {"mode": "bootstrap", "entries": [], "urls": [], "removed": []}

    previous = published_pages(state)
    entries: dict[str, dict[str, object]] = {}

    def add(page: dict[str, object], kind: str, reason: str | None = None) -> None:
        entry = {
            "url": page["url"],
            "path": page["path"],
            "kind": kind,
            "indexable": page.get("indexable", False),
            "fingerprint": page.get("fingerprint", ""),
        }
        if page.get("file"):
            entry["file"] = page["file"]
        if reason:
            entry["reason"] = reason
        entries[str(page["url"])] = entry

    for path, page in current.items():
        old = previous.get(path)
        if old is None:
            if page.get("indexable"):
                add(page, "new")
            continue
        if page.get("fingerprint") != old.get("fingerprint") or page.get("indexable") != old.get("indexable"):
            add(page, "changed")

    for path, old in previous.items():
        if old.get("indexable") and path not in current:
            add({"path": path, "url": old["url"], "indexable": False, "fingerprint": old.get("fingerprint", "")}, "removed")

    for record in pending_records(state):
        url = str(record["url"])
        path = str(record.get("path", url.removeprefix(BASE_URL)))
        page = current.get(path)
        if page is not None:
            add(page, "pending", "retrying previously unaccepted notification")
        elif url in entries:
            continue
        else:
            entries[url] = dict(record)
            entries[url].setdefault("kind", "removed")
            entries[url].setdefault("path", path)

    ordered = sorted(entries.values(), key=lambda entry: str(entry["url"]))
    return {
        "mode": "delta",
        "entries": ordered,
        "urls": [entry["url"] for entry in ordered],
        "removed": [entry["url"] for entry in ordered if entry.get("kind") == "removed"],
    }


def build_manual_plan(current: dict[str, dict[str, object]], url: str) -> dict[str, object]:
    """Build a one-URL plan for an explicit operator-triggered submission."""
    validate_url(url)
    page = next((candidate for candidate in current.values() if candidate.get("url") == url), None)
    if page is None or page.get("indexable") is not True:
        raise ValueError("manual IndexNow URL must be a current indexable public page")
    entry: dict[str, object] = {
        "url": page["url"],
        "path": page["path"],
        "kind": "manual",
        "indexable": True,
        "fingerprint": page.get("fingerprint", ""),
    }
    if page.get("file"):
        entry["file"] = page["file"]
    return {"mode": "manual", "entries": [entry], "urls": [url], "removed": []}


def retry_after_seconds(headers: object) -> float | None:
    value = headers.get("Retry-After") if hasattr(headers, "get") else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            when = email.utils.parsedate_to_datetime(str(value))
            if when.tzinfo is None:
                when = when.replace(tzinfo=dt.timezone.utc)
            return max(0.0, (when - dt.datetime.now(dt.timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def probe_removed(url: str) -> tuple[int | None, str | None, str | None]:
    request = Request(url, headers={"Accept": "text/html", "User-Agent": "Terento-IndexNow/1"})
    try:
        with NO_REDIRECT_OPENER.open(request, timeout=REQUEST_TIMEOUT) as response:
            return int(response.status), response.headers.get("Location"), None
    except HTTPError as error:
        return int(error.code), error.headers.get("Location"), None
    except (OSError, URLError, TimeoutError) as error:
        return None, None, error.__class__.__name__


def post_indexnow(key: str, urls: list[str], *, sleep=time.sleep, clock=time.monotonic) -> tuple[int | None, str | None, int]:
    payload = json.dumps(
        {"host": HOST, "key": key, "keyLocation": f"{BASE_URL}/{key}.txt", "urlList": urls},
        separators=(",", ":"),
    ).encode("utf-8")
    started = clock()
    last_status: int | None = None
    last_error: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if clock() - started >= OVERALL_TIMEOUT:
            break
        request = Request(
            INDEXNOW_ENDPOINT,
            data=payload,
            method="POST",
            headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "Terento-IndexNow/1"},
        )
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                status = int(response.status)
                headers = response.headers
                response.read(4096)
        except HTTPError as error:
            status = int(error.code)
            headers = error.headers
            if getattr(error, "fp", None) is not None:
                try:
                    error.read(4096)
                except (AttributeError, KeyError, OSError):
                    pass
        except (OSError, URLError, TimeoutError) as error:
            status = None
            headers = {}
            last_error = error.__class__.__name__

        last_status = status
        if status in {200, 202}:
            return status, None, attempt
        if status is not None and status not in TRANSIENT_STATUSES:
            return status, last_error, attempt
        last_error = last_error or (f"HTTP {status}" if status is not None else "network error")
        if attempt == MAX_ATTEMPTS:
            break
        delay = retry_after_seconds(headers) if status is not None else None
        delay = delay if delay is not None else float(attempt * 2)
        remaining = OVERALL_TIMEOUT - (clock() - started)
        if remaining <= 0:
            break
        sleep(min(delay, remaining))
    return last_status, last_error, MAX_ATTEMPTS


def state_after_publication(
    current: dict[str, dict[str, object]],
    state: dict[str, object],
    bootstrap: bool,
    plan: dict[str, object],
    accepted: list[dict[str, object]],
    pending: list[dict[str, object]],
    *,
    published_commit: str | None,
    run_status: str,
    submission_at: str | None = None,
    successful_submission_at: str | None = None,
    submission_result: str | None = None,
    error_code: str | None = None,
) -> dict[str, object]:
    previous_index_now = state.get("indexNow") if isinstance(state.get("indexNow"), dict) else {}
    accepted_history = merge_accepted_records(state, accepted)
    last_submission_at = previous_index_now.get("lastSubmissionAt")
    last_successful_submission_at = previous_index_now.get("lastSuccessfulSubmissionAt")
    if submission_at:
        last_submission_at = submission_at
    if successful_submission_at:
        last_successful_submission_at = successful_submission_at
    last_result = previous_index_now.get("lastResult")
    last_error_code = previous_index_now.get("lastErrorCode")
    if submission_result:
        last_result = submission_result
        last_error_code = error_code
    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "published",
        "published": {
            "commit": published_commit,
            "pages": [page_snapshot(current[path]) for path in sorted(current)],
        },
        "indexNow": {
            "accepted": accepted_history,
            "pending": pending,
            "lastSubmissionAt": last_submission_at,
            "lastSuccessfulSubmissionAt": last_successful_submission_at,
            "lastResult": last_result,
            "lastErrorCode": last_error_code,
        },
        "lastRun": {
            "at": utc_now(),
            "status": run_status,
            "bootstrap": bootstrap,
            "planned": len(plan.get("entries", [])),
            "accepted": len(accepted),
            "pending": len(pending),
            "previousAccepted": len(previous_index_now.get("accepted", [])) if isinstance(previous_index_now, dict) else 0,
        },
    }


def _pending_since(entry: dict[str, object], fallback: str) -> dict[str, object]:
    retained = dict(entry)
    if not isinstance(retained.get("pendingSince"), str) or not retained["pendingSince"]:
        retained["pendingSince"] = fallback
    return retained


def _oldest_pending_at(records: list[dict[str, object]]) -> str | None:
    values = [
        str(record.get("pendingSince"))
        for record in records
        if isinstance(record.get("pendingSince"), str) and record.get("pendingSince")
    ]
    return min(values) if values else None


def _report_status(result: str, pending_count: int | None) -> str:
    if result in {"submitted", "no_changes"}:
        return "HEALTHY" if pending_count == 0 else "UNKNOWN"
    if result in {"validation_pending", "pending_retry", "partial_success"}:
        return "WARNING"
    if result in {"action_required", "live_verification_failed"}:
        return "FAILED"
    return "UNKNOWN"


def build_report(
    state: dict[str, object],
    plan: dict[str, object],
    *,
    result: str,
    publication_id: str,
    attempted_urls: list[str] | None = None,
    http_status: int | None = None,
    http_200_count: int = 0,
    http_202_count: int = 0,
    error_code: str | None = None,
) -> dict[str, object]:
    if result not in REPORT_RESULTS:
        raise ValueError("invalid IndexNow report result")
    index_now = state.get("indexNow") if isinstance(state.get("indexNow"), dict) else {}
    state_is_published = state.get("status") == "published" and isinstance(state.get("published"), dict)
    pending = pending_records(state)
    pending_count = len(pending) if state_is_published else None
    urls = sorted(set(attempted_urls or []))
    for url in urls:
        validate_url(url)
    preview = urls[:10]
    details: dict[str, object] = {
        "publication_id": publication_id,
        "result": result,
        "last_submission_at": index_now.get("lastSubmissionAt"),
        "last_successful_submission_at": index_now.get("lastSuccessfulSubmissionAt"),
        "attempted_url_count": len(urls),
        "http_200_count": http_200_count,
        "http_202_count": http_202_count,
        "http_status": http_status,
        "pending_url_count": pending_count,
        "oldest_pending_at": _oldest_pending_at(pending),
        "error_code": error_code,
        "error_summary": None,
        "url_preview": "\n".join(preview) if preview else None,
        "url_preview_count": len(preview),
        "url_preview_total": len(urls),
    }
    error_summaries = {
        "missing_configuration": "IndexNow configuration is missing.",
        "key_verification_failed": "The public IndexNow key check failed.",
        "live_verification_failed": "Live public-site verification failed before notification.",
        "validation_pending": "IndexNow validation is still pending.",
        "pending_retry": "IndexNow is temporarily unavailable; pending URLs will be retried.",
        "http_400": "IndexNow returned a permanent request error.",
        "http_403": "IndexNow returned a permanent request error.",
        "http_422": "IndexNow returned a permanent request error.",
        "http_429": "IndexNow is temporarily unavailable; pending URLs will be retried.",
        "http_5xx": "IndexNow is temporarily unavailable; pending URLs will be retried.",
        "network_timeout": "IndexNow is temporarily unavailable; pending URLs will be retried.",
        "report_delivery_failed": "The operational report could not be delivered after retries.",
    }
    safe_error_code = error_code if isinstance(error_code, str) and error_code in error_summaries else None
    details["error_code"] = safe_error_code
    details["error_summary"] = error_summaries.get(safe_error_code)
    previous_result = index_now.get("lastResult")
    if not isinstance(previous_result, str):
        previous_result = None
    previous_error_code = index_now.get("lastErrorCode")
    if not isinstance(previous_error_code, str) or previous_error_code not in error_summaries:
        previous_error_code = None
    if result == "no_changes" and previous_result in {
        "validation_pending", "pending_retry", "partial_success", "action_required",
    }:
        details["error_code"] = safe_error_code or previous_error_code or (
            "validation_pending" if previous_result == "validation_pending" else "pending_retry"
        )
        details["error_summary"] = error_summaries.get(details["error_code"])
        if previous_result == "action_required":
            overall_status = "FAILED"
        else:
            overall_status = "WARNING"
    else:
        overall_status = _report_status(result, pending_count)
    return {
        "schemaVersion": 1,
        "status": overall_status,
        "summary": REPORT_SUMMARIES[result],
        "details": details,
        "planned_url_count": len(plan.get("entries", [])),
    }


def write_report(path: Path | None, report: dict[str, object]) -> None:
    if path is not None:
        atomic_write_json(path, report)


def run(args: argparse.Namespace) -> int:
    current = current_pages_from_manifest(args.current_manifest)
    state, bootstrap = load_state(args.state)
    manual_url = getattr(args, "manual_url", None)
    if manual_url:
        if args.mode != "send":
            raise ValueError("--manual-url requires --send")
        plan = build_manual_plan(current, manual_url)
        bootstrap = False
    else:
        plan = build_plan(current, state, bootstrap)
    if args.plan_out:
        atomic_write_json(args.plan_out, plan)

    entries = [dict(entry) for entry in plan["entries"]]
    report_out = getattr(args, "report_out", None)
    publication_id = getattr(args, "publication_id", None) or "unassigned-publication"
    report_result = getattr(args, "report_result", None)
    report_error_code = getattr(args, "error_code", None)
    if args.mode == "report-only":
        result = report_result or "not_initialized"
        write_report(
            report_out,
            build_report(
                state, plan, result=result, publication_id=publication_id,
                error_code=report_error_code,
            ),
        )
        print(f"IndexNow report prepared: {result}; no IndexNow request was made.")
        return 0
    if args.mode == "dry-run":
        print(f"IndexNow dry-run: {len(entries)} URL(s) planned; no network request or state change.")
        if plan["mode"] == "bootstrap":
            print("IndexNow state is bootstrap; the first confirmed publication will establish a baseline without bulk submission.")
        return 0

    accepted: list[dict[str, object]] = []
    pending: list[dict[str, object]] = pending_records(state) if manual_url else []
    eligible: list[str] = []
    submission_at: str | None = None
    successful_submission_at: str | None = None
    if bootstrap:
        new_state = state_after_publication(
            current, state, True, plan, [], [], published_commit=args.published_commit,
            run_status="bootstrap", submission_result="bootstrap",
        )
        atomic_write_json(args.state, new_state)
        write_report(
            report_out,
            build_report(new_state, plan, result="bootstrap", publication_id=publication_id),
        )
        print("IndexNow baseline recorded; no URLs were submitted for the first confirmed publication.")
        return 0

    for entry in entries:
        if entry.get("kind") != "removed":
            eligible.append(str(entry["url"]))
            continue
        if args.mode == "record":
            entry["reason"] = "removed URL requires a live 404, 410 or redirect check"
            pending.append(entry)
            continue
        status, location, probe_error = probe_removed(str(entry["url"]))
        if status == 404 or status == 410 or (status is not None and 300 <= status < 400 and location):
            eligible.append(str(entry["url"]))
        else:
            if status == 200:
                entry["reason"] = "live URL still returns 200; removal not confirmed"
            elif probe_error:
                entry["reason"] = "live removal check was unavailable; retry required"
            else:
                entry["reason"] = f"live removal check returned HTTP {status}"
            pending.append(entry)

    pending = [_pending_since(entry, utc_now()) for entry in pending]

    if len(eligible) > MAX_URLS:
        raise ValueError(f"IndexNow URL batch exceeds the {MAX_URLS}-URL limit")

    if args.mode == "record":
        pending.extend(_pending_since(entry, utc_now()) for entry in entries if entry.get("kind") != "removed")
        status_text = "pending-indexnow" if pending else "published-no-notifications"
        result = report_result or ("pending_retry" if pending else "no_changes")
        new_state = state_after_publication(
            current, state, False, plan, [], pending,
            published_commit=args.published_commit, run_status=status_text,
            submission_result=result, error_code=report_error_code,
        )
        atomic_write_json(args.state, new_state)
        write_report(
            report_out,
            build_report(
                new_state, plan, result=result, publication_id=publication_id,
                error_code=report_error_code,
            ),
        )
        print(f"IndexNow not sent: {len(pending)} URL(s) retained for a later configured submission.")
        return 0

    if not eligible:
        result = "pending_retry" if pending else "no_changes"
        new_state = state_after_publication(
            current, state, False, plan, [], pending,
            published_commit=args.published_commit, run_status="no-eligible-notifications",
            submission_result=result,
        )
        atomic_write_json(args.state, new_state)
        write_report(
            report_out,
            build_report(new_state, plan, result=result, publication_id=publication_id),
        )
        print(f"IndexNow: no eligible URL(s) to submit; {len(pending)} URL(s) remain pending.")
        return 0 if not pending else 1

    attempted_urls = sorted(set(eligible))
    submission_at = utc_now()
    status, error, attempts = post_indexnow(args.key, attempted_urls)
    if status in {200, 202}:
        entries_by_url = {str(entry["url"]): entry for entry in entries}
        accepted = [
            {
                "url": url,
                "fingerprint": entries_by_url[url].get("fingerprint", ""),
                "status": status,
                "acceptedAt": utc_now(),
            }
            for url in attempted_urls
        ]
        successful_submission_at = submission_at if status == 200 else None
        run_status = "accepted"
        exit_code = 0
    else:
        retained_pending = {
            (str(entry.get("url")), str(entry.get("fingerprint", ""))): entry
            for entry in pending
        }
        for entry in entries:
            if entry.get("kind") != "removed" or str(entry["url"]) in eligible:
                key = (str(entry["url"]), str(entry.get("fingerprint", "")))
                retained_pending[key] = _pending_since(entry, submission_at)
        pending = list(retained_pending.values())
        run_status = "failed"
        exit_code = 1

    if status == 200:
        result = "submitted"
        error_code = None
    elif status == 202:
        result = "validation_pending"
        error_code = None
    elif status in {400, 403, 422}:
        result = "action_required"
        error_code = f"http_{status}"
    elif status == 429:
        result = "pending_retry"
        error_code = "http_429"
    elif status is None:
        result = "pending_retry"
        error_code = "network_timeout"
    else:
        result = "pending_retry"
        error_code = "http_5xx" if status >= 500 else "pending_retry"

    new_state = state_after_publication(
        current, state, False, plan, accepted, pending,
        published_commit=args.published_commit, run_status=run_status,
        submission_at=submission_at,
        successful_submission_at=successful_submission_at,
        submission_result=result, error_code=error_code,
    )
    atomic_write_json(args.state, new_state)
    write_report(
        report_out,
        build_report(
            new_state, plan, result=result, publication_id=publication_id,
            attempted_urls=attempted_urls,
            http_status=status,
            http_200_count=len(accepted) if status == 200 else 0,
            http_202_count=len(accepted) if status == 202 else 0,
            error_code=error_code,
        ),
    )
    if status in {200, 202}:
        print(f"IndexNow submission accepted with HTTP {status} for {len(accepted)} URL(s) after {attempts} attempt(s); this does not mean the pages are indexed.")
    else:
        detail = f"HTTP {status}" if status is not None else "network failure"
        print(f"IndexNow submission not accepted ({detail}); {len(pending)} URL(s) retained for retry after {attempts} attempt(s).", file=sys.stderr)
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", dest="mode", action="store_const", const="dry-run")
    mode.add_argument("--record-published", dest="mode", action="store_const", const="record")
    mode.add_argument("--send", dest="mode", action="store_const", const="send")
    mode.add_argument("--report-only", dest="mode", action="store_const", const="report-only")
    parser.add_argument("--current-manifest", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--plan-out", type=Path)
    parser.add_argument("--published-commit")
    parser.add_argument("--key-env", default="TERENTO_INDEXNOW_KEY")
    parser.add_argument("--report-out", type=Path)
    parser.add_argument("--publication-id")
    parser.add_argument("--report-result", choices=sorted(REPORT_RESULTS))
    parser.add_argument("--error-code")
    parser.add_argument("--manual-url", help="explicitly submit one current indexable public URL")
    args = parser.parse_args()
    for attribute in ("current_manifest", "state", "plan_out"):
        path = getattr(args, attribute)
        if path is not None and not path.is_absolute():
            setattr(args, attribute, ROOT / path)

    if args.mode == "send":
        key = os.environ.get(args.key_env, "")
        if not KEY_RE.fullmatch(key):
            print("IndexNow send refused: configured key is missing or does not match the required 32-hex format.", file=sys.stderr)
            return 2
        args.key = key
    else:
        args.key = ""

    try:
        return run(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"IndexNow preparation failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
