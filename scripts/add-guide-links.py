#!/usr/bin/env python3
"""Add the guide's contextual links to existing public-site surfaces."""

import html
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUIDE = "guides/install-garmin-maps-mac/"

COPY = {
    "en": {
        "home": "Read the full Mac installation guide.",
        "download_guide": "Read the Mac installation guide",
        "download_compatibility": "Check compatibility",
        "download_details_eyebrow": "Before you install",
        "download_details_title": "Check the essentials first.",
        "compatibility": "First time installing third-party maps? Read the Mac guide",
        "community_eyebrow": "Community testing",
        "community_heading": "Have another Garmin smartwatch with map support?",
        "community_body": "Try the beta and share the result.",
        "community_download": "Download",
        "evidence_note": "These counts come from successful installations shared with Terento. They are not Garmin certification.",
    },
    "de": {
        "home": "Lies die vollständige Mac-Installationsanleitung.",
        "download_guide": "Mac-Installationsanleitung lesen",
        "download_compatibility": "Kompatibilität prüfen",
        "download_details_eyebrow": "Vor der Installation",
        "download_details_title": "Prüfe zuerst die wichtigsten Voraussetzungen.",
        "compatibility": "Zum ersten Mal Drittanbieter-Karten installieren? Lies die Mac-Anleitung",
        "community_eyebrow": "Community-Tests",
        "community_heading": "Hast du eine weitere Garmin-Smartwatch mit Kartenunterstützung?",
        "community_body": "Teste die Beta und teile das Ergebnis.",
        "community_download": "Herunterladen",
        "evidence_note": "Diese Zahlen stammen aus erfolgreichen Installationen, die mit Terento geteilt wurden. Sie sind keine Garmin-Zertifizierung.",
    },
    "fr": {
        "home": "Lisez le guide complet d’installation sur Mac.",
        "download_guide": "Lire le guide d’installation sur Mac",
        "download_compatibility": "Vérifier la compatibilité",
        "download_details_eyebrow": "Avant l’installation",
        "download_details_title": "Vérifiez l’essentiel avant de commencer.",
        "compatibility": "Vous installez des cartes tierces pour la première fois ? Lisez le guide Mac",
        "community_eyebrow": "Tests communautaires",
        "community_heading": "Vous avez une autre montre Garmin compatible avec les cartes ?",
        "community_body": "Testez la bêta et partagez le résultat.",
        "community_download": "Télécharger",
        "evidence_note": "Ces chiffres proviennent d’installations réussies partagées avec Terento. Ils ne constituent pas une certification Garmin.",
    },
    "pl": {
        "home": "Przeczytaj pełną instrukcję instalacji na Macu.",
        "download_guide": "Przeczytaj instrukcję instalacji na Macu",
        "download_compatibility": "Sprawdź kompatybilność",
        "download_details_eyebrow": "Przed instalacją",
        "download_details_title": "Sprawdź najważniejsze informacje.",
        "compatibility": "Instalujesz mapy innych firm pierwszy raz? Przeczytaj instrukcję na Macu",
        "community_eyebrow": "Testy społeczności",
        "community_heading": "Masz inny zegarek Garmin obsługujący mapy?",
        "community_body": "Przetestuj betę i udostępnij wynik.",
        "community_download": "Pobierz",
        "evidence_note": "Te dane pochodzą z udanych instalacji udostępnionych Terento. Nie są certyfikatem firmy Garmin.",
    },
    "cs": {
        "home": "Přečtěte si úplného průvodce instalací na Macu.",
        "download_guide": "Přečíst průvodce instalací na Macu",
        "download_compatibility": "Ověřit kompatibilitu",
        "download_details_eyebrow": "Před instalací",
        "download_details_title": "Nejdřív si ověřte to podstatné.",
        "compatibility": "Instalujete mapy třetích stran poprvé? Přečtěte si průvodce pro Mac",
        "community_eyebrow": "Komunitní testování",
        "community_heading": "Máte jiné hodinky Garmin s podporou map?",
        "community_body": "Vyzkoušejte betu a sdílejte výsledek.",
        "community_download": "Stáhnout",
        "evidence_note": "Tato čísla pocházejí z úspěšných instalací sdílených s Terento. Nejde o certifikaci Garmin.",
    },
    "it": {
        "home": "Leggi la guida completa all’installazione su Mac.",
        "download_guide": "Leggi la guida all’installazione su Mac",
        "download_compatibility": "Verifica la compatibilità",
        "download_details_eyebrow": "Prima dell’installazione",
        "download_details_title": "Controlla i requisiti essenziali.",
        "compatibility": "Installi mappe di terze parti per la prima volta? Leggi la guida per Mac",
        "community_eyebrow": "Test della community",
        "community_heading": "Hai un altro smartwatch Garmin con supporto mappe?",
        "community_body": "Prova la beta e condividi il risultato.",
        "community_download": "Scarica",
        "evidence_note": "Questi dati provengono da installazioni riuscite condivise con Terento. Non sono una certificazione Garmin.",
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


def download_link(label: str, href: str, *, event=None, location=None) -> str:
    """Return an intrinsic-width link whose final word stays with its arrow."""
    prefix, tail = label.rsplit(" ", 1)
    attributes = ""
    if event:
        attributes += f' data-umami-event="{html.escape(event, quote=True)}"'
    if location:
        attributes += f' data-umami-event-location="{html.escape(location, quote=True)}"'
    return (
        f'<a class="text-link download-info-link" href="{href}"{attributes}>'
        f'<span class="download-info-link-label">{prefix}</span> '
        '<span class="download-info-link-tail">'
        f'<span class="download-info-link-label">{tail}</span>'
        '<span class="download-info-link-arrow" aria-hidden="true">→</span>'
        '</span></a>'
    )


def normalize_download_layout(source: str, locale: str) -> str:
    """Bring Download pages onto a focused actions + technical-details layout."""
    source = re.sub(r'\s*<p class="download-trust">[\s\S]*?</p>', '', source, count=1)
    if 'class="download-layout"' in source or 'class="download-hero"' in source:
        source = re.sub(r'<div class="download-visual">[\s\S]*?</div>', '', source, count=1)
        source = source.replace('class="download-layout"', 'class="download-hero"', 1)
        source = re.sub(
            r'(<p class="download-intro">[^<]*)\s*<strong>[^<]*</strong>',
            r'\1',
            source,
            count=1,
        )
        source = re.sub(
            r'(<div class="download-copy">[\s\S]*?)\s*<p class="download-requirement">[\s\S]*?</p>',
            r'\1',
            source,
            count=1,
        )
        source = re.sub(
            r'(<div class="download-actions">[\s\S]*?<a class=")[^"]+(" href="https://github\.com/VooZ2/terento/releases/download/[^" ]+\.dmg")',
            r'\1download-action download-action-primary\2',
            source,
            count=1,
        )
        source = re.sub(
            r'(<div class="download-actions">[\s\S]*?<a class=")[^"]+(" href="https://github\.com/VooZ2/terento/releases/tag/)',
            r'\1download-action download-action-tertiary\2',
            source,
            count=1,
        )
        sections = list(re.finditer(r'<section class="download-detail">[\s\S]*?</section>', source))
        for section in reversed(sections[2:]):
            source = source[:section.start()] + source[section.end():]
        source = re.sub(
            r'</section>\s*</div></section></main>',
            r'</section></div></section></main>',
            source,
            count=1,
        )
        return source
    pattern = re.compile(
        r'<div class="download-grid">'
        r'<div class="section-heading"><p class="eyebrow">(?P<label>.*?)</p>'
        r'<h2>(?P<version>.*?)</h2>'
        r'<p class="supporting-copy">(?P<release>.*?)</p></div>'
        r'<div class="download-list">(?P<sections>[\s\S]*?)</div></div>'
    )
    match = pattern.search(source)
    if match:
        replacement = (
            f'<p class="download-release">{match.group("label")}: '
            f'<strong>{match.group("version")}</strong> '
            '<span aria-hidden="true">·</span> '
            f'{match.group("release")}</p>'
            f'<div class="download-sections">{match.group("sections")}</div>'
        )
        source = source[:match.start()] + replacement + source[match.end():]

    pattern = re.compile(
        r'(?P<top>\s*<p class="eyebrow">[\s\S]*?<p class="download-release">[\s\S]*?</p>)\s*'
        r'<div class="download-sections">(?P<sections>[\s\S]*?)</div>\s*</div>(?P<main_close></main>)'
    )
    match = pattern.search(source)
    if not match:
        return source
    top = re.sub(r'\s*<p class="download-requirement">[\s\S]*?</p>', '', match.group("top"), count=1)
    top = re.sub(r'(<p class="download-intro">[^<]*)\s*<strong>[^<]*</strong>', r'\1', top, count=1)
    top = re.sub(
        r'(<div class="download-actions">[\s\S]*?<a class=")[^"]+(" href="https://github\.com/VooZ2/terento/releases/download/[^" ]+\.dmg")',
        r'\1download-action download-action-primary\2',
        top,
        count=1,
    )
    top = re.sub(
        r'(<div class="download-actions">[\s\S]*?<a class=")[^"]+(" href="https://github\.com/VooZ2/terento/releases/tag/)',
        r'\1download-action download-action-tertiary\2',
        top,
        count=1,
    )
    sections = re.findall(r'<section class="download-item">[\s\S]*?</section>', match.group("sections"))[:2]
    sections = ''.join(section.replace('class="download-item"', 'class="download-detail"', 1) for section in sections)
    details = (
        '<section class="download-details" aria-labelledby="download-details-title">'
        f'<div class="download-details-heading"><p class="eyebrow">{COPY[locale]["download_details_eyebrow"]}</p>'
        f'<h2 id="download-details-title">{COPY[locale]["download_details_title"]}</h2></div>'
        f'<div class="download-details-list">{sections}</div>'
        '</section>'
    )
    replacement = (
        f'<div class="download-hero"><div class="download-copy">{top}</div>'
        '</div>'
        f'{details}{match.group("main_close")}'
    )
    return source[:match.start()] + replacement + source[match.end():]


def replace_download_section_link(source: str, section_index: int, anchor: str) -> str:
    sections = list(re.finditer(r'<section class="download-(?:item|detail)">[\s\S]*?</section>', source))
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
        "en": "Yes. Terento takes you from choosing a map to installing it on your watch. You can also add a compatible map file from your Mac. Apple Silicon is required.",
        "de": "Ja. Terento führt dich von der Kartenauswahl bis zur Installation auf der Uhr. Du kannst auch eine kompatible Kartendatei von deinem Mac hinzufügen. Apple Silicon ist erforderlich.",
        "fr": "Oui. Terento vous guide du choix de la carte jusqu’à son installation sur la montre. Vous pouvez aussi ajouter un fichier cartographique compatible depuis votre Mac. Apple Silicon est requis.",
        "pl": "Tak. Terento prowadzi od wyboru mapy do instalacji na zegarku. Możesz też dodać zgodny plik mapy z Maca. Wymagany jest Apple Silicon.",
        "cs": "Ano. Terento vás provede od výběru mapy až po instalaci do hodinek. Z Macu můžete také přidat kompatibilní mapový soubor. Je vyžadován Apple Silicon.",
        "it": "Sì. Terento ti guida dalla scelta della mappa all’installazione sullo smartwatch. Puoi anche aggiungere dal Mac un file cartografico compatibile. È richiesto Apple Silicon.",
    }[locale]
    sentence = COPY[locale]["home"]
    visible = f'<p>{answer}</p>'
    visible_with_link = f'<p>{answer} <a href="{localized_guide(locale)}" data-umami-event="guide-link-click" data-umami-event-location="home-faq-guide">{sentence}</a></p>'
    if visible in source:
        source = source.replace(visible, visible_with_link, 1)
    json_answer = f'"text": "{answer}"'
    json_with_link = f'"text": "{answer} {sentence}"'
    if json_answer in source:
        source = source.replace(json_answer, json_with_link, 1)
    path.write_text(source, encoding="utf-8")


def add_download_link(locale: str) -> None:
    path = path_for(locale, "download/index.html")
    source = normalize_download_layout(path.read_text(encoding="utf-8"), locale)
    guide = download_link(
        COPY[locale]["download_guide"],
        localized_guide(locale),
        event="guide-link-click",
        location="download-page",
    )
    compatibility = download_link(
        COPY[locale]["download_compatibility"],
        localized_compatibility(locale),
        event="compatibility-link-click",
        location="download-page",
    )
    source = replace_download_section_link(source, 1, compatibility)
    source = replace_download_section_link(source, 0, guide)
    path.write_text(source, encoding="utf-8")


def add_compatibility_link(locale: str) -> None:
    path = path_for(locale, "compatibility/index.html")
    source = path.read_text(encoding="utf-8")
    hero_count = 1
    if 'class="compatibility-hero-copy"' not in source:
        source, hero_count = re.subn(
            r'(<section class="compatibility-hero"[^>]*>\s*<div class="shell compatibility-hero-inner">)([\s\S]*?)(</div>\s*</section>)',
            r'\1<div class="compatibility-hero-copy">\2</div>\3',
            source,
            count=1,
        )
        if not hero_count:
            raise RuntimeError(f"Compatibility hero not found for {locale}")
    evidence_note = f'<p class="compatibility-evidence-note" data-compatibility-evidence-note>{COPY[locale]["evidence_note"]}</p>'
    if 'data-compatibility-evidence-note' not in source:
        source, note_count = re.subn(
            r'(<div class="compatibility-how-body">\s*<p>[\s\S]*?</p>)',
            rf'\1{evidence_note}',
            source,
            count=1,
        )
        if not note_count:
            raise RuntimeError(f"Compatibility evidence explanation not found for {locale}")
    guide = f'<a class="text-link compatibility-guide-link" href="{localized_guide(locale)}" data-umami-event="guide-link-click" data-umami-event-location="compatibility-community-testing">{COPY[locale]["compatibility"]} <span aria-hidden="true">→</span></a>'
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
