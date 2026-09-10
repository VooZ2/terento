#!/usr/bin/env python3
"""Render the API-driven compatibility shell into every public locale page."""

from __future__ import annotations

import html
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCALES = ("en", "de", "fr", "pl", "cs", "it")

COPY = {
    "en": {
        "loading": "Loading live compatibility evidence…",
        "model_many": "models with evidence",
        "successes": "successful installs",
        "more": "More models ready for testing",
        "latest": "Latest installation",
        "retry": "Retry",
        "clear": "Clear filters",
        "no_match": "No models match these filters.",
        "noscript": "Enable JavaScript to load the current compatibility results.",
    },
    "de": {
        "loading": "Aktuelle Kompatibilitätsnachweise werden geladen…",
        "model_many": "Modelle mit Nachweis",
        "successes": "erfolgreiche Installationen",
        "more": "Weitere Modelle zum Testen",
        "latest": "Letzte Installation",
        "retry": "Erneut versuchen",
        "clear": "Filter zurücksetzen",
        "no_match": "Keine Modelle passen zu diesen Filtern.",
        "noscript": "Aktiviere JavaScript, um die aktuellen Kompatibilitätsergebnisse zu laden.",
    },
    "fr": {
        "loading": "Chargement des données de compatibilité en direct…",
        "model_many": "modèles avec preuve",
        "successes": "installations réussies",
        "more": "D’autres modèles prêts à être testés",
        "latest": "Dernière installation",
        "retry": "Réessayer",
        "clear": "Effacer les filtres",
        "no_match": "Aucun modèle ne correspond à ces filtres.",
        "noscript": "Activez JavaScript pour charger les résultats de compatibilité actuels.",
    },
    "pl": {
        "loading": "Ładowanie aktualnych danych o kompatybilności…",
        "model_many": "modele z potwierdzeniem",
        "successes": "udanych instalacji",
        "more": "Kolejne modele gotowe do testów",
        "latest": "Ostatnia instalacja",
        "retry": "Spróbuj ponownie",
        "clear": "Wyczyść filtry",
        "no_match": "Żaden model nie pasuje do tych filtrów.",
        "noscript": "Włącz JavaScript, aby załadować aktualne wyniki kompatybilności.",
    },
    "cs": {
        "loading": "Načítají se aktuální údaje o kompatibilitě…",
        "model_many": "modely s ověřením",
        "successes": "úspěšných instalací",
        "more": "Další modely připravené k testování",
        "latest": "Poslední instalace",
        "retry": "Zkusit znovu",
        "clear": "Vymazat filtry",
        "no_match": "Žádný model neodpovídá těmto filtrům.",
        "noscript": "Pro načtení aktuálních výsledků kompatibility povolte JavaScript.",
    },
    "it": {
        "loading": "Caricamento dei dati di compatibilità aggiornati…",
        "model_many": "modelli con evidenze",
        "successes": "installazioni riuscite",
        "more": "Altri modelli pronti per i test",
        "latest": "Ultima installazione",
        "retry": "Riprova",
        "clear": "Cancella filtri",
        "no_match": "Nessun modello corrisponde a questi filtri.",
        "noscript": "Abilita JavaScript per caricare i risultati di compatibilità aggiornati.",
    },
}


def page_path(locale: str) -> Path:
    return ROOT / (
        "site/compatibility/index.html"
        if locale == "en"
        else f"site/{locale}/compatibility/index.html"
    )


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def summary_markup(locale: str) -> str:
    copy = COPY[locale]
    return f'''<div class="compatibility-summary" id="compatibility-summary" aria-live="polite" aria-busy="true">
  <p class="compatibility-summary-line compatibility-summary-loading" data-summary-loading role="status">{escape(copy["loading"])}</p>
  <p class="compatibility-summary-line" data-summary-content hidden style="display:none">
    <span class="compatibility-summary-item"><strong data-summary="models"></strong> <span data-summary-model-label>{escape(copy["model_many"])}</span> <span class="compatibility-summary-separator" aria-hidden="true">·</span></span>
    <span class="compatibility-summary-item"><strong data-summary="successes"></strong> {escape(copy["successes"])} <span class="compatibility-summary-separator" aria-hidden="true">·</span></span>
    <span class="compatibility-summary-item compatibility-summary-more">{escape(copy["more"])} <span class="compatibility-summary-separator" aria-hidden="true">·</span></span>
    <span class="compatibility-summary-item compatibility-summary-updated" data-summary-updated hidden>{escape(copy["latest"])} <time data-summary="updated"></time></span>
  </p>
  <p class="compatibility-freshness" role="status"><span id="compatibility-freshness">{escape(copy["loading"])}</span> <button type="button" id="compatibility-retry" hidden>{escape(copy["retry"])}</button></p>
</div>'''


def render_page(source: str, locale: str) -> str:
    copy = COPY[locale]
    source = re.sub(
        r'<button[^>]*id="compatibility-clear"[^>]*>[\s\S]*?</button>\s*',
        "",
        source,
    )

    summary_pattern = (
        r'<div class="compatibility-summary" id="compatibility-summary"[\s\S]*?'
        r'</div>\s*(?=<details class="compatibility-how")'
    )
    source, summary_count = re.subn(
        summary_pattern,
        summary_markup(locale) + "\n\n          ",
        source,
        count=1,
    )
    if summary_count != 1:
        raise ValueError(f"{page_path(locale)}: compatibility summary insertion point not found")

    grid_start = source.find('<p class="compatibility-results-count" id="results-count"')
    if grid_start < 0:
        grid_start = source.find('<div class="watch-grid" id="watch-grid"')
    grid_end = source.find('<p class="compatibility-empty"', grid_start)
    if grid_start < 0 or grid_end < 0:
        raise ValueError(f"{page_path(locale)}: compatibility grid insertion point not found")
    dynamic_shell = (
        '<p class="compatibility-results-count" id="results-count" aria-live="polite"></p>\n'
        '          <div class="watch-grid" id="watch-grid" aria-live="polite" aria-busy="true"></div>\n'
        f'          <noscript class="compatibility-noscript"><p>{escape(copy["noscript"])}</p></noscript>\n'
        '          '
    )
    source = source[:grid_start] + dynamic_shell + source[grid_end:]

    source = re.sub(
        r'<script type="application/json" id="compatibility-snapshot">[\s\S]*?</script>\s*',
        "",
        source,
    )
    source = source.replace(
        '<p class="compatibility-results-count"',
        f'<button type="button" class="compatibility-clear" id="compatibility-clear">{escape(copy["clear"])}</button>\n          <p class="compatibility-results-count"',
        1,
    )
    source = re.sub(
        r'(<p class="compatibility-empty"[^>]*>)[^<]*(</p>)',
        lambda match: match[1] + escape(copy["no_match"]) + match[2],
        source,
    )
    return source


def main() -> None:
    for locale in LOCALES:
        path = page_path(locale)
        source = path.read_text(encoding="utf-8")
        path.write_text(render_page(source, locale), encoding="utf-8")
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
