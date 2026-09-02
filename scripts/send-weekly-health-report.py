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


def build_message(report: dict[str, Any], sender: str, recipient: str) -> EmailMessage:
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
        "Test suites:",
    ]
    lines.extend(f"- {name.replace('_', ' ').title()}: {value}" for name, value in sorted(details.items()))
    lines.extend(("", f"GitHub Actions: {report.get('sourceRunUrl') or '—'}", "", "The same report is retained in Terento /admin/system-health."))
    message = EmailMessage()
    message["Subject"] = f"[Terento] Weekly project health: {status}"
    message["From"] = sender
    message["To"] = recipient
    message.set_content("\n".join(lines))
    return message


def send(report_path: Path) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    host = os.environ.get("SMTP_HOST", "mail-eu.smtp2go.com").strip()
    port = int(os.environ.get("SMTP_PORT", "2525"))
    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    sender = os.environ.get("REPORT_FROM", "report@terento.app").strip()
    recipient = os.environ.get("REPORT_TO", "report@terento.app").strip()
    if not username or not password or not sender or not recipient:
        raise RuntimeError("SMTP_USERNAME, SMTP_PASSWORD, REPORT_FROM, and REPORT_TO are required")
    message = build_message(report, sender, recipient)
    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=20) as client:
        client.ehlo()
        client.starttls(context=context)
        client.ehlo()
        client.login(username, password)
        client.send_message(message)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: send-weekly-health-report.py REPORT.json")
    send(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
