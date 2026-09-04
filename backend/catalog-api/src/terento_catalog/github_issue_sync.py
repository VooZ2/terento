"""Bounded, read-only GitHub polling; only the local review lifecycle changes."""
from __future__ import annotations

import json
import logging
from threading import Event
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

LOGGER = logging.getLogger(__name__)
INTERVAL_SECONDS = 900
MAX_ISSUES = 10  # At most 40 unauthenticated requests/hour from one worker.
REPOSITORY = "https://api.github.com/repos/VooZ2/terento/issues/"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_issue(number: int) -> dict:
    request = Request(REPOSITORY + str(number), headers={
        "Accept": "application/vnd.github+json", "User-Agent": "Terento-admin-issue-sync",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with build_opener(NoRedirect()).open(request, timeout=10) as response:
        body = response.read(262145)
    if len(body) > 262144:
        raise ValueError("GitHub response exceeds limit")
    document = json.loads(body)
    if (not isinstance(document, dict) or document.get("number") != number
            or document.get("state") not in {"open", "closed"}
            or "pull_request" in document
            or document.get("html_url") != f"https://github.com/VooZ2/terento/issues/{number}"):
        raise ValueError("Unexpected GitHub issue response")
    # Do not retain issue bodies, names, or any other GitHub metadata.
    return {"state": document["state"], "state_reason": document.get("state_reason")}


def apply_closed_issue(connection, number: int, reason: str | None) -> int:
    """Lock and recheck exact links; audit only rows whose lifecycle changes.

    Concurrent relinking serializes on the evidence rows. A mixed/conflicting
    operation is left for manual review, never resolved by a partial match.
    """
    reference = f"#{number}"
    rows = connection.execute("""
        SELECT event_id, diagnostic_status, linked_github_issue,
               COALESCE(operation_id::text, 'legacy:' || event_id::text) AS operation_key
        FROM compatibility_evidence_event
        WHERE COALESCE(operation_id::text, 'legacy:' || event_id::text) IN (
            SELECT COALESCE(operation_id::text, 'legacy:' || event_id::text)
            FROM compatibility_evidence_event WHERE linked_github_issue = %s
        ) ORDER BY event_id FOR UPDATE
    """, (reference,)).fetchall()
    groups = {}
    for row in rows:
        groups.setdefault(row["operation_key"], []).append(row)
    code = "FIXED" if reason == "completed" else "OTHER"
    note = f"GitHub issue #{number} closed ({reason if reason in {'completed', 'not_planned'} else 'unspecified'}); synchronized automatically."
    changed = 0
    for group in groups.values():
        if any(row["linked_github_issue"] != reference for row in group):
            continue
        for row in group:
            if row["diagnostic_status"] != "ACTIVE":
                continue
            connection.execute("""
                UPDATE compatibility_evidence_event
                SET diagnostic_status = 'RESOLVED', resolution_code = %s,
                    resolution_reason = %s, resolution_note = %s,
                    resolved_at = now(), resolved_by = NULL
                WHERE event_id = %s
            """, (code, code, note, row["event_id"]))
            connection.execute("""
                INSERT INTO compatibility_diagnostic_lifecycle_audit
                    (event_id, previous_status, new_status, resolution_reason,
                     resolution_note, linked_github_issue, changed_by)
                VALUES (%s, 'ACTIVE', 'RESOLVED', %s, %s, %s, NULL)
            """, (row["event_id"], code, note, reference))
            changed += 1
    return changed


def sync_once(database, *, fetch=fetch_issue) -> int:
    changed = 0
    with database.connection() as connection:
        # Transaction lock also prevents concurrent API processes polling twice.
        if not connection.execute("SELECT pg_try_advisory_xact_lock(734820194) AS acquired").fetchone()["acquired"]:
            return 0
        targets = connection.execute("""
            SELECT DISTINCT substring(e.linked_github_issue from 2)::bigint AS issue_number,
                            s.checked_at
            FROM compatibility_evidence_event e
            LEFT JOIN admin_github_issue_sync s
                ON e.linked_github_issue = '#' || s.issue_number::text
            WHERE e.diagnostic_status = 'ACTIVE'
              AND e.linked_github_issue ~ '^#[1-9][0-9]{0,9}$'
              AND (s.checked_at IS NULL OR s.checked_at < now() - interval '15 minutes')
            ORDER BY s.checked_at ASC NULLS FIRST, issue_number
            LIMIT %s
        """, (MAX_ISSUES,)).fetchall()
        for target in targets:
            number = int(target["issue_number"])
            state, error, stop = None, None, False
            try:
                issue = fetch(number)
                state = issue["state"]
                if state == "closed":
                    changed += apply_closed_issue(connection, number, issue.get("state_reason"))
            except HTTPError as exc:
                error = f"GitHub HTTP {exc.code}"
                stop = exc.code in {403, 429}
            except (ValueError, OSError, KeyError):
                error = "GitHub state could not be verified"
            connection.execute("""
                INSERT INTO admin_github_issue_sync (issue_number, state, error)
                VALUES (%s, %s, %s)
                ON CONFLICT (issue_number) DO UPDATE SET
                    state = COALESCE(EXCLUDED.state, admin_github_issue_sync.state),
                    checked_at = now(), error = EXCLUDED.error
            """, (number, state, error))
            if stop:
                break
    return changed


def sync_health(connection) -> dict:
    row = connection.execute("""
        SELECT count(DISTINCT e.linked_github_issue) AS linked,
            count(DISTINCT e.linked_github_issue) FILTER (
                WHERE e.diagnostic_status = 'ACTIVE' AND
                    (s.checked_at IS NULL OR s.checked_at < now() - interval '30 minutes')
            ) AS overdue,
            count(DISTINCT e.linked_github_issue) FILTER (
                WHERE e.diagnostic_status = 'ACTIVE' AND s.error IS NOT NULL
            ) AS errors,
            max(s.checked_at) AS checked_at
        FROM compatibility_evidence_event e
        LEFT JOIN admin_github_issue_sync s ON e.linked_github_issue = '#' || s.issue_number::text
        WHERE e.linked_github_issue IS NOT NULL
    """).fetchone() or {}
    return dict(row)


def run_sync(database, stop: Event) -> None:
    while not stop.is_set():
        try:
            sync_once(database)
        except Exception:
            LOGGER.exception("GitHub issue synchronization failed; next cycle will retry")
        stop.wait(INTERVAL_SECONDS)
