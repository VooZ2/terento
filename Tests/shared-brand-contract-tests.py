#!/usr/bin/env python3
"""Verify the non-app brand-token source, generated outputs, and locked identity."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TOKENS_PATH = ROOT / "brand" / "DESIGN_TOKENS.json"
APP_TOKENS_PATH = (
    ROOT / "lab" / "native-connectivity-poc" / "Sources" / "TerentoPoC"
    / "Views" / "DesignSystem" / "TerentoTokens.generated.swift"
)
CONNECT_SCREEN_PATH = ROOT / "lab" / "native-connectivity-poc" / "Sources" / "TerentoPoC" / "Views" / "ConnectScreen.swift"
SITE_CSS_PATH = ROOT / "site" / "styles.css"
ADMIN_SOURCE_PATH = ROOT / "backend" / "catalog-api" / "src" / "terento_catalog" / "admin.py"
ADMIN_MODULE_PATH = ROOT / "backend" / "catalog-api" / "src" / "terento_catalog" / "admin_brand_tokens_generated.py"
LOGO_PATH = ROOT / "brand" / "logo" / "logo.svg"
HEX_RE = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
SITE_BEGIN = "/* BEGIN GENERATED TERENTO BRAND TOKENS */"
SITE_END = "/* END GENERATED TERENTO BRAND TOKENS */"
STYLE_VERSION = "20260905-guide-flow-v1"
LOGO_SHA256 = "6fd490112b8cb34e9a0f699a38f16ddf6d3a0848981ec15c694710946421dc13"


def token_value(tokens: dict, *path: str) -> str:
    node: object = tokens
    for part in path:
        assert isinstance(node, dict) and part in node, f"missing token path: {'.'.join(path)}"
        node = node[part]
    if isinstance(node, dict) and "$value" in node:
        node = node["$value"]
    assert isinstance(node, str), f"token path is not a string: {'.'.join(path)}"
    if node.startswith("{") and node.endswith("}"):
        return token_value(tokens, *node[1:-1].split("."))
    return node


def luminance(hex_value: str) -> float:
    channels = [int(hex_value[offset : offset + 2], 16) / 255 for offset in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground: str, background: str) -> float:
    foreground_luminance = luminance(foreground)
    background_luminance = luminance(background)
    return (max(foreground_luminance, background_luminance) + 0.05) / (
        min(foreground_luminance, background_luminance) + 0.05
    )


def load_generated_admin_css() -> str:
    spec = importlib.util.spec_from_file_location("admin_brand_tokens_generated", ADMIN_MODULE_PATH)
    assert spec and spec.loader, "unable to load generated admin token module"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ADMIN_BRAND_TOKENS_CSS


def main() -> int:
    tokens = json.loads(TOKENS_PATH.read_text(encoding="utf-8"))

    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate-brand-tokens.py"), "--check"],
        cwd=ROOT,
        check=True,
    )

    locked_values = {
        ("color", "brand", "sky"): "#7898A8",
        ("color", "brand", "lichen"): "#9AA58B",
        ("color", "brand", "stone"): "#B39A78",
        ("color", "brand", "offWhite"): "#F7F3EC",
        ("color", "brand", "graphite"): "#222A2B",
        ("color", "functional", "interactivePrimary"): "#577787",
        ("color", "functional", "interactiveHover"): "#4F6E7E",
    }
    for path, expected in locked_values.items():
        assert token_value(tokens, *path) == expected, f"locked token changed: {'.'.join(path)}"

    app_tokens = APP_TOKENS_PATH.read_text(encoding="utf-8")
    assert "Generated from brand/DESIGN_TOKENS.json. Do not edit manually." in app_tokens
    for value in locked_values.values():
        assert f"0x{value[1:]}" in app_tokens, f"app output is missing canonical value {value}"
    assert 'brandFontName = "Instrument Sans"' in app_tokens
    assert 'uiFontName = "Inter"' in app_tokens
    assert 'monoFontName = "JetBrains Mono"' in app_tokens

    connect_screen = CONNECT_SCREEN_PATH.read_text(encoding="utf-8")
    assert "private enum TerentoColors" not in connect_screen
    assert "private extension Font" not in connect_screen
    assert "Color(hex:" not in connect_screen

    assert hashlib.sha256(LOGO_PATH.read_bytes()).hexdigest() == LOGO_SHA256, "canonical logo geometry changed"

    site = SITE_CSS_PATH.read_text(encoding="utf-8")
    assert site.count(SITE_BEGIN) == 1 and site.count(SITE_END) == 1, "site token markers are not unique"
    site_start = site.index(SITE_BEGIN)
    site_end = site.index(SITE_END) + len(SITE_END)
    site_generated = site[site_start:site_end]
    site_local = site[:site_start] + site[site_end:]
    assert not HEX_RE.search(site_local), "site contains a raw color outside the generated token block"
    for variable in (
        "--link-text", "--link-text-hover", "--muted-text", "--eyebrow-text",
        "--interactive-primary-text", "--font-brand", "--font-ui",
    ):
        assert variable in site_generated, f"site generated block is missing {variable}"
    assert "background: var(--interactive);" in site, "site primary action lost shared interactive token"
    for html_path in (ROOT / "site").rglob("*.html"):
        html = html_path.read_text(encoding="utf-8")
        if "/styles.css?v=" not in html:
            continue
        assert f"/styles.css?v={STYLE_VERSION}" in html, f"{html_path}: stale stylesheet cache version"
        assert not re.search(rf"/styles\.css\?v=(?!{re.escape(STYLE_VERSION)})[^\"\s]+", html), f"{html_path}: inconsistent stylesheet cache version"

    admin_source = ADMIN_SOURCE_PATH.read_text(encoding="utf-8")
    admin_generated = load_generated_admin_css()
    assert "from .admin_brand_tokens_generated import ADMIN_BRAND_TOKENS_CSS" in admin_source
    assert 'ADMIN_STYLES = ADMIN_BRAND_TOKENS_CSS + """' in admin_source
    assert not HEX_RE.search(admin_source), "admin.py contains a raw color literal"
    for variable in (
        "--status-neutral-surface", "--status-tested-surface", "--status-supported-surface",
        "--status-success-surface", "--status-error-surface", "--error-surface",
        "--success-text", "--new-badge-text", "--font-brand", "--font-ui", "--font-mono",
    ):
        assert variable in admin_generated, f"generated admin CSS is missing {variable}"
    assert "var(--status-error-surface)" in admin_source
    assert "var(--status-success-surface)" in admin_source
    assert "var(--font-brand)" in admin_source and "var(--font-ui)" in admin_source

    light_background = token_value(tokens, "color", "light", "backgroundPrimary")
    light_surface = token_value(tokens, "color", "light", "surfacePrimary")
    light_secondary_surface = token_value(tokens, "color", "light", "backgroundSecondary")
    for name in ("linkText", "linkTextHover"):
        assert contrast(token_value(tokens, "semantic", "web", "light", name), light_background) >= 4.5
    for name in ("mutedTextStrong", "eyebrowText"):
        assert contrast(token_value(tokens, "semantic", "web", "light", name), light_secondary_surface) >= 4.5
    for text_name, surface_name in (
        ("statusNeutralText", "statusNeutralSurface"),
        ("statusTestedText", "statusTestedSurface"),
        ("statusSupportedText", "statusSupportedSurface"),
        ("statusSuccessText", "statusSuccessSurface"),
        ("statusErrorText", "statusErrorSurface"),
    ):
        ratio = contrast(
            token_value(tokens, "semantic", "admin", "light", text_name),
            token_value(tokens, "semantic", "admin", "light", surface_name),
        )
        assert ratio >= 4.5, f"admin status contrast is only {ratio:.2f}:1 for {text_name}"
    assert contrast(token_value(tokens, "semantic", "admin", "light", "destructiveText"), light_surface) >= 4.5
    assert contrast(token_value(tokens, "semantic", "admin", "light", "errorText"), token_value(tokens, "semantic", "admin", "light", "errorSurface")) >= 4.5
    assert contrast(token_value(tokens, "semantic", "admin", "light", "successText"), token_value(tokens, "semantic", "admin", "light", "successSurface")) >= 4.5
    assert contrast(token_value(tokens, "semantic", "admin", "light", "newBadgeText"), token_value(tokens, "semantic", "admin", "light", "newBadgeSurface")) >= 4.5

    print("Non-app brand token contract, identity locks, and contrast checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
