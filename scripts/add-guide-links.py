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
        "download_web_installer": "No Apple Silicon Mac? Use the web installer",
        "compatibility": "First time? Read the Mac install guide",
        "community_eyebrow": "Community results",
        "community_heading": "Don’t see your Garmin here?",
        "community_body": "If your Garmin smartwatch supports maps, you can still try Terento. This list grows as successful installations are shared from more exact models and variants.",
        "community_download": "Download",
        "evidence_note": "Installation results are shared with Terento by users. They are not Garmin certification.",
    },
    "de": {
        "home": "Lies die vollständige Mac-Installationsanleitung.",
        "download_web_installer": "Kein Mac mit Apple Silicon? Nutze den Web-Installer",
        "compatibility": "Zum ersten Mal? Lies die Mac-Anleitung",
        "community_eyebrow": "Ergebnisse aus der Community",
        "community_heading": "Dein Garmin ist nicht dabei?",
        "community_body": "Wenn deine Garmin-Smartwatch Karten unterstützt, kannst du Terento trotzdem ausprobieren. Diese Liste wächst, wenn erfolgreiche Installationen für weitere genaue Modelle und Varianten geteilt werden.",
        "community_download": "Herunterladen",
        "evidence_note": "Die Installationsergebnisse wurden von Nutzern mit Terento geteilt; sie sind keine Garmin-Zertifizierung.",
    },
    "fr": {
        "home": "Lisez le guide complet d’installation sur Mac.",
        "download_web_installer": "Pas de Mac Apple Silicon ? Utilisez l’installateur web",
        "compatibility": "Première fois ? Lisez le guide Mac",
        "community_eyebrow": "Résultats de la communauté",
        "community_heading": "Votre Garmin n’apparaît pas ?",
        "community_body": "Si votre montre Garmin prend en charge les cartes, vous pouvez tout de même essayer Terento. Cette liste s’allonge à mesure que des installations réussies sont partagées pour d’autres modèles et variantes exacts.",
        "community_download": "Télécharger",
        "evidence_note": "Les résultats d’installation sont partagés avec Terento par les utilisateurs ; ils ne constituent pas une certification Garmin.",
    },
    "pl": {
        "home": "Przeczytaj pełną instrukcję instalacji na Macu.",
        "download_web_installer": "Nie masz Maca z Apple Silicon? Użyj instalatora webowego",
        "compatibility": "Pierwszy raz? Przeczytaj instrukcję na Maca",
        "community_eyebrow": "Wyniki społeczności",
        "community_heading": "Nie widzisz swojego Garmina?",
        "community_body": "Jeśli Twój zegarek Garmin obsługuje mapy, nadal możesz wypróbować Terento. Lista rośnie wraz z udanymi instalacjami udostępnianymi dla kolejnych dokładnych modeli i wariantów.",
        "community_download": "Pobierz",
        "evidence_note": "Wyniki instalacji są udostępniane Terento przez użytkowników; nie są certyfikacją Garmin.",
    },
    "cs": {
        "home": "Přečtěte si úplného průvodce instalací na Macu.",
        "download_web_installer": "Nemáte Mac s Apple Silicon? Použijte webový instalátor",
        "compatibility": "Poprvé? Přečtěte si průvodce pro Mac",
        "community_eyebrow": "Výsledky komunity",
        "community_heading": "Nevidíte zde svůj Garmin?",
        "community_body": "Pokud vaše hodinky Garmin podporují mapy, můžete Terento přesto vyzkoušet. Seznam se rozšiřuje s dalšími sdílenými úspěšnými instalacemi pro konkrétní modely a varianty.",
        "community_download": "Stáhnout",
        "evidence_note": "Výsledky instalací sdílejí s Terento uživatelé; nejde o certifikaci Garmin.",
    },
    "it": {
        "home": "Leggi la guida completa all’installazione su Mac.",
        "download_web_installer": "Niente Mac con Apple Silicon? Usa l’installer web",
        "compatibility": "Prima volta? Leggi la guida per Mac",
        "community_eyebrow": "Risultati della community",
        "community_heading": "Non vedi il tuo Garmin?",
        "community_body": "Se il tuo smartwatch Garmin supporta le mappe, puoi comunque provare Terento. L’elenco cresce man mano che vengono condivise installazioni riuscite per altri modelli e varianti esatti.",
        "community_download": "Scarica",
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
    guide = f'<a class="text-link compatibility-guide-link" href="{localized_guide(locale)}" data-umami-event="guide-link-click" data-umami-event-location="compatibility-community-testing">{COPY[locale]["compatibility"]}</a>'
    download = f'<a class="download-action download-action-primary compatibility-community-link" href="{localized_download(locale)}" data-umami-event="download-cta-click" data-umami-event-location="compatibility-community-testing">{COPY[locale]["community_download"]}</a>'
    # Without an Apple Silicon Mac: the web installer (2026-11-02, same words as the Download page).
    web_installer = f'<a class="text-link compatibility-web-installer-link" href="/{'' if locale == 'en' else f'{locale}/'}install/" data-umami-event="web-installer-link-click" data-umami-event-location="compatibility-community-testing">{COPY[locale]["download_web_installer"]}</a>'
    community = (
        '<div class="compatibility-community-cta">'
        '<div class="compatibility-community-copy">'
        f'<h2>{COPY[locale]["community_heading"]}</h2>'
        f'<p>{COPY[locale]["community_body"]}</p>'
        f'{guide}{web_installer}'
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
        add_compatibility_link(locale)
    print("Added guide links to Home FAQ and Compatibility testing surfaces.")


if __name__ == "__main__":
    main()
