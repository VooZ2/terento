#!/usr/bin/env python3
"""Generate Markdown content-negotiation representations from public HTML."""

from __future__ import annotations

import argparse
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "site/metadata.json"
IGNORED = {"button", "canvas", "form", "iframe", "nav", "noscript", "script", "select", "style", "svg", "template"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BLOCKS = {
    "article", "blockquote", "dd", "details", "div", "dl", "dt", "figcaption", "figure",
    "h1", "h2", "h3", "h4", "h5", "h6", "li", "main", "ol", "p", "section", "summary",
    "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
}


class MarkdownRenderer(HTMLParser):
    def __init__(self, canonical: str):
        super().__init__(convert_charrefs=True)
        self.canonical = canonical
        self.parts: list[str] = []
        self.links: list[tuple[str, list[str]]] = []
        self.lists: list[tuple[str, int]] = []
        self.ignored: list[bool] = []
        self.main_depth = 0
        self.seen_main = False
        self.fenced_code = 0

    def emit(self, value: str) -> None:
        if not value:
            return
        (self.links[-1][1] if self.links else self.parts).append(value)

    def line_break(self, count: int = 1) -> None:
        destination = self.links[-1][1] if self.links else self.parts
        current = "".join(destination)
        needed = max(0, count - (len(current) - len(current.rstrip("\n"))))
        if needed:
            destination.append("\n" * needed)

    def in_main(self) -> bool:
        return self.main_depth > 0

    def has_pending_list_marker(self) -> bool:
        destination = self.links[-1][1] if self.links else self.parts
        line = "".join(destination).split("\n")[-1].strip()
        return re.fullmatch(r"(?:[-*+]|\d+\.)", line) is not None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs)
        parent_ignored = bool(self.ignored and self.ignored[-1])
        hidden_style = re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", attrs.get("style") or "", re.I)
        hidden = "hidden" in attrs or (attrs.get("aria-hidden") or "").lower() == "true" or bool(hidden_style)
        ignored = parent_ignored or hidden or tag in IGNORED
        if tag not in VOID:
            self.ignored.append(ignored)
        if tag == "main" and not parent_ignored:
            self.main_depth += 1
            self.seen_main = True
        if ignored or not self.in_main():
            return

        if tag in BLOCKS:
            pending_list_marker = self.has_pending_list_marker()
            in_list_heading = tag.startswith("h") and bool(self.lists)
            if not in_list_heading and not pending_list_marker:
                self.line_break(2 if tag.startswith("h") or tag in {"p", "section", "article", "figure", "details", "blockquote"} else 1)
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            if not self.lists:
                self.emit("#" * int(tag[1]) + " ")
        elif tag == "a":
            href = attrs.get("href")
            destination = self.links[-1][1] if self.links else self.parts
            current = "".join(destination)
            if current and not current[-1].isspace():
                destination.append(" ")
            self.links.append((urljoin(self.canonical, href) if href else "", []))
        elif tag in {"strong", "b"}:
            self.emit("**")
        elif tag in {"em", "i"}:
            self.emit("*")
        elif tag == "code" and self.fenced_code == 0:
            self.emit("`")
        elif tag == "pre":
            self.line_break(2)
            self.emit("```\n")
            self.fenced_code += 1
        elif tag in {"ul", "ol"}:
            self.lists.append((tag, 0))
        elif tag == "li":
            self.line_break(1)
            indent = "  " * max(0, len(self.lists) - 1)
            if self.lists and self.lists[-1][0] == "ol":
                kind, number = self.lists[-1]
                number += 1
                self.lists[-1] = (kind, number)
                self.emit(f"{indent}{number}. ")
            else:
                self.emit(f"{indent}- ")
        elif tag == "br":
            self.line_break()
        elif tag == "hr":
            self.line_break(2)
            self.emit("---\n")
        elif tag == "img" and attrs.get("alt"):
            self.emit(html.unescape(attrs["alt"] or ""))
        elif tag in {"td", "th"}:
            self.emit(" | ")

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            return
        ignored = self.ignored.pop() if self.ignored else False
        if tag == "main" and not ignored and self.main_depth:
            self.main_depth -= 1
        if ignored or not self.in_main():
            return
        if tag == "a" and self.links:
            href, chunks = self.links.pop()
            label = re.sub(r"\s+", " ", "".join(chunks)).strip()
            self.emit(f"[{label}]({href})" if label and href else label)
        elif tag in {"strong", "b"}:
            self.emit("**")
        elif tag in {"em", "i"}:
            self.emit("*")
        elif tag == "code" and self.fenced_code == 0:
            self.emit("`")
        elif tag == "pre" and self.fenced_code:
            self.fenced_code -= 1
            self.line_break()
            self.emit("```\n")
        elif tag in {"ul", "ol"} and self.lists:
            self.lists.pop()
        elif tag in BLOCKS:
            in_list_heading = tag.startswith("h") and bool(self.lists)
            if not in_list_heading:
                self.line_break(2 if tag.startswith("h") or tag in {"p", "section", "article", "figure", "details", "blockquote"} else 1)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self.in_main() and not any(self.ignored):
            self.emit(data if self.fenced_code else re.sub(r"\s+", " ", data))


def clean_markdown(value: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def render_page(page: dict[str, str]) -> str:
    source = (ROOT / page["file"]).read_text(encoding="utf-8")
    renderer = MarkdownRenderer("https://terento.app" + page["path"])
    renderer.feed(source)
    body = clean_markdown("".join(renderer.parts))
    if not renderer.seen_main or len(body.strip()) < 100:
        raise ValueError(f"No substantial <main> content found for {page['path']}")
    title = json.dumps(page["title"], ensure_ascii=False)
    return f"---\ntitle: {title}\ncanonical: https://terento.app{page['path']}\n---\n\n{body}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write generated Markdown beside each page")
    mode.add_argument("--check", action="store_true", help="check committed Markdown output parity")
    parser.add_argument("--page", action="append", help="limit output to an exact public route; repeat for multiple pages")
    args = parser.parse_args()
    pages = json.loads(METADATA.read_text(encoding="utf-8"))["pages"]
    if args.page:
        unknown = set(args.page) - {page["path"] for page in pages}
        if unknown:
            parser.error(f"Unknown public routes: {sorted(unknown)}")
        pages = [page for page in pages if page["path"] in args.page]
    failed = []
    for page in pages:
        destination = (ROOT / page["file"]).with_name("index.md")
        expected = render_page(page)
        if args.write:
            destination.write_text(expected, encoding="utf-8")
        elif not destination.is_file() or destination.read_text(encoding="utf-8") != expected:
            failed.append(str(destination.relative_to(ROOT)))
    if failed:
        raise SystemExit("Markdown representation parity failed: " + ", ".join(failed))
    print(f"Markdown representations {'written' if args.write else 'match'} for {len(pages)} pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
