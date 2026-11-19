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
        "evidence_note": "Installation results are shared with Terento by users. They are not Garmin certification.",
    },
    "de": {
        "home": "Lies die vollständige Mac-Installationsanleitung.",
        "evidence_note": "Die Installationsergebnisse wurden von Nutzern mit Terento geteilt; sie sind keine Garmin-Zertifizierung.",
    },
    "fr": {
        "home": "Lisez le guide complet d’installation sur Mac.",
        "evidence_note": "Les résultats d’installation sont partagés avec Terento par les utilisateurs ; ils ne constituent pas une certification Garmin.",
    },
    "pl": {
        "home": "Przeczytaj pełną instrukcję instalacji na Macu.",
        "evidence_note": "Wyniki instalacji są udostępniane Terento przez użytkowników; nie są certyfikacją Garmin.",
    },
    "cs": {
        "home": "Přečtěte si úplného průvodce instalací na Macu.",
        "evidence_note": "Výsledky instalací sdílejí s Terento uživatelé; nejde o certifikaci Garmin.",
    },
    "it": {
        "home": "Leggi la guida completa all’installazione su Mac.",
        "evidence_note": "I risultati delle installazioni sono condivisi con Terento dagli utenti; non costituiscono una certificazione Garmin.",
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


def add_compatibility_link(locale: str) -> None:
    path = path_for(locale, "compatibility/index.html")
    source = path.read_text(encoding="utf-8")
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
    # The hero, the community card and the closing call to action come from
    # scripts/build-compatibility-pages.py (2026-11-19, round 4).
    path.write_text(source, encoding="utf-8")


def main() -> None:
    for locale in COPY:
        add_home_link(locale)
        add_compatibility_link(locale)
    print("Added guide links to Home FAQ and Compatibility testing surfaces.")


if __name__ == "__main__":
    main()
