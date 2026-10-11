#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path
from typing import Any


def build_message(
    report: dict[str, Any], sender: str, recipient: str, context: dict[str, Any] | None = None,
) -> EmailMessage:
    status = str(report.get("status") or "UNKNOWN").title()
    details = report.get("details") if isinstance(report.get("details"), dict) else {}
    lines = [
        f"Terento weekly project health: {status}",
        "",
        str(report.get("summary") or "No summary was supplied."),
        "",
        f"Release: {report.get('releaseVersion') or '—'}",
        f"Build: {report.get('buildNumber') or '—'}",
        f"Commit: {str(report.get('commitSha') or '—')[:12]}",
        f"Observed: {report.get('observedAt') or '—'}",
        "",
        "Quality gates:",
    ]
    suite_labels = {
        "selection": "Test-suite selection",
        "site": "Public website",
        "backend": "Backend / API",
        "app": "macOS application",
        "native": "Native device safety",
        "release": "Release contracts",
        "shared_ci": "Shared / CI contracts",
        "live_catalog": "Live catalog contract",
    }
    lines.extend(
        f"- {suite_labels[name]}: {details[name]}"
        for name in suite_labels if name in details
    )
    lines.extend(("", "Provider catalogs:"))
    providers = [p for p in (context or {}).get("providers") or [] if isinstance(p, dict)]
    if not providers:
        lines.append("- Catalog report context was unavailable.")
    for provider in providers:
        lines.extend((
            f"- {provider.get('name') or provider.get('id') or 'Provider'}: {provider.get('status') or 'UNKNOWN'}",
            f"  Latest release: {provider.get('latestRelease') or '—'}",
            f"  Last successful collection: {provider.get('lastCollectionSuccess') or '—'}",
            f"  Last detected release change: {provider.get('latestReleaseDetectedAt') or '—'}",
            f"  New release detected in the last 7 days: {'yes' if provider.get('newReleaseDetectedInLast7Days') is True else 'no'}",
            f"  Reason: {provider.get('reason') or 'No catalog context was supplied.'}",
        ))
    lines.extend(("", f"GitHub Actions: {report.get('sourceRunUrl') or '—'}", "", "The same report is retained in Terento /admin/system-health."))
    message = EmailMessage()
    message["Subject"] = f"[Terento] Weekly project health: {status}"
    message["From"] = sender
    message["To"] = recipient
    message.set_content("\n".join(lines))
    return message


def send(report_path: Path, context_path: Path) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    context = json.loads(context_path.read_text(encoding="utf-8"))
    host = os.environ.get("SMTP_HOST", "mail-eu.smtp2go.com").strip()
    port = int(os.environ.get("SMTP_PORT", "2525"))
    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    sender = os.environ.get("REPORT_FROM", "report@terento.app").strip()
    recipient = os.environ.get("REPORT_TO", "report@terento.app").strip()
    if not username or not password or not sender or not recipient:
        raise RuntimeError("SMTP_USERNAME, SMTP_PASSWORD, REPORT_FROM, and REPORT_TO are required")
    message = build_message(report, sender, recipient, context)
    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=20) as client:
        client.ehlo()
        client.starttls(context=context)
        client.ehlo()
        client.login(username, password)
        client.send_message(message)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: send-weekly-health-report.py REPORT.json REPORT-CONTEXT.json")
    send(Path(sys.argv[1]), Path(sys.argv[2]))


if __name__ == "__main__":
    main()
