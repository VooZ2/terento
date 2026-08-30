#!/usr/bin/env python3
"""Generate non-app Terento brand-token outputs from DESIGN_TOKENS.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
TOKENS_PATH = ROOT / "brand" / "DESIGN_TOKENS.json"
BRAND_CSS_PATH = ROOT / "brand" / "tokens.css"
APP_TOKENS_PATH = (
    ROOT / "lab" / "native-connectivity-poc" / "Sources" / "TerentoPoC"
    / "Views" / "DesignSystem" / "TerentoTokens.generated.swift"
)
SITE_CSS_PATH = ROOT / "site" / "styles.css"
ADMIN_MODULE_PATH = (
    ROOT / "backend" / "catalog-api" / "src" / "terento_catalog"
    / "admin_brand_tokens_generated.py"
)
SITE_BEGIN = "/* BEGIN GENERATED TERENTO BRAND TOKENS */"
SITE_END = "/* END GENERATED TERENTO BRAND TOKENS */"
GENERATED_HEADER = "Generated from brand/DESIGN_TOKENS.json. Do not edit manually."


def load_tokens() -> dict:
    try:
        return json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Unable to read {TOKENS_PATH}: {exc}") from exc


def resolve_value(tokens: dict, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Token value must be a string, got {value!r}")
    if not (value.startswith("{") and value.endswith("}")):
        return value
    path = value[1:-1].split(".")
    node: object = tokens
    for part in path:
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"Unknown token reference: {value}")
        node = node[part]
    if isinstance(node, dict) and "$value" in node:
        return resolve_value(tokens, node["$value"])
    return resolve_value(tokens, node)


def value_at(tokens: dict, *path: str) -> str:
    node: object = tokens
    for part in path:
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"Missing token path: {'.'.join(path)}")
        node = node[part]
    if not isinstance(node, dict) or "$value" not in node:
        raise ValueError(f"Token path has no $value: {'.'.join(path)}")
    return resolve_value(tokens, node["$value"])


def kebab(value: str) -> str:
    output = []
    for character in value:
        if character.isupper():
            output.append("-")
        output.append(character.lower())
    return "".join(output).lstrip("-")


def color(tokens: dict, *path: str) -> str:
    return value_at(tokens, "color", *path)


def semantic(tokens: dict, platform: str, mode: str, name: str) -> str:
    return value_at(tokens, "semantic", platform, mode, name)


def font_stack(tokens: dict, name: str, fallback: str) -> str:
    family = value_at(tokens, "typography", "fontFamily", name)
    return f'"{family}", {fallback}'


def swift_color_literal(tokens: dict, *path: str) -> str:
    value = value_at(tokens, "color", *path)
    if not (value.startswith("#") and len(value) == 7):
        raise ValueError(f"Swift app token must be a #RRGGBB color: {value}")
    return f"0x{value[1:].upper()}"


def app_swift_tokens(tokens: dict) -> str:
    lines = [
        f"// {GENERATED_HEADER}",
        "import SwiftUI",
        "",
        "enum TerentoGeneratedTokens {",
        "    enum Brand {",
        f"        static let sky = Color(terentoHex: {swift_color_literal(tokens, 'brand', 'sky')})",
        f"        static let lichen = Color(terentoHex: {swift_color_literal(tokens, 'brand', 'lichen')})",
        f"        static let warmStone = Color(terentoHex: {swift_color_literal(tokens, 'brand', 'stone')})",
        f"        static let offWhite = Color(terentoHex: {swift_color_literal(tokens, 'brand', 'offWhite')})",
        f"        static let graphite = Color(terentoHex: {swift_color_literal(tokens, 'brand', 'graphite')})",
        "    }",
        "",
        "    enum Functional {",
        f"        static let interactivePrimary = Color(terentoHex: {swift_color_literal(tokens, 'functional', 'interactivePrimary')})",
        f"        static let interactiveHover = Color(terentoHex: {swift_color_literal(tokens, 'functional', 'interactiveHover')})",
        f"        static let secondaryText = Color(terentoHex: {swift_color_literal(tokens, 'functional', 'secondaryText')})",
        f"        static let lichenDark = Color(terentoHex: {swift_color_literal(tokens, 'functional', 'lichenDark')})",
        f"        static let stoneDark = Color(terentoHex: {swift_color_literal(tokens, 'functional', 'stoneDark')})",
        f"        static let errorRust = Color(terentoHex: {swift_color_literal(tokens, 'functional', 'errorRust')})",
        f"        static let selectedTint = Color(terentoHex: {swift_color_literal(tokens, 'functional', 'selectedTint')})",
        "    }",
        "",
        "    enum Light {",
    ]
    for name in (
        "backgroundPrimary", "backgroundSecondary", "surfacePrimary", "surfaceElevated",
        "textPrimary", "textSecondary", "textMuted", "textDisabled", "borderSubtle",
        "selectedBackground", "selectedBorder", "focusRing", "progressTrack", "progressFill",
    ):
        lines.append(
            f"        static let {name} = Color(terentoHex: "
            f"{swift_color_literal(tokens, 'light', name)})"
        )
    lines.extend((
        "    }",
        "",
        "    enum Status {",
    ))
    for name in ("success", "warning", "error", "info"):
        lines.append(
            f"        static let {name} = Color(terentoHex: "
            f"{swift_color_literal(tokens, 'status', 'light', name)})"
        )
    lines.extend((
        "    }",
        "",
        "    enum Typography {",
        f'        static let brandFontName = {json.dumps(value_at(tokens, "typography", "fontFamily", "brand"), ensure_ascii=False)}',
        f'        static let uiFontName = {json.dumps(value_at(tokens, "typography", "fontFamily", "ui"), ensure_ascii=False)}',
        f'        static let monoFontName = {json.dumps(value_at(tokens, "typography", "fontFamily", "mono"), ensure_ascii=False)}',
        "    }",
        "}",
        "",
        "private extension Color {",
        "    init(terentoHex hex: UInt32) {",
        "        self.init(",
        "            red: Double((hex >> 16) & 0xFF) / 255,",
        "            green: Double((hex >> 8) & 0xFF) / 255,",
        "            blue: Double(hex & 0xFF) / 255",
        "        )",
        "    }",
        "}",
        "",
    ))
    return "\n".join(lines)


BRAND_FONT_FALLBACK = '"Helvetica Neue", Arial, sans-serif'
UI_FONT_FALLBACK = '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
MONO_FONT_FALLBACK = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"


def canonical_css(tokens: dict) -> str:
    lines = [
        f"/* {GENERATED_HEADER} */",
        ":root {",
        "  /* Terento — core brand */",
        f"  --terento-sky: {color(tokens, 'brand', 'sky')};",
        f"  --terento-lichen: {color(tokens, 'brand', 'lichen')};",
        f"  --terento-warm-stone: {color(tokens, 'brand', 'stone')};",
        f"  --terento-off-white: {color(tokens, 'brand', 'offWhite')};",
        f"  --terento-graphite: {color(tokens, 'brand', 'graphite')};",
        "",
        "  /* Accessible functional derivatives */",
        f"  --terento-interactive: {color(tokens, 'functional', 'interactivePrimary')};",
        f"  --terento-interactive-hover: {color(tokens, 'functional', 'interactiveHover')};",
        f"  --terento-text-secondary-accessible: {color(tokens, 'functional', 'secondaryText')};",
        f"  --terento-lichen-dark: {color(tokens, 'functional', 'lichenDark')};",
        f"  --terento-stone-dark: {color(tokens, 'functional', 'stoneDark')};",
        f"  --terento-error-rust: {color(tokens, 'functional', 'errorRust')};",
        f"  --terento-selected-tint: {color(tokens, 'functional', 'selectedTint')};",
        "",
        "  /* Shared web semantic derivatives */",
    ]
    for name in ("linkText", "linkTextHover", "mutedTextStrong", "eyebrowText"):
        lines.append(f"  --terento-web-{kebab(name)}: {semantic(tokens, 'web', 'light', name)};")
    lines.extend(("", "  /* Admin semantic derivatives */"))
    for name in (
        "destructiveText", "successSurface", "placeholderText",
        "statusNeutralSurface", "statusNeutralBorder", "statusNeutralText",
        "statusTestedSurface", "statusTestedBorder", "statusTestedText",
        "statusSupportedSurface", "statusSupportedBorder", "statusSupportedText",
        "statusSuccessSurface", "statusSuccessBorder", "statusSuccessText",
        "statusErrorSurface", "statusErrorBorder", "statusErrorText",
        "errorSurface", "errorText", "successText", "newBadgeSurface", "newBadgeText",
    ):
        lines.append(f"  --terento-admin-{kebab(name)}: {semantic(tokens, 'admin', 'light', name)};")
    lines.extend(("", "  /* Light mode */"))
    light_names = (
        "backgroundPrimary", "backgroundSecondary", "surfacePrimary", "surfaceElevated",
        "textPrimary", "textSecondary", "textMuted", "textDisabled", "borderSubtle",
    )
    for name in light_names:
        lines.append(f"  --{kebab(name)}: {color(tokens, 'light', name)};")
    lines.extend((
        "",
        f"  --interactive-primary: {color(tokens, 'functional', 'interactivePrimary')};",
        f"  --interactive-primary-hover: {color(tokens, 'functional', 'interactiveHover')};",
        f"  --interactive-primary-text: {color(tokens, 'light', 'surfacePrimary')};",
        f"  --focus-ring: {color(tokens, 'light', 'focusRing')};",
        f"  --status-success: {color(tokens, 'status', 'light', 'success')};",
        f"  --status-warning: {color(tokens, 'status', 'light', 'warning')};",
        f"  --status-error: {color(tokens, 'status', 'light', 'error')};",
        f"  --status-info: {color(tokens, 'status', 'light', 'info')};",
        f"  --selected-background: {color(tokens, 'light', 'selectedBackground')};",
        f"  --selected-border: {color(tokens, 'light', 'selectedBorder')};",
        f"  --progress-track: {color(tokens, 'light', 'progressTrack')};",
        f"  --progress-fill: {color(tokens, 'light', 'progressFill')};",
        "",
        "  /* Typography */",
        f"  --font-brand: {font_stack(tokens, 'brand', BRAND_FONT_FALLBACK)};",
        f"  --font-ui: {font_stack(tokens, 'ui', UI_FONT_FALLBACK)};",
        f"  --font-mono: {font_stack(tokens, 'mono', MONO_FONT_FALLBACK)};",
        "",
        "  /* Validated type scale */",
    ))
    for name in (
        "hero", "h1", "h2", "h3", "uiHeading", "body", "bodySmall", "label",
        "button", "caption", "diagnostics",
    ):
        scale = tokens["typography"]["scale"][name]
        lines.extend((
            f"  --type-{kebab(name)}-size: {scale['fontSize']};",
            f"  --type-{kebab(name)}-line: {scale['lineHeight']};",
        ))
    lines.extend(("", "  /* Provisional implementation defaults; validate in the real product */"))
    for index, spacing in zip((1, 2, 3, 4, 6, 8, 12, 16), tokens["implementationDefaults"]["spacing"]):
        lines.append(f"  --space-{index}: {spacing};")
    lines.extend((
        "",
        f"  --radius-control: {tokens['implementationDefaults']['radius']['control']};",
        f"  --radius-card: {tokens['implementationDefaults']['radius']['card']};",
        f"  --radius-large: {tokens['implementationDefaults']['radius']['large']};",
        "}",
        "",
        '[data-theme="dark"],',
        ".terento-dark {",
    ))
    dark_names = (
        "backgroundPrimary", "backgroundSecondary", "surfacePrimary", "surfaceElevated",
        "textPrimary", "textSecondary", "textMuted", "textDisabled", "borderSubtle",
    )
    for name in dark_names:
        lines.append(f"  --{kebab(name)}: {color(tokens, 'dark', name)};")
    lines.extend((
        "",
        f"  --interactive-primary: {color(tokens, 'functional', 'interactivePrimary')};",
        f"  --interactive-primary-hover: {color(tokens, 'functional', 'interactiveHover')};",
        f"  --interactive-primary-text: {color(tokens, 'light', 'surfacePrimary')};",
        f"  --focus-ring: {color(tokens, 'dark', 'focusRing')};",
        f"  --status-success: {color(tokens, 'status', 'dark', 'success')};",
        f"  --status-warning: {color(tokens, 'status', 'dark', 'warning')};",
        f"  --status-error: {color(tokens, 'status', 'dark', 'error')};",
        f"  --status-info: {color(tokens, 'status', 'dark', 'info')};",
        f"  --progress-track: {color(tokens, 'dark', 'progressTrack')};",
        f"  --progress-fill: {color(tokens, 'dark', 'progressFill')};",
        "}",
        "",
        "/* Suggested semantic usage */",
        ".terento-heading {",
        "  font-family: var(--font-brand);",
        "  color: var(--text-primary);",
        "}",
        "",
        ".terento-body {",
        "  font-family: var(--font-ui);",
        "  color: var(--text-primary);",
        "}",
        "",
        ".terento-diagnostics {",
        "  font-family: var(--font-mono);",
        "}",
        "",
        ".terento-primary-button {",
        "  background: var(--interactive-primary);",
        "  color: var(--interactive-primary-text);",
        "  font: 600 var(--type-button-size)/var(--type-button-line) var(--font-ui);",
        "}",
        "",
        ".terento-primary-button:hover {",
        "  background: var(--interactive-primary-hover);",
        "}",
        "",
        ".terento-primary-button:focus-visible {",
        "  outline: 3px solid var(--focus-ring);",
        "  outline-offset: 3px;",
        "}",
        "",
    ))
    return "\n".join(lines)


def site_token_block(tokens: dict) -> str:
    light = {
        "sky": color(tokens, "brand", "sky"),
        "lichen": color(tokens, "brand", "lichen"),
        "stone": color(tokens, "brand", "stone"),
        "off-white": color(tokens, "light", "backgroundPrimary"),
        "graphite": color(tokens, "light", "textPrimary"),
        "interactive": color(tokens, "functional", "interactivePrimary"),
        "interactive-hover": color(tokens, "functional", "interactiveHover"),
        "link-text": semantic(tokens, "web", "light", "linkText"),
        "link-text-hover": semantic(tokens, "web", "light", "linkTextHover"),
        "accent-text": semantic(tokens, "web", "light", "linkText"),
        "muted-text": semantic(tokens, "web", "light", "mutedTextStrong"),
        "eyebrow-text": semantic(tokens, "web", "light", "eyebrowText"),
        "focus-ring": semantic(tokens, "web", "light", "linkText"),
        "surface": color(tokens, "light", "surfacePrimary"),
        "surface-muted": color(tokens, "light", "backgroundSecondary"),
        "border": color(tokens, "light", "borderSubtle"),
        "footer-bg": color(tokens, "brand", "graphite"),
        "footer-text": color(tokens, "brand", "offWhite"),
        "interactive-primary-text": color(tokens, "light", "surfacePrimary"),
    }
    dark = {
        "off-white": color(tokens, "dark", "backgroundPrimary"),
        "graphite": color(tokens, "dark", "textPrimary"),
        "surface": color(tokens, "dark", "surfacePrimary"),
        "surface-muted": color(tokens, "dark", "backgroundSecondary"),
        "muted-text": semantic(tokens, "web", "dark", "mutedTextStrong"),
        "eyebrow-text": semantic(tokens, "web", "dark", "eyebrowText"),
        "link-text": semantic(tokens, "web", "dark", "linkText"),
        "link-text-hover": semantic(tokens, "web", "dark", "linkTextHover"),
        "accent-text": semantic(tokens, "web", "dark", "linkText"),
        "focus-ring": semantic(tokens, "web", "dark", "linkText"),
        "border": color(tokens, "dark", "borderSubtle"),
        "sky": color(tokens, "dark", "focusRing"),
        "lichen": color(tokens, "status", "dark", "success"),
        "stone": color(tokens, "status", "dark", "warning"),
        "footer-bg": color(tokens, "brand", "graphite"),
        "footer-text": color(tokens, "brand", "offWhite"),
    }
    lines = [
        SITE_BEGIN,
        f"/* {GENERATED_HEADER} */",
        ":root {",
    ]
    for name, value in light.items():
        lines.append(f"  --{name}: {value};")
    lines.extend((
        "  --secondary: var(--muted-text);",
        f"  --font-brand: {font_stack(tokens, 'brand', BRAND_FONT_FALLBACK)};",
        f"  --font-ui: {font_stack(tokens, 'ui', UI_FONT_FALLBACK)};",
        "}",
        "",
        "@media (prefers-color-scheme: dark) {",
        "  :root {",
    ))
    for name, value in dark.items():
        lines.append(f"    --{name}: {value};")
    lines.extend(("    --secondary: var(--muted-text);", "  }", "}", SITE_END, ""))
    return "\n".join(lines)


def admin_token_css(tokens: dict) -> str:
    shared = {
        "off-white": color(tokens, "brand", "offWhite"),
        "graphite": color(tokens, "brand", "graphite"),
        "sky": color(tokens, "brand", "sky"),
        "lichen": color(tokens, "brand", "lichen"),
        "stone": color(tokens, "brand", "stone"),
        "interactive": color(tokens, "functional", "interactivePrimary"),
        "interactive-hover": color(tokens, "functional", "interactiveHover"),
        "secondary": color(tokens, "functional", "secondaryText"),
        "font-brand": font_stack(tokens, "brand", BRAND_FONT_FALLBACK),
        "font-ui": font_stack(tokens, "ui", UI_FONT_FALLBACK),
        "font-mono": font_stack(tokens, "mono", MONO_FONT_FALLBACK),
        "surface": color(tokens, "light", "surfacePrimary"),
        "surface-muted": color(tokens, "light", "backgroundSecondary"),
        "border": color(tokens, "light", "borderSubtle"),
        "interactive-primary-text": color(tokens, "light", "surfacePrimary"),
        "danger": semantic(tokens, "admin", "light", "destructiveText"),
        "success-bg": semantic(tokens, "admin", "light", "successSurface"),
        "admin-placeholder": semantic(tokens, "admin", "light", "placeholderText"),
        "admin-focus-ring": "3px solid color-mix(in srgb,var(--sky) 58%,white)",
    }
    lines = [
        f"/* {GENERATED_HEADER} */",
        f'@font-face{{font-family:"{value_at(tokens, "typography", "fontFamily", "brand")}";src:url("https://terento.app/assets/fonts/instrument-sans.woff2") format("woff2");font-weight:400 700;font-display:swap}}',
        f'@font-face{{font-family:"{value_at(tokens, "typography", "fontFamily", "ui")}";src:url("https://terento.app/assets/fonts/inter-variable.woff2") format("woff2");font-weight:100 900;font-display:swap}}',
        ":root{" + ";".join(f"--{name}:{value}" for name, value in shared.items()) + ";",
    ]
    for name in (
        "statusNeutralSurface", "statusNeutralBorder", "statusNeutralText",
        "statusTestedSurface", "statusTestedBorder", "statusTestedText",
        "statusSupportedSurface", "statusSupportedBorder", "statusSupportedText",
        "statusSuccessSurface", "statusSuccessBorder", "statusSuccessText",
        "statusErrorSurface", "statusErrorBorder", "statusErrorText",
        "errorSurface", "errorText", "successText", "newBadgeSurface", "newBadgeText",
    ):
        lines[-1] += f"--{kebab(name)}:{semantic(tokens, 'admin', 'light', name)};"
    lines[-1] += "}"
    return "\n".join(lines) + "\n"


def replace_site_block(source: str, block: str) -> str:
    start = source.find(SITE_BEGIN)
    end = source.find(SITE_END)
    if start < 0 or end < 0 or end < start:
        raise ValueError(f"{SITE_CSS_PATH} must contain the generated token markers")
    end += len(SITE_END)
    return source[:start] + block.rstrip("\n") + source[end:]


def admin_module(css: str) -> str:
    encoded = json.dumps(css, ensure_ascii=False)
    return (
        '"""Generated admin brand tokens. Do not edit manually; regenerate from JSON."""\n\n'
        f"ADMIN_BRAND_TOKENS_CSS = {encoded}\n"
    )


def expected_outputs(tokens: dict) -> dict[Path, str]:
    site_source = SITE_CSS_PATH.read_text(encoding="utf-8")
    admin_css = admin_token_css(tokens)
    return {
        BRAND_CSS_PATH: canonical_css(tokens),
        APP_TOKENS_PATH: app_swift_tokens(tokens),
        SITE_CSS_PATH: replace_site_block(site_source, site_token_block(tokens)),
        ADMIN_MODULE_PATH: admin_module(admin_css),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when generated outputs are stale")
    args = parser.parse_args()
    try:
        outputs = expected_outputs(load_tokens())
    except (OSError, ValueError) as exc:
        print(f"Brand token generation failed: {exc}", file=sys.stderr)
        return 1
    drift = [path for path, expected in outputs.items() if not path.exists() or path.read_text(encoding="utf-8") != expected]
    if args.check:
        if drift:
            for path in drift:
                print(f"Generated output drift detected: {path}", file=sys.stderr)
            print("Run: python3 scripts/generate-brand-tokens.py", file=sys.stderr)
            return 1
        print("Brand token outputs are up to date.")
        return 0
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print(
        "Generated brand/tokens.css, the app Swift token file, "
        "site/styles.css token block, and admin token module."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
