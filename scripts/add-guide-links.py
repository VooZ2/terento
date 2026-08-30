#!/usr/bin/env python3
"""Add the guide's contextual links to existing public-site surfaces."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUIDE = "guides/install-garmin-maps-mac/"

COPY = {
    "en": {
        "home": "Read the full Mac installation guide.",
        "download": "New to third-party maps? Read the Mac installation guide",
        "compatibility": "First time installing third-party maps? Read the Mac guide",
        "community_eyebrow": "Community testing",
        "community_heading": "Have another Garmin smartwatch with map support?",
        "community_body": "Try the beta and share the result.",
        "community_download": "Download the beta",
    },
    "de": {
        "home": "Lies die vollständige Mac-Installationsanleitung.",
        "download": "Neu bei Drittanbieter-Karten? Lies die Mac-Installationsanleitung",
        "compatibility": "Zum ersten Mal Drittanbieter-Karten installieren? Lies die Mac-Anleitung",
        "community_eyebrow": "Community-Tests",
        "community_heading": "Hast du eine weitere Garmin-Smartwatch mit Kartenunterstützung?",
        "community_body": "Teste die Beta und teile das Ergebnis.",
        "community_download": "Beta herunterladen",
    },
    "fr": {
        "home": "Lisez le guide complet d’installation sur Mac.",
        "download": "Vous débutez avec les cartes tierces ? Lisez le guide d’installation sur Mac",
        "compatibility": "Vous installez des cartes tierces pour la première fois ? Lisez le guide Mac",
        "community_eyebrow": "Tests communautaires",
        "community_heading": "Vous avez une autre montre Garmin compatible avec les cartes ?",
        "community_body": "Testez la bêta et partagez le résultat.",
        "community_download": "Télécharger la bêta",
    },
    "pl": {
        "home": "Przeczytaj pełną instrukcję instalacji na Macu.",
        "download": "Dopiero zaczynasz z mapami innych firm? Przeczytaj instrukcję instalacji na Macu",
        "compatibility": "Instalujesz mapy innych firm pierwszy raz? Przeczytaj instrukcję na Macu",
        "community_eyebrow": "Testy społeczności",
        "community_heading": "Masz inny zegarek Garmin obsługujący mapy?",
        "community_body": "Przetestuj betę i udostępnij wynik.",
        "community_download": "Pobierz wersję beta",
    },
    "cs": {
        "home": "Přečtěte si úplného průvodce instalací na Macu.",
        "download": "Začínáte s mapami třetích stran? Přečtěte si průvodce instalací na Macu",
        "compatibility": "Instalujete mapy třetích stran poprvé? Přečtěte si průvodce pro Mac",
        "community_eyebrow": "Komunitní testování",
        "community_heading": "Máte jiné hodinky Garmin s podporou map?",
        "community_body": "Vyzkoušejte betu a sdílejte výsledek.",
        "community_download": "Stáhnout betu",
    },
    "it": {
        "home": "Leggi la guida completa all’installazione su Mac.",
        "download": "È la prima volta che installi mappe di terze parti? Leggi la guida per Mac",
        "compatibility": "Installi mappe di terze parti per la prima volta? Leggi la guida per Mac",
        "community_eyebrow": "Test della community",
        "community_heading": "Hai un altro smartwatch Garmin con supporto mappe?",
        "community_body": "Prova la beta e condividi il risultato.",
        "community_download": "Scarica la beta",
    },
}


def path_for(locale: str, suffix: str) -> Path:
    return ROOT / "site" / (suffix if locale == "en" else f"{locale}/{suffix}")


def localized_guide(locale: str) -> str:
    return f"/{'' if locale == 'en' else f'{locale}/'}{GUIDE}"


def localized_download(locale: str) -> str:
    return f"/{'' if locale == 'en' else f'{locale}/'}download/"


def localized_compatibility(locale: str) -> str:
    return f"/{'' if locale == 'en' else f'{locale}/'}compatibility/"


def add_home_link(locale: str) -> None:
    path = path_for(locale, "index.html")
    source = path.read_text(encoding="utf-8")
    answer = {
        "en": "Yes. Terento provides a guided native macOS workflow for installing supported third-party maps without BaseCamp or a general-purpose MTP file manager. The current beta uses Freizeitkarte and requires an Apple Silicon Mac.",
        "de": "Ja. Terento bietet einen geführten nativen macOS-Ablauf zum Installieren unterstützter Drittanbieter-Karten ohne BaseCamp oder einen allgemeinen MTP-Dateimanager. Die aktuelle Beta verwendet Freizeitkarte und erfordert einen Apple-Silicon-Mac.",
        "fr": "Oui. Terento propose un parcours macOS natif guidé pour installer des cartes tierces prises en charge, sans BaseCamp ni gestionnaire MTP généraliste. La bêta actuelle utilise Freizeitkarte et nécessite un Mac Apple Silicon.",
        "pl": "Tak. Terento oferuje prowadzony, natywny dla macOS sposób instalowania obsługiwanych map innych firm bez BaseCamp i bez uniwersalnego menedżera plików MTP. Obecna beta korzysta z Freizeitkarte i wymaga Maca z Apple Silicon.",
        "cs": "Ano. Terento nabízí řízený nativní postup pro macOS k instalaci podporovaných map třetích stran bez BaseCampu a bez univerzálního správce souborů MTP. Aktuální beta používá Freizeitkarte a vyžaduje Mac s Apple Silicon.",
        "it": "Sì. Terento offre un flusso nativo guidato per macOS per installare mappe di terze parti supportate, senza BaseCamp né un file manager MTP generico. La beta attuale usa Freizeitkarte e richiede un Mac Apple Silicon.",
    }[locale]
    sentence = COPY[locale]["home"]
    visible = f'<p>{answer}</p>'
    visible_with_link = f'<p>{answer} <a href="{localized_guide(locale)}">{sentence}</a></p>'
    if visible in source:
        source = source.replace(visible, visible_with_link, 1)
    json_answer = f'"text": "{answer}"'
    json_with_link = f'"text": "{answer} {sentence}"'
    if json_answer in source:
        source = source.replace(json_answer, json_with_link, 1)
    path.write_text(source, encoding="utf-8")


def add_download_link(locale: str) -> None:
    path = path_for(locale, "download/index.html")
    source = path.read_text(encoding="utf-8")
    marker = '<div class="download-sections">' if '<div class="download-sections">' in source else '<div class="download-grid">'
    start = source.index(marker)
    end = source.index("</ul>", start) + len("</ul>")
    anchor = f'<a class="download-compatibility-link" href="{localized_guide(locale)}">{COPY[locale]["download"]} <span aria-hidden="true">→</span></a>'
    if anchor not in source:
        source = source[:end] + anchor + source[end:]
    path.write_text(source, encoding="utf-8")


def add_compatibility_link(locale: str) -> None:
    path = path_for(locale, "compatibility/index.html")
    source = path.read_text(encoding="utf-8")
    guide = f'<a class="text-link compatibility-guide-link" href="{localized_guide(locale)}">{COPY[locale]["compatibility"]} <span aria-hidden="true">→</span></a>'
    download = f'<a class="download-action download-action-primary compatibility-community-link" href="{localized_download(locale)}" data-umami-event="download-cta-click" data-umami-event-location="compatibility-community-testing">{COPY[locale]["community_download"]}</a>'
    community = (
        '<div class="compatibility-community-cta">'
        '<div class="compatibility-community-copy">'
        f'<p class="eyebrow">{COPY[locale]["community_eyebrow"]}</p>'
        f'<h2>{COPY[locale]["community_heading"]}</h2>'
        f'<p>{COPY[locale]["community_body"]}</p>'
        f'{guide}'
        '</div>'
        f'{download}'
        '</div></div></section>'
    )
    source = re.sub(
        r'<div class="compatibility-community-cta">[\s\S]*?</div>\s*</div>\s*</section>',
        community,
        source,
        count=1,
    )
    path.write_text(source, encoding="utf-8")


def main() -> None:
    for locale in COPY:
        add_home_link(locale)
        add_download_link(locale)
        add_compatibility_link(locale)
    print("Added guide links to Home FAQ, Download requirements, and Compatibility testing surfaces.")


if __name__ == "__main__":
    main()
