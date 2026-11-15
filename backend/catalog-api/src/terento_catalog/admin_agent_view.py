"""Read-only text view of Admin GET pages for the operator agent.

``GET /internal/attention?page=/admin/...`` renders the page with the same
Admin code a signed-in owner gets (same populations, periods and
deduplication), then turns the HTML into plain text so an agent reads exactly
what Admin shows. Form fields, scripts, styles and hidden markup are
dropped; every text line passes through the issue-report sanitiser. Nothing
here changes data, and the CSRF token given to the renderer is empty, so no
rendered form could ever be submitted.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

from .admin import _sanitised_issue_value
from .admin_attention import _sanitised

SCHEMA_VERSION = 1
MAX_PAGE_LENGTH = 512
MAX_TEXT_CHARACTERS = 1_500_000
MAX_LINKS = 400
# Admin GETs that are not owner-readable pages: sign-in/account forms and the
# CSV download. Static assets are refused by extension.
_DENIED_PATHS = frozenset({"/admin/login", "/admin/setup", "/admin/logout", "/admin/account"})
_DENIED_PREFIXES = ("/admin/map-assets/",)
# The synthetic renderer session; it never matches a stored session.
AGENT_SESSION: dict[str, Any] = {"id": None, "username": "", "agent_read": True}

# Button labels stay (sortable table headers are buttons); form values and
# option lists do not.
_SKIPPED = frozenset({"script", "style", "template", "select", "option", "head", "noscript", "textarea"})
_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"})
_BLOCK = frozenset({
    "p", "div", "section", "article", "header", "footer", "main", "aside", "nav", "ul", "ol", "dl",
    "dt", "dd", "table", "thead", "tbody", "tfoot", "tr", "details", "summary", "figure",
    "figcaption", "form", "fieldset", "legend", "label", "blockquote", "pre", "caption",
})


def agent_page(raw: str) -> str | None:
    """The validated Admin path (with query) an agent may read, else None."""
    page = str(raw or "").strip()
    if not page or len(page) > MAX_PAGE_LENGTH or re.search(r"[\x00-\x20\x7f\\]", page):
        return None
    parts = urlsplit(page)
    path = parts.path
    if parts.scheme or parts.netloc or parts.fragment or "//" in path or "/." in path:
        return None
    if not (path == "/admin" or path.startswith("/admin/")):
        return None
    normalised = path.rstrip("/") or "/admin"
    if normalised in _DENIED_PATHS or path.startswith(_DENIED_PREFIXES):
        return None
    last = normalised.rsplit("/", 1)[-1]
    if "." in last and not last.endswith(".json"):
        return None
    return path + (f"?{parts.query}" if parts.query else "")


def _admin_link(href: str) -> str | None:
    href = href.strip()
    if not href.startswith("/admin") or href.startswith("//"):
        return None
    href = href.split("#", 1)[0]
    return href if agent_page(href) else None


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.links: list[str] = []
        self.chunks: list[str] = []
        self._stack: list[tuple[str, bool]] = []  # (tag, text suppressed here)
        self._in_title = False
        self._title_done = False
        self._chart_svgs = 0  # open chart SVGs whose <title> tooltips carry values
        self._chart_title: list[str] | None = None
        self._cell_in_row = 0
        self._chart_lines: set[str] = set()

    @property
    def _suppressed(self) -> bool:
        return bool(self._stack and self._stack[-1][1])

    def _link(self, href: str | None) -> None:
        link = _admin_link(href or "")
        if link and link not in self.links and len(self.links) < MAX_LINKS:
            self.links.append(link)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        names = {name for name, _ in attrs}
        if tag == "title":
            if self._chart_svgs:
                self._chart_title = []
            elif not self._title_done:
                self._in_title = True
        if tag == "a":
            self._link(values.get("href"))
        if tag == "form" and values.get("action", "").startswith("/admin") and \
                values.get("method", "get").lower() == "get":
            self._link(values.get("action"))
        parent_suppressed = self._suppressed
        if not parent_suppressed and "data-chart-values" in values:
            self._chart(values["data-chart-values"])
        classes = values.get("class", "").split()
        # The top bar (menu, time zone, account) repeats on every page; its links are kept.
        chrome = (tag == "header" and "admin-topbar" in classes) or "admin-skip-link" in classes
        suppressed = parent_suppressed or tag in _SKIPPED or tag == "svg" or "hidden" in names \
            or values.get("aria-hidden") == "true" or tag == "input" or chrome
        if tag == "svg" and not parent_suppressed and values.get("aria-hidden") != "true" and \
                values.get("role") in {"img", "group"}:
            self._chart_svgs += 1
            self._stack.append(("svg:chart", True))
            if values.get("aria-label"):
                self.chunks.append(f"\n[chart] {values['aria-label']}\n")
            return
        if tag in _VOID:
            if tag == "br" and not suppressed:
                self.chunks.append("\n")
            return
        self._stack.append((tag, suppressed))
        if suppressed:
            return
        if re.fullmatch(r"h[1-6]", tag):
            self.chunks.append("\n" + "#" * int(tag[1]) + " ")
        elif tag == "li":
            self.chunks.append("\n- ")
        elif tag == "tr":
            self._cell_in_row = 0
            self.chunks.append("\n")
        elif tag in {"td", "th"}:
            if self._cell_in_row:
                self.chunks.append(" | ")
            self._cell_in_row += 1
        elif tag in _BLOCK:
            self.chunks.append("\n")
        else:
            # A metric label and its value are adjacent inline elements.
            self.chunks.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            if self._chart_title is not None:
                self._chart_line("[chart value] " + " ".join("".join(self._chart_title).split()))
                self._chart_title = None
            elif self._in_title:
                self._in_title, self._title_done = False, True
        if tag in _VOID or not any(open_tag.split(":")[0] == tag for open_tag, _ in self._stack):
            return
        while self._stack:
            open_tag, _ = self._stack.pop()
            if open_tag == "svg:chart":
                self._chart_svgs -= 1
            if open_tag.split(":")[0] == tag:
                break
        if not self._suppressed and (tag in _BLOCK or re.fullmatch(r"h[1-6]|li", tag)):
            self.chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._chart_title is not None:
            self._chart_title.append(data)
            return
        if self._in_title:
            self.title += data
            return
        if not self._suppressed:
            self.chunks.append(data)

    def _chart(self, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except ValueError:
            return
        if not isinstance(payload, dict):
            return
        series = "; ".join(
            f"{item[1]} {item[2] if item[2] is not None else '—'}"
            for item in payload.get("values") or [] if isinstance(item, list) and len(item) >= 3
        )
        total = payload.get("total")
        self._chart_line(f"[chart value] {payload.get('date') or ''}: {series}"
                         + (f"; total {total}" if total is not None else ""))

    def _chart_line(self, line: str) -> None:
        # Desktop and phone variants of one chart repeat the same values.
        if line.strip() != "[chart value]" and line not in self._chart_lines:
            self._chart_lines.add(line)
            self.chunks.append(f"\n{line}\n")


def html_text(markup: str) -> dict[str, Any]:
    """Plain sanitised text of one Admin HTML document or fragment, plus its Admin links."""
    parser = _TextExtractor()
    parser.feed(markup)
    parser.close()
    lines: list[str] = []
    for raw_line in "".join(parser.chunks).split("\n"):
        # Plain text, never markup: keep "<20" readable instead of redacted.
        line = _sanitised_issue_value(raw_line.replace("<", "‹").replace(">", "›"))
        if line and line not in {"|", "-"} and (not lines or lines[-1] != line):
            lines.append(line)
    text = "\n".join(lines)
    truncated = len(text) > MAX_TEXT_CHARACTERS
    return {
        "title": _sanitised_issue_value(parser.title) or None,
        "text": text[:MAX_TEXT_CHARACTERS],
        "truncated": truncated,
        "links": parser.links,
    }


def _json_view(value: Any) -> Any:
    """Admin JSON with any rendered ``html`` fragment turned into text."""
    if isinstance(value, dict):
        converted: dict[str, Any] = {}
        for key, item in value.items():
            if key == "html" and isinstance(item, str):
                view = html_text(item)
                converted["text"] = view["text"]
                converted["links"] = view["links"]
            else:
                converted[key] = _json_view(item)
        return converted
    if isinstance(value, list):
        return [_json_view(item) for item in value]
    return value


def page_view(page: str, captured: dict[str, Any]) -> dict[str, Any]:
    """The response document for one captured Admin response."""
    document: dict[str, Any] = {"schemaVersion": SCHEMA_VERSION, "page": page, "status": int(captured["status"])}
    kind = captured["kind"]
    if kind == "html":
        document.update(html_text(captured["body"].decode("utf-8", "replace")))
    elif kind == "json":
        document["json"] = _sanitised(_json_view(captured["document"]))
    elif kind == "redirect":
        location = _admin_link(captured["location"])
        document["redirect"] = location
    return document
