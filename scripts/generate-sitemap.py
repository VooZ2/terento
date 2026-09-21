#!/usr/bin/env python3
"""Generate Terento's deterministic sitemap and public-page content manifest.

The page inventory comes from site/metadata.json.  A page fingerprint keeps
IndexNow and sitemap lastmod decisions aligned: visible text, SEO metadata,
structured data, embedded JSON and local JavaScript dependencies are included;
presentation-only HTML attributes, comments and asset cache versions are not.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "site" / "metadata.json"
SITEMAP_PATH = ROOT / "site" / "sitemap.xml"
DEFAULT_STATE_PATH = ROOT / ".github" / "indexnow" / "site-state.json"
BASE_URL = "https://terento.app"
SCHEMA_VERSION = 1

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_JS_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_JS_LINE_COMMENT_RE = re.compile(r"(^|\s)//[^\n]*")
_SPACE_RE = re.compile(r"\s+")
_ASSET_VERSION_RE = re.compile(r"([?&])v=[^&#\s\"']+")
_ATTR_RE = re.compile(r"\s+([a-zA-Z_:][-a-zA-Z0-9_:]*)\s*=\s*([\"'])(.*?)\2", re.DOTALL)
_TECHNICAL_JSON_KEYS = {"generatedAt"}


def run_git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def normalize_space(value: str) -> str:
    return _SPACE_RE.sub(" ", html.unescape(value)).strip()


def normalize_asset_url(value: str) -> str:
    return _ASSET_VERSION_RE.sub(r"\1v=<cache-version>", value)


def normalize_script(source: str) -> str:
    source = _JS_BLOCK_COMMENT_RE.sub("", source)
    source = _JS_LINE_COMMENT_RE.sub(r"\1", source)
    return _SPACE_RE.sub(" ", source).strip()


def remove_technical_json_fields(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: remove_technical_json_fields(item)
            for key, item in value.items()
            if key not in _TECHNICAL_JSON_KEYS
        }
    if isinstance(value, list):
        return [remove_technical_json_fields(item) for item in value]
    return value


def canonical_json(value: str) -> str:
    try:
        parsed = remove_technical_json_fields(json.loads(value))
    except json.JSONDecodeError:
        return normalize_space(value)
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def local_script_path(source: str) -> str | None:
    path = urlsplit(source).path
    if not path.startswith("/") or not path.endswith(".js"):
        return None
    relative = Path("site") / path.lstrip("/")
    try:
        relative.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return None
    if not relative.is_file():
        return None
    return relative.as_posix()


class SemanticHTMLParser(HTMLParser):
    """Collect page content while excluding layout/cache implementation noise."""

    _META_NAMES = {"description", "robots"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[str] = []
        self.dependencies: set[str] = set()
        self._script_kind: str | None = None
        self._script_buffer: list[str] = []
        self._style_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attributes = {name.lower(): value or "" for name, value in attrs}
        if tag == "script":
            source = local_script_path(attributes.get("src", ""))
            if source:
                self.dependencies.add(source)
            script_type = attributes.get("type", "").lower()
            self._script_kind = "json" if script_type in {"application/json", "application/ld+json"} else "script"
            self._script_buffer = []
            return
        if tag == "style":
            self._style_depth += 1
            return
        if tag == "noscript":
            return

        selected: list[str] = []
        if tag == "a" and attributes.get("href"):
            selected.append(f"href={normalize_asset_url(attributes['href'])}")
        if tag == "img" and attributes.get("alt"):
            selected.append(f"alt={normalize_space(attributes['alt'])}")
        if tag == "time" and attributes.get("datetime"):
            selected.append(f"datetime={normalize_space(attributes['datetime'])}")
        if tag == "html" and attributes.get("lang"):
            selected.append(f"lang={normalize_space(attributes['lang'])}")
        if tag == "meta":
            name = attributes.get("name", "").lower()
            prop = attributes.get("property", "").lower()
            if name in self._META_NAMES or name.startswith("twitter:") or prop.startswith("og:"):
                for key in ("name", "property", "content"):
                    if attributes.get(key):
                        selected.append(f"{key}={normalize_space(attributes[key])}")
        if tag == "link":
            rel = {part.lower() for part in attributes.get("rel", "").split()}
            if {"canonical", "alternate"} & rel:
                selected.append(f"rel={' '.join(sorted(rel))}")
                if attributes.get("hreflang"):
                    selected.append(f"hreflang={normalize_space(attributes['hreflang'])}")
                if attributes.get("href"):
                    selected.append(f"href={normalize_asset_url(attributes['href'])}")

        self.tokens.append(f"<{tag}>")
        self.tokens.extend(selected)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "script":
            if self._script_kind == "json":
                self.tokens.append(f"json={canonical_json(''.join(self._script_buffer))}")
            self._script_kind = None
            self._script_buffer = []
            return
        if tag == "style":
            self._style_depth = max(0, self._style_depth - 1)
            return
        if tag != "noscript":
            self.tokens.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._script_kind == "json":
            self._script_buffer.append(data)
        elif self._script_kind is None and self._style_depth == 0:
            value = normalize_space(data)
            if value:
                self.tokens.append(f"text={value}")


def semantic_material(source: str) -> tuple[str, list[str]]:
    source = _COMMENT_RE.sub("", source)
    parser = SemanticHTMLParser()
    parser.feed(source)
    parser.close()
    parts = [*parser.tokens]
    for dependency in sorted(parser.dependencies):
        dependency_source = (ROOT / dependency).read_text(encoding="utf-8")
        parts.append(f"dependency={dependency}:{normalize_script(dependency_source)}")
    return "\n".join(parts), sorted(parser.dependencies)


def content_fingerprint(source: str) -> tuple[str, list[str]]:
    material, dependencies = semantic_material(source)
    return hashlib.sha256(material.encode("utf-8")).hexdigest(), dependencies


def page_path(page: dict[str, object]) -> Path:
    relative = Path(str(page["file"]))
    if relative.is_absolute() or relative.parts[:1] != ("site",):
        raise ValueError(f"page file must be inside site/: {relative}")
    path = ROOT / relative
    if not path.is_file():
        raise ValueError(f"page file does not exist: {relative}")
    return path


def validate_page(page: dict[str, object], pages: list[dict[str, object]]) -> None:
    path = str(page.get("path", ""))
    if not path.startswith("/") or "?" in path or "#" in path:
        raise ValueError(f"invalid canonical page path: {path}")
    if path != "/" and not path.endswith("/"):
        raise ValueError(f"canonical page path must keep trailing slash: {path}")
    url = f"{BASE_URL}{path}"
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "terento.app" or parsed.query or parsed.fragment:
        raise ValueError(f"invalid canonical page URL: {url}")
    if sum(1 for candidate in pages if candidate.get("path") == path) != 1:
        raise ValueError(f"duplicate canonical page path: {path}")
    page_path(page)


def read_state(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(state, dict) or state.get("schemaVersion") != SCHEMA_VERSION:
        return None
    published = state.get("published")
    if state.get("status") != "published" or not isinstance(published, dict):
        return None
    pages = published.get("pages")
    if not isinstance(pages, list):
        return None
    result: dict[str, object] = {}
    for page in pages:
        if isinstance(page, dict) and isinstance(page.get("path"), str):
            result[page["path"]] = page
    return result


def git_dirty(paths: list[str]) -> bool:
    if not paths:
        return True
    for path in paths:
        if run_git("ls-files", "--error-unmatch", "--", path).returncode != 0:
            return True
    result = run_git("diff", "--quiet", "HEAD", "--", *paths)
    return result.returncode != 0


def git_text(revision: str, relative: str) -> str | None:
    result = run_git("show", f"{revision}:{relative}")
    return result.stdout if result.returncode == 0 else None


def revision_fingerprint(revision: str, relative: str) -> str | None:
    source = git_text(revision, relative)
    if source is None:
        return None
    material, dependencies = semantic_material_at_revision(revision, source)
    parts = [material]
    for dependency in dependencies:
        dependency_source = git_text(revision, dependency)
        if dependency_source is not None:
            parts.append(f"dependency={dependency}:{normalize_script(dependency_source)}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def semantic_material_at_revision(revision: str, source: str) -> tuple[str, list[str]]:
    source = _COMMENT_RE.sub("", source)
    parser = SemanticHTMLParser()
    parser.feed(source)
    parser.close()
    return "\n".join(parser.tokens), sorted(parser.dependencies)


def git_last_semantic_change(relative: str, dependencies: list[str]) -> str | None:
    paths = [relative, *dependencies]
    log = run_git("log", "--format=%H%x09%cs", "HEAD", "--", *paths)
    if log.returncode != 0:
        return None
    for line in log.stdout.splitlines():
        revision, _, date = line.partition("\t")
        if not revision or not date:
            continue
        parent_result = run_git("rev-parse", f"{revision}^")
        parent = parent_result.stdout.strip() if parent_result.returncode == 0 else ""
        current_fingerprint = revision_fingerprint(revision, relative)
        previous_fingerprint = revision_fingerprint(parent, relative) if parent else None
        if current_fingerprint is not None and current_fingerprint != previous_fingerprint:
            return date
    return None


def build_manifest(state_path: Path) -> dict[str, object]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if config.get("baseUrl", "").rstrip("/") != BASE_URL:
        raise ValueError("site/metadata.json must use https://terento.app as baseUrl")
    pages = config.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("site/metadata.json must contain pages")
    for page in pages:
        if not isinstance(page, dict):
            raise ValueError("site/metadata.json pages must be objects")
        validate_page(page, pages)

    previous = read_state(state_path)
    result_pages: list[dict[str, object]] = []
    for page in pages:
        source_path = page_path(page)
        relative = source_path.relative_to(ROOT).as_posix()
        source = source_path.read_text(encoding="utf-8")
        fingerprint, dependencies = content_fingerprint(source)
        old = previous.get(str(page["path"])) if previous else None
        old_fingerprint = old.get("fingerprint") if isinstance(old, dict) else None
        lastmod = old.get("lastmod") if isinstance(old, dict) and old_fingerprint == fingerprint else None
        lastmod_reason = None
        if lastmod is None:
            tracked_paths = [relative, *dependencies]
            if git_dirty(tracked_paths):
                lastmod_reason = "uncommitted content has no reliable Git date"
            else:
                lastmod = git_last_semantic_change(relative, dependencies)
                if lastmod is None:
                    lastmod_reason = "no reliable semantic Git change was found"
        result_pages.append(
            {
                "path": str(page["path"]),
                "url": f"{BASE_URL}{page['path']}",
                "file": relative,
                "locale": str(page.get("locale", "")),
                "indexable": page.get("indexable", True) is not False,
                "fingerprint": fingerprint,
                "dependencies": dependencies,
                **({"lastmod": lastmod} if lastmod else {}),
                **({"lastmodOmittedReason": lastmod_reason} if lastmod_reason else {}),
            }
        )

    return {"schemaVersion": SCHEMA_VERSION, "baseUrl": BASE_URL, "pages": result_pages}


def render_sitemap(manifest: dict[str, object]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for page in manifest["pages"]:
        if not page["indexable"]:
            continue
        lines.append("  <url>")
        lines.append(f"    <loc>{html.escape(str(page['url']))}</loc>")
        if page.get("lastmod"):
            lines.append(f"    <lastmod>{page['lastmod']}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write site/sitemap.xml")
    mode.add_argument("--check", action="store_true", help="fail if site/sitemap.xml is stale")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH, help="last confirmed public-site state")
    parser.add_argument("--manifest-out", type=Path, help="write the content manifest to this path")
    args = parser.parse_args()

    try:
        manifest = build_manifest(args.state if args.state.is_absolute() else ROOT / args.state)
        rendered = render_sitemap(manifest)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"sitemap generation failed: {error}", file=sys.stderr)
        return 1

    if args.write:
        SITEMAP_PATH.write_text(rendered, encoding="utf-8")
    elif SITEMAP_PATH.read_text(encoding="utf-8") != rendered:
        print("site/sitemap.xml is stale; run scripts/generate-sitemap.py --write", file=sys.stderr)
        return 1

    if args.manifest_out:
        output = args.manifest_out if args.manifest_out.is_absolute() else ROOT / args.manifest_out
        write_json(output, manifest)

    omitted = [page for page in manifest["pages"] if page.get("indexable") and page.get("lastmodOmittedReason")]
    for page in omitted:
        print(f"lastmod omitted for {page['path']}: {page['lastmodOmittedReason']}", file=sys.stderr)
    print(f"sitemap {'written' if args.write else 'validated'}: {sum(1 for page in manifest['pages'] if page['indexable'])} indexable URL(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
