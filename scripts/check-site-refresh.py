#!/usr/bin/env python3
"""Compare the SEO-relevant facts of the public site pages before and after a change.

For every page and locale it compares, between a git base ref and the working
tree: <title>, H1, meta description, canonical, the hreflang set, robots, the
ordered H2 list, the JSON-LD types, the FAQPage questions against the visible
FAQ, the Umami event names with their locations, and the visible word count.

Usage:
  python3 scripts/check-site-refresh.py [--base origin/main] [--expect FILE] [paths...]

Without paths it checks every site/**/index.html present on either side.
--expect points to a JSON file {"<path>": {"<field>": <expected after value>}}
for intended changes (for example a copy fix that changes an H2). The extra
field "events_removed" lists Umami "event @ location" pairs a page may drop.
Exit code 1 when an SEO field or an Umami event changed unexpectedly, or when
a FAQPage does not match its visible questions. Word counts are informational.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEO_FIELDS = ("title", "h1", "description", "canonical", "hreflang", "robots", "h2", "jsonld_types")
SKIP_TEXT = {"script", "style", "noscript", "template", "svg", "head"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class PageFacts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.facts: dict[str, object] = {"title": None, "h1": [], "description": None, "canonical": None,
                                         "hreflang": [], "robots": None, "h2": [], "jsonld": [], "events": [],
                                         "summaries": []}
        self.stack: list[tuple[str, bool]] = []  # (tag, hidden-for-text)
        self.capture: list[list] = []  # open captures: [tag, depth, buffer, kind]
        self.words: list[str] = []
        self.jsonld_buffer: list[str] | None = None

    def hidden(self) -> bool:
        return any(flag for _, flag in self.stack)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            name = (a.get("name") or "").lower()
            if name == "description":
                self.facts["description"] = clean(a.get("content") or "")
            elif name == "robots":
                self.facts["robots"] = clean(a.get("content") or "")
        if tag == "link":
            rel = (a.get("rel") or "").lower()
            if rel == "canonical":
                self.facts["canonical"] = a.get("href")
            elif rel == "alternate" and a.get("hreflang"):
                self.facts["hreflang"].append(f'{a["hreflang"]} {a.get("href")}')
        if a.get("data-umami-event"):
            self.facts["events"].append(f'{a["data-umami-event"]} @ {a.get("data-umami-event-location", "-")}')
        if tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self.jsonld_buffer = []
        if tag in VOID:
            return
        hide = tag in SKIP_TEXT or "hidden" in a or a.get("aria-hidden") == "true"
        self.stack.append((tag, hide))
        if tag in ("title", "h1", "h2", "summary"):
            self.capture.append([tag, len(self.stack), [], tag])

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if tag == "script" and self.jsonld_buffer is not None:
            self.facts["jsonld"].append("".join(self.jsonld_buffer))
            self.jsonld_buffer = None
        while self.capture and self.capture[-1][1] >= len(self.stack) and self.stack and self.stack[-1][0] == tag:
            kind, _, buffer, _ = self.capture.pop()
            text = clean("".join(buffer))
            if kind == "title":
                self.facts["title"] = text
            elif kind == "summary":
                self.facts["summaries"].append(text)
            else:
                self.facts[kind].append(text)
        # Pop to the matching tag (tolerates implicit closes such as </p>).
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.jsonld_buffer is not None:
            self.jsonld_buffer.append(data)
            return
        for capture in self.capture:
            if capture[0] == "title" or not self.hidden():
                capture[2].append(data)
        if not self.hidden():
            self.words.extend(data.split())


def jsonld_types(blocks: list[str]) -> tuple[list[str], list[str]]:
    types, faq = [], []

    def walk(node):
        if isinstance(node, dict):
            kind = node.get("@type")
            if kind:
                types.append(kind if isinstance(kind, str) else "+".join(kind))
            if kind == "FAQPage":
                faq.extend(clean(item.get("name", "")) for item in node.get("mainEntity", []))
            for key, value in node.items():
                if key in ("@graph",) or (isinstance(value, (dict, list)) and key != "mainEntity"):
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for block in blocks:
        try:
            walk(json.loads(block))
        except json.JSONDecodeError:
            types.append("INVALID-JSON")
    return sorted(set(types)), faq


def facts(source: str) -> dict[str, object]:
    parser = PageFacts()
    parser.feed(source)
    result = dict(parser.facts)
    result["h1"] = " | ".join(result["h1"])
    result["hreflang"] = sorted(result["hreflang"])
    result["jsonld_types"], result["faq"] = jsonld_types(result.pop("jsonld"))
    result["events"] = sorted(set(result["events"]))
    result["words"] = len(parser.words)
    return result


def git_show(base: str, path: str) -> str | None:
    completed = subprocess.run(["git", "show", f"{base}:{path}"], cwd=ROOT, capture_output=True, text=True)
    return completed.stdout if completed.returncode == 0 else None


def all_pages(base: str) -> list[str]:
    tracked = subprocess.run(["git", "ls-tree", "-r", "--name-only", base, "site"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    current = [str(path.relative_to(ROOT)) for path in (ROOT / "site").rglob("index.html")]
    return sorted({path for path in tracked + current if path.endswith("index.html")})


def faq_problem(page: dict[str, object]) -> str | None:
    questions = page["faq"]
    if not questions:
        return None
    visible = page["summaries"]
    missing = [question for question in questions if question not in visible]
    if missing:
        return f"FAQPage has {len(questions)} questions; not visible as a question: {missing}"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--expect", type=Path)
    parser.add_argument("--all", action="store_true", help="list unchanged pages too")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args(argv)
    expected = json.loads(args.expect.read_text(encoding="utf-8")) if args.expect else {}
    paths = args.paths or all_pages(args.base)
    failures, rows = 0, []
    for path in paths:
        before_source, after_path = git_show(args.base, path), ROOT / path
        if before_source is None or not after_path.exists():
            print(f"FAIL {path}: page {'added' if before_source is None else 'removed'}")
            failures += 1
            continue
        after_source = after_path.read_text(encoding="utf-8")
        before, after = facts(before_source), facts(after_source)
        problems, notes = [], []
        for field in SEO_FIELDS:
            if before[field] == after[field]:
                continue
            want = expected.get(path, {}).get(field)
            if want is not None and want == after[field]:
                notes.append(f"{field}: expected change {before[field]!r} -> {after[field]!r}")
            else:
                problems.append(f"{field}: {before[field]!r} -> {after[field]!r}")
        removed = sorted(set(before["events"]) - set(after["events"]))
        added = sorted(set(after["events"]) - set(before["events"]))
        new_names = {event.split(" @ ")[0] for event in added} - {event.split(" @ ")[0] for event in before["events"]}
        allowed_removed = set(expected.get(path, {}).get("events_removed", []))
        if set(removed) & allowed_removed:
            notes.append(f"umami events removed as expected: {sorted(set(removed) & allowed_removed)}")
        if set(removed) - allowed_removed:
            problems.append(f"umami events removed: {sorted(set(removed) - allowed_removed)}")
        if new_names - {"send-to-computer-click"}:
            problems.append(f"new umami event names: {sorted(new_names)}")
        if added:
            notes.append(f"umami events added: {added}")
        faq = faq_problem(after)
        if faq:
            problems.append(faq)
        if before["faq"] != after["faq"]:
            notes.append(f"FAQPage questions {len(before['faq'])} -> {len(after['faq'])}")
        delta = after["words"] - before["words"]
        changed = before_source != after_source
        status = "FAIL" if problems else ("CHANGED" if changed else "same")
        failures += bool(problems)
        rows.append((path, status, before["words"], after["words"], delta, len(after["faq"])))
        if changed or args.all or problems:
            print(f"{status:7} {path}  words {before['words']} -> {after['words']} ({delta:+d})  h2 {len(after['h2'])}  faq {len(after['faq'])}")
            for line in problems:
                print(f"        ! {line}")
            for line in notes:
                print(f"        · {line}")
    changed = sum(1 for row in rows if row[1] != "same")
    print(f"\n{len(rows)} pages checked against {args.base}: {changed} changed, {failures} with unexpected SEO/analytics changes.")
    print("Fields compared: title, H1, meta description, canonical, hreflang set, robots, ordered H2 list, JSON-LD types, Umami events, FAQPage vs visible questions; word count is informational.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
