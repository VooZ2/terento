#!/usr/bin/env python3
"""Add the guide's contextual links to existing public-site surfaces."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUIDE = "guides/install-garmin-maps-mac/"

COPY = {
    "en": {
        "home": "Read the full Mac installation guide.",
        "download_guide": "Read the Mac installation guide",
        "download_compatibility": "Check compatibility",
        "compatibility": "First time installing third-party maps? Read the Mac guide",
        "community_eyebrow": "Community testing",
        "community_heading": "Have another Garmin smartwatch with map support?",
        "community_body": "Try the beta and share the result.",
        "community_download": "Download the beta",
    },
    "de": {
        "home": "Lies die vollständige Mac-Installationsanleitung.",
        "download_guide": "Mac-Installationsanleitung lesen",
        "download_compatibility": "Kompatibilität prüfen",
        "compatibility": "Zum ersten Mal Drittanbieter-Karten installieren? Lies die Mac-Anleitung",
        "community_eyebrow": "Community-Tests",
        "community_heading": "Hast du eine weitere Garmin-Smartwatch mit Kartenunterstützung?",
        "community_body": "Teste die Beta und teile das Ergebnis.",
        "community_download": "Beta herunterladen",
    },
    "fr": {
        "home": "Lisez le guide complet d’installation sur Mac.",
        "download_guide": "Lire le guide d’installation sur Mac",
        "download_compatibility": "Vérifier la compatibilité",
        "compatibility": "Vous installez des cartes tierces pour la première fois ? Lisez le guide Mac",
        "community_eyebrow": "Tests communautaires",
        "community_heading": "Vous avez une autre montre Garmin compatible avec les cartes ?",
        "community_body": "Testez la bêta et partagez le résultat.",
        "community_download": "Télécharger la bêta",
    },
    "pl": {
        "home": "Przeczytaj pełną instrukcję instalacji na Macu.",
        "download_guide": "Przeczytaj instrukcję instalacji na Macu",
        "download_compatibility": "Sprawdź kompatybilność",
        "compatibility": "Instalujesz mapy innych firm pierwszy raz? Przeczytaj instrukcję na Macu",
        "community_eyebrow": "Testy społeczności",
        "community_heading": "Masz inny zegarek Garmin obsługujący mapy?",
        "community_body": "Przetestuj betę i udostępnij wynik.",
        "community_download": "Pobierz wersję beta",
    },
    "cs": {
        "home": "Přečtěte si úplného průvodce instalací na Macu.",
        "download_guide": "Přečíst průvodce instalací na Macu",
        "download_compatibility": "Ověřit kompatibilitu",
        "compatibility": "Instalujete mapy třetích stran poprvé? Přečtěte si průvodce pro Mac",
        "community_eyebrow": "Komunitní testování",
        "community_heading": "Máte jiné hodinky Garmin s podporou map?",
        "community_body": "Vyzkoušejte betu a sdílejte výsledek.",
        "community_download": "Stáhnout betu",
    },
    "it": {
        "home": "Leggi la guida completa all’installazione su Mac.",
        "download_guide": "Leggi la guida all’installazione su Mac",
        "download_compatibility": "Verifica la compatibilità",
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


def download_link(label: str, href: str) -> str:
    """Return an intrinsic-width link whose final word stays with its arrow."""
    prefix, tail = label.rsplit(" ", 1)
    return (
        f'<a class="text-link download-info-link" href="{href}">'
        f'<span class="download-info-link-label">{prefix}</span> '
        '<span class="download-info-link-tail">'
        f'<span class="download-info-link-label">{tail}</span>'
        '<span class="download-info-link-arrow" aria-hidden="true">→</span>'
        '</span></a>'
    )


def normalize_download_layout(source: str) -> str:
    """Bring legacy localized Download markup onto the shared three-column layout."""
    pattern = re.compile(
        r'<div class="download-grid">'
        r'<div class="section-heading"><p class="eyebrow">(?P<label>.*?)</p>'
        r'<h2>(?P<version>.*?)</h2>'
        r'<p class="supporting-copy">(?P<release>.*?)</p></div>'
        r'<div class="download-list">(?P<sections>[\s\S]*?)</div></div>'
    )
    match = pattern.search(source)
    if not match:
        return source
    replacement = (
        f'<p class="download-release">{match.group("label")}: '
        f'<strong>{match.group("version")}</strong> '
        '<span aria-hidden="true">·</span> '
        f'{match.group("release")}</p>'
        f'<div class="download-sections">{match.group("sections")}</div>'
    )
    return source[:match.start()] + replacement + source[match.end():]


def replace_download_section_link(source: str, section_index: int, anchor: str) -> str:
    sections = list(re.finditer(r'<section class="download-item">[\s\S]*?</section>', source))
    if len(sections) < 2:
        raise RuntimeError("Download page must contain at least two information sections")
    match = sections[section_index]
    section = re.sub(
        r'<a class="(?:download-compatibility-link|(?:text-link )?download-info-link)"[\s\S]*?</a>',
        '',
        match.group(0),
    )
    section = section.replace('</section>', f'{anchor}</section>', 1)
    return source[:match.start()] + section + source[match.end():]


def add_home_link(locale: str) -> None:
    path = path_for(locale, "index.html")
    source = path.read_text(encoding="utf-8")
    answer = {
        "en": "Yes. Terento provides a guided native macOS workflow for installing supported third-party maps without BaseCamp or a general-purpose MTP file manager. You can also import a supported third-party .img map from your Mac. Apple Silicon is required.",
        "de": "Ja. Terento bietet einen geführten nativen macOS-Ablauf zum Installieren unterstützter Drittanbieter-Karten ohne BaseCamp oder einen allgemeinen MTP-Dateimanager. Du kannst auch eine unterstützte Drittanbieter-.img-Karte von deinem Mac importieren. Apple Silicon ist erforderlich.",
        "fr": "Oui. Terento propose un parcours macOS natif guidé pour installer des cartes tierces prises en charge, sans BaseCamp ni gestionnaire MTP généraliste. Vous pouvez aussi importer une carte .img tierce prise en charge depuis votre Mac. Apple Silicon est requis.",
        "pl": "Tak. Terento oferuje prowadzony, natywny dla macOS sposób instalowania obsługiwanych map innych firm bez BaseCamp i bez uniwersalnego menedżera plików MTP. Możesz też zaimportować obsługiwaną mapę .img innej firmy z Maca. Wymagany jest Apple Silicon.",
        "cs": "Ano. Terento nabízí řízený nativní postup pro macOS k instalaci podporovaných map třetích stran bez BaseCampu a bez univerzálního správce souborů MTP. Můžete také přímo z Macu importovat podporovanou mapu .img třetí strany. Je vyžadován Apple Silicon.",
        "it": "Sì. Terento offre un flusso nativo guidato per macOS per installare mappe di terze parti supportate, senza BaseCamp né un file manager MTP generico. Puoi anche importare dal Mac una mappa .img di terze parti supportata. È richiesto Apple Silicon.",
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
    source = normalize_download_layout(path.read_text(encoding="utf-8"))
    guide = download_link(COPY[locale]["download_guide"], localized_guide(locale))
    compatibility = download_link(
        COPY[locale]["download_compatibility"],
        localized_compatibility(locale),
    )
    source = replace_download_section_link(source, 1, compatibility)
    source = replace_download_section_link(source, 0, guide)
    path.write_text(source, encoding="utf-8")


def add_compatibility_link(locale: str) -> None:
    path = path_for(locale, "compatibility/index.html")
    source = path.read_text(encoding="utf-8")
    if 'class="compatibility-hero-copy"' not in source:
        source, hero_count = re.subn(
            r'(<section class="compatibility-hero"[^>]*>\s*<div class="shell compatibility-hero-inner">)([\s\S]*?)(</div>\s*</section>)',
            r'\1<div class="compatibility-hero-copy">\2</div>\3',
            source,
            count=1,
        )
        if not hero_count:
            raise RuntimeError(f"Compatibility hero not found for {locale}")
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
