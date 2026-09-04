#!/usr/bin/env python3
"""Render the checked-in compatibility snapshot into all public locale pages."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "site/compatibility/public-models.snapshot.json"
LOCALES = ("en", "de", "fr", "pl", "cs", "it")
STATUS_CODES = ("VERIFIED", "SUPPORTED", "TESTED", "TESTING")
FALLBACK_IMAGE_URL = "/assets/generic-garmin-watch.png?v=20260826-1"

COPY = {
    "en": {
        "model_one": "model with evidence",
        "model_many": "models with evidence",
        "successes": "successful installs",
        "results_one": "model",
        "results_many": "models",
        "latest": "Latest installation",
        "snapshot_intro": "Latest compatibility snapshot based on real Terento installations:",
        "statuses": {"VERIFIED": "Verified", "SUPPORTED": "Supported", "TESTED": "Tested", "TESTING": "Testing"},
    },
    "de": {
        "model_one": "Modell mit Nachweis",
        "model_many": "Modelle mit Nachweis",
        "successes": "erfolgreiche Installationen",
        "results_one": "Modell",
        "results_many": "Modelle",
        "latest": "Letzte Installation",
        "snapshot_intro": "Aktueller Kompatibilitäts-Snapshot auf Grundlage echter Terento-Installationen:",
        "statuses": {"VERIFIED": "Bestätigt", "SUPPORTED": "Unterstützt", "TESTED": "Getestet", "TESTING": "In Prüfung"},
    },
    "fr": {
        "model_one": "modèle avec preuve",
        "model_many": "modèles avec preuve",
        "successes": "installations réussies",
        "results_one": "modèle",
        "results_many": "modèles",
        "latest": "Dernière installation",
        "snapshot_intro": "Dernier snapshot de compatibilité basé sur des installations réelles avec Terento :",
        "statuses": {"VERIFIED": "Vérifiée", "SUPPORTED": "Prise en charge", "TESTED": "Testée", "TESTING": "En test"},
    },
    "pl": {
        "model_one": "model z potwierdzeniem",
        "model_many": "modele z potwierdzeniem",
        "successes": "udanych instalacji",
        "results_one": "model",
        "results_many": "modeli",
        "latest": "Ostatnia instalacja",
        "snapshot_intro": "Najnowszy snapshot kompatybilności na podstawie rzeczywistych instalacji Terento:",
        "statuses": {"VERIFIED": "Potwierdzona", "SUPPORTED": "Obsługiwana", "TESTED": "Przetestowana", "TESTING": "W trakcie testów"},
    },
    "cs": {
        "model_one": "model s ověřením",
        "model_many": "modely s ověřením",
        "successes": "úspěšných instalací",
        "results_one": "model",
        "results_many": "modelů",
        "latest": "Poslední instalace",
        "snapshot_intro": "Nejnovější snapshot kompatibility podle skutečných instalací Terento:",
        "statuses": {"VERIFIED": "Ověřeno", "SUPPORTED": "Podporováno", "TESTED": "Testováno", "TESTING": "Testování"},
    },
    "it": {
        "model_one": "modello con evidenze",
        "model_many": "modelli con evidenze",
        "successes": "installazioni riuscite",
        "results_one": "modello",
        "results_many": "modelli",
        "latest": "Ultima installazione",
        "snapshot_intro": "Ultimo snapshot della compatibilità basato su installazioni reali con Terento:",
        "statuses": {"VERIFIED": "Verificata", "SUPPORTED": "Supportata", "TESTED": "Testata", "TESTING": "In test"},
    },
}


def page_path(locale: str) -> Path:
    return ROOT / ("site/compatibility/index.html" if locale == "en" else f"site/{locale}/compatibility/index.html")


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def public_model_name(value: object) -> str:
    label = str(value or "").strip()
    label = re.sub(r"^Garmin\s+", "", label, flags=re.IGNORECASE)
    without_variant = re.sub(
        r"\s*(?:[·•|:]\s*|[-–—]\s*)?\d{2}\s*mm(?:\s*,?\s*(?:AMOLED|Solar|microLED))?\s*$",
        "",
        label,
        flags=re.IGNORECASE,
    )
    without_variant = re.sub(
        r"\s*(?:[·•|:]\s*|[-–—]\s*)?(?:AMOLED|Solar|microLED)\s*$",
        "",
        without_variant,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", without_variant).strip() or label


def variant_label(row: dict) -> str:
    source = f"{row.get('variant', '')} {row.get('model', '')}"
    size_value = row.get("caseSizeMm", row.get("case_size_mm"))
    try:
        size = f"{int(size_value)} mm" if int(size_value) > 0 else ""
    except (TypeError, ValueError):
        size_match = re.search(r"\b(\d{2})\s*mm\b", source, flags=re.IGNORECASE)
        size = f"{int(size_match.group(1))} mm" if size_match else ""
    display_value = str(row.get("displayType", row.get("display_type", "")) or "").strip()
    display_match = re.search(r"\b(amoled|solar|microled)\b", display_value or source, flags=re.IGNORECASE)
    display = display_match.group(1).upper() if display_match else ""
    if display.lower() == "microled":
        display = "microLED"
    exact = [part for part in (size, display) if part]
    if exact:
        return ", ".join(exact)
    raw = str(row.get("variant", "") or "").strip()
    return re.sub(r"\s*(?:·|\||/)\s*", ", ", raw) or "Smartwatch"


def parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def format_date(value: object, locale: str) -> str:
    date = parse_datetime(value)
    if not date:
        return ""
    months = {
        "fr": ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."),
        "pl": ("sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"),
        "it": ("gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"),
    }
    if locale == "en":
        return f"{months_en[date.month - 1]} {date.day}, {date.year}"
    if locale == "de":
        return f"{date.day:02d}.{date.month:02d}.{date.year}"
    if locale == "fr":
        return f"{date.day} {months['fr'][date.month - 1]} {date.year}"
    if locale == "pl":
        return f"{date.day} {months['pl'][date.month - 1]} {date.year}"
    if locale == "cs":
        return f"{date.day}. {date.month}. {date.year}"
    return f"{date.day} {months['it'][date.month - 1]} {date.year}"


months_en = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def successful_install_label(count: int, locale: str) -> str:
    if locale == "en":
        return f"{count} successful install{'s' if count != 1 else ''}"
    if locale == "de":
        return f"{count} erfolgreiche Installation{'en' if count != 1 else ''}"
    if locale == "fr":
        return f"{count} installation{'s' if count != 1 else ''} réussie{'s' if count != 1 else ''}"
    if locale == "pl":
        return f"{count} {'udana instalacja' if count == 1 else 'udanych instalacji'}"
    if locale == "cs":
        return f"{count} {'úspěšná instalace' if count == 1 else 'úspěšných instalací'}"
    return f"{count} installazione{'i' if count != 1 else ''} riuscita{'e' if count != 1 else ''}"


def load_snapshot() -> dict:
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1 or not isinstance(payload.get("generatedAt"), str):
        raise ValueError("compatibility snapshot must use schemaVersion 1 and generatedAt")
    models = payload.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("compatibility snapshot models must be a non-empty array")
    identities = set()
    for row in models:
        if not isinstance(row, dict):
            raise ValueError("compatibility snapshot model rows must be objects")
        identity = str(row.get("compatibilityIdentity") or row.get("model") or "").strip()
        status = str(row.get("evidenceStatus") or row.get("status") or "").upper()
        attempted = row.get("attemptedInstallations", row.get("attempted", 0))
        successful = row.get("successfulInstallations", row.get("successful", 0))
        if not identity or identity in identities:
            raise ValueError(f"compatibility snapshot has missing or duplicate identity: {identity!r}")
        if status not in STATUS_CODES:
            raise ValueError(f"compatibility snapshot has unsupported status: {status!r}")
        if not isinstance(attempted, int) or not isinstance(successful, int) or attempted < 1 or successful < 1 or successful > attempted:
            raise ValueError(f"compatibility snapshot has invalid evidence counts for {identity!r}")
        identities.add(identity)
    return payload


def normalized_rows(payload: dict) -> list[dict]:
    rows = []
    for source in payload["models"]:
        row = dict(source)
        row["status"] = str(row.get("evidenceStatus") or row.get("status") or "").upper()
        row["modelName"] = public_model_name(row.get("model"))
        row["variantLabel"] = variant_label(row)
        row["successful"] = int(row.get("successfulInstallations", row.get("successful", 0)))
        row["attempted"] = int(row.get("attemptedInstallations", row.get("attempted", 0)))
        row["lastSuccess"] = row.get("lastSuccessfulInstallation") or row.get("lastSuccess")
        row["familyName"] = str(row.get("familyName") or row.get("family") or "Other").strip()
        row["imageUrl"] = str((row.get("image") or {}).get("url") or row.get("imageUrl") or FALLBACK_IMAGE_URL)
        rows.append(row)
    return sorted(rows, key=lambda row: (-row["attempted"], -row["successful"], row["modelName"].casefold(), row["variantLabel"].casefold()))


def card_markup(row: dict, locale: str) -> str:
    copy = COPY[locale]
    status = row["status"]
    status_label = copy["statuses"][status]
    install_label = successful_install_label(row["successful"], locale)
    latest = format_date(row["lastSuccess"], locale)
    latest_markup = f'<p class="watch-card-meta">{escape(copy["latest"])} {escape(latest)}</p>' if latest else ""
    accessible = ", ".join(filter(None, [row["modelName"], row["variantLabel"], status_label, install_label, f'{copy["latest"]} {latest}' if latest else ""]))
    return f'''<article class="watch-card" aria-label="{escape(accessible)}">
  <div class="watch-card-image"><img class="is-ready" data-remote-src="{escape(row["imageUrl"])}" src="{escape(row["imageUrl"])}" alt="" loading="lazy"></div>
  <div class="watch-card-body">
    <div class="watch-card-heading">
      <p class="watch-family">{escape(row["familyName"])}</p>
      <div class="watch-card-model-row"><h3>{escape(row["modelName"])}</h3><span class="status-badge status-{status.lower()}" aria-label="{escape(status_label)}"><span>{escape(status_label)}</span></span></div>
      <p class="watch-variant">{escape(row["variantLabel"])}</p>
    </div>
    <p class="watch-install-count">{escape(install_label)}</p>
    {latest_markup}
  </div>
</article>'''


def static_results(rows: list[dict], locale: str) -> tuple[int, str, str]:
    copy = COPY[locale]
    count = len(rows)
    successes = sum(row["successful"] for row in rows)
    latest = max((parse_datetime(row["lastSuccess"]) for row in rows if parse_datetime(row["lastSuccess"])), default=None)
    latest_raw = latest.isoformat() if latest else ""
    latest_visible = format_date(latest_raw, locale)
    model_label = copy["model_one"] if count == 1 else copy["model_many"]
    results_label = copy["results_one"] if count == 1 else copy["results_many"]
    summary = f'''<div class="compatibility-summary" id="compatibility-summary" aria-live="polite" aria-busy="false">
  <p class="compatibility-summary-line compatibility-summary-loading" data-summary-loading role="status" hidden style="display:none">Loading compatibility evidence…</p>
  <p class="compatibility-summary-line" data-summary-content>
    <span class="compatibility-summary-item"><strong data-summary="models">{count}</strong> <span data-summary-model-label>{escape(model_label)}</span> <span class="compatibility-summary-separator" aria-hidden="true">·</span></span>
    <span class="compatibility-summary-item"><strong data-summary="successes">{successes}</strong> {escape(copy["successes"])} <span class="compatibility-summary-separator" aria-hidden="true">·</span></span>
    <span class="compatibility-summary-item compatibility-summary-more">More models ready for testing <span class="compatibility-summary-separator" aria-hidden="true">·</span></span>
    <span class="compatibility-summary-item compatibility-summary-updated" data-summary-updated{' hidden' if not latest_visible else ''}>{escape('Updated' if locale == 'en' else {'de': 'Aktualisiert', 'fr': 'Mis à jour', 'pl': 'Zaktualizowano', 'cs': 'Aktualizováno', 'it': 'Aggiornato'}[locale])} <time data-summary="updated" datetime="{escape(latest_raw)}">{escape(latest_visible)}</time></span>
  </p>
</div>'''
    results_count = f'<p class="compatibility-results-count" id="results-count" aria-live="polite">{count} {escape(results_label)}</p>'
    return summary, results_count


def noscript_markup(rows: list[dict], locale: str) -> str:
    copy = COPY[locale]
    items = "\n".join(
        f'  <li><strong>{escape(row["modelName"])}</strong> — {escape(row["variantLabel"])} — {escape(copy["statuses"][row["status"]])} — {escape(successful_install_label(row["successful"], locale))}</li>'
        for row in rows
    )
    return f'''<noscript class="compatibility-noscript">
  <p>{escape(copy["snapshot_intro"])}</p>
  <ul>{items}</ul>
</noscript>'''


def snapshot_script(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return f'<script type="application/json" id="compatibility-snapshot">{encoded}</script>'


def render_page(source: str, locale: str, payload: dict) -> str:
    rows = normalized_rows(payload)
    summary, results_count = static_results(rows, locale)
    cards = "\n".join(card_markup(row, locale) for row in rows)
    grid = f'<div class="watch-grid" id="watch-grid" aria-live="polite" aria-busy="false">{cards}</div>'
    noscript = noscript_markup(rows, locale)

    malformed_summary_marker = re.compile(
        r'<div class="compatibility-summary" id="compatibility-summary"[^>]*>\s*<details class="compatibility-how"'
    )
    malformed_summary = malformed_summary_marker.search(source) is not None
    if malformed_summary:
        source, cleanup_count = re.subn(
            r'<p class="compatibility-summary-line compatibility-summary-loading"[\s\S]*?</p>\s*'
            r'<p class="compatibility-summary-line" data-summary-content[\s\S]*?</p>\s*</div>\s*'
            r'<p class="compatibility-results-count" id="results-count"[^>]*>[\s\S]*?</p>\s*',
            "",
            source,
            count=1,
        )
        if cleanup_count != 1:
            raise ValueError(f"{page_path(locale)}: malformed compatibility snapshot cleanup failed")

    if malformed_summary:
        source, summary_count = re.subn(
            r'<div class="compatibility-summary" id="compatibility-summary"[^>]*>\s*(?=<details class="compatibility-how")',
            summary + "\n\n          ",
            source,
            count=1,
        )
    else:
        summary_pattern = r'<div class="compatibility-summary" id="compatibility-summary"[\s\S]*?</div>\s*(?=<details class="compatibility-how")'
        source, summary_count = re.subn(summary_pattern, summary + "\n\n          ", source, count=1)
    if summary_count != 1:
        raise ValueError(f"{page_path(locale)}: compatibility summary insertion point not found")

    grid_start = source.find('<p class="compatibility-results-count" id="results-count"')
    if grid_start < 0:
        grid_start = source.find('<div class="watch-grid" id="watch-grid"')
    grid_end = source.find('<p class="compatibility-empty"', grid_start)
    if grid_start < 0 or grid_end < 0:
        raise ValueError(f"{page_path(locale)}: compatibility grid insertion point not found")
    source = source[:grid_start] + results_count + "\n          " + grid + "\n          " + noscript + "\n          " + source[grid_end:]

    script_pattern = r'<script type="application/json" id="compatibility-snapshot">[\s\S]*?</script>\s*'
    source, script_count = re.subn(script_pattern, snapshot_script(payload) + "\n    ", source, count=1)
    if script_count == 0:
        marker = '<script defer src="/compatibility/compatibility.js?'
        if marker not in source:
            raise ValueError(f"{page_path(locale)}: compatibility script insertion point not found")
        source = source.replace(marker, snapshot_script(payload) + "\n    " + marker, 1)
    return source


def main() -> None:
    payload = load_snapshot()
    for locale in LOCALES:
        path = page_path(locale)
        source = path.read_text(encoding="utf-8")
        path.write_text(render_page(source, locale, payload), encoding="utf-8")
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
