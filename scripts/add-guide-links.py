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
        "compatibility": "First time installing third-party maps? Read the Mac guide",
        "community_eyebrow": "Community results",
        "community_heading": "Don’t see your Garmin here?",
        "community_body": "If your Garmin smartwatch supports maps, you can still try Terento. This list grows as successful installations are shared from more exact models and variants.",
        "community_download": "Download",
        "evidence_note": "Installation results are shared with Terento by users. They are not Garmin certification.",
        "download_status": "This is the current Terento beta. It supports maps from four map providers. The Compatibility page shows exact models and variants with successful shared installations. A model missing from the list is not an unsupported-device claim.",
    },
    "de": {
        "home": "Lies die vollständige Mac-Installationsanleitung.",
        "download_guide": "Mac-Installationsanleitung lesen",
        "download_compatibility": "Kompatibilität prüfen",
        "compatibility": "Zum ersten Mal Drittanbieter-Karten installieren? Lies die Mac-Anleitung",
        "community_eyebrow": "Ergebnisse aus der Community",
        "community_heading": "Dein Garmin ist nicht dabei?",
        "community_body": "Wenn deine Garmin-Smartwatch Karten unterstützt, kannst du Terento trotzdem ausprobieren. Diese Liste wächst, wenn erfolgreiche Installationen für weitere genaue Modelle und Varianten geteilt werden.",
        "community_download": "Herunterladen",
        "evidence_note": "Die Installationsergebnisse wurden von Nutzern mit Terento geteilt; sie sind keine Garmin-Zertifizierung.",
        "download_status": "Dies ist die aktuelle Terento-Beta. Sie unterstützt Karten von vier Kartenanbietern. Die Kompatibilitätsseite zeigt genaue Modelle und Varianten mit erfolgreich geteilten Installationen. Ein fehlendes Modell ist keine Aussage, dass das Gerät nicht unterstützt wird.",
    },
    "fr": {
        "home": "Lisez le guide complet d’installation sur Mac.",
        "download_guide": "Lire le guide d’installation sur Mac",
        "download_compatibility": "Vérifier la compatibilité",
        "compatibility": "Vous installez des cartes tierces pour la première fois ? Lisez le guide Mac",
        "community_eyebrow": "Résultats de la communauté",
        "community_heading": "Votre Garmin n’apparaît pas ?",
        "community_body": "Si votre montre Garmin prend en charge les cartes, vous pouvez tout de même essayer Terento. Cette liste s’allonge à mesure que des installations réussies sont partagées pour d’autres modèles et variantes exacts.",
        "community_download": "Télécharger",
        "evidence_note": "Les résultats d’installation sont partagés avec Terento par les utilisateurs ; ils ne constituent pas une certification Garmin.",
        "download_status": "Il s’agit de la bêta actuelle de Terento. Elle prend en charge les cartes de quatre fournisseurs. La page Compatibilité affiche les modèles et variantes exacts avec des installations réussies partagées. L’absence d’un modèle ne signifie pas qu’il n’est pas pris en charge.",
    },
    "pl": {
        "home": "Przeczytaj pełną instrukcję instalacji na Macu.",
        "download_guide": "Przeczytaj instrukcję instalacji na Macu",
        "download_compatibility": "Sprawdź kompatybilność",
        "compatibility": "Instalujesz mapy innych firm pierwszy raz? Przeczytaj instrukcję na Macu",
        "community_eyebrow": "Wyniki społeczności",
        "community_heading": "Nie widzisz swojego Garmina?",
        "community_body": "Jeśli Twój zegarek Garmin obsługuje mapy, nadal możesz wypróbować Terento. Lista rośnie wraz z udanymi instalacjami udostępnianymi dla kolejnych dokładnych modeli i wariantów.",
        "community_download": "Pobierz",
        "evidence_note": "Wyniki instalacji są udostępniane Terento przez użytkowników; nie są certyfikacją Garmin.",
        "download_status": "To aktualna beta Terento. Obsługuje mapy od czterech dostawców. Strona zgodności pokazuje dokładne modele i warianty z udanymi, udostępnionymi instalacjami. Brak modelu nie oznacza, że urządzenie nie jest obsługiwane.",
    },
    "cs": {
        "home": "Přečtěte si úplného průvodce instalací na Macu.",
        "download_guide": "Přečíst průvodce instalací na Macu",
        "download_compatibility": "Ověřit kompatibilitu",
        "compatibility": "Instalujete mapy třetích stran poprvé? Přečtěte si průvodce pro Mac",
        "community_eyebrow": "Výsledky komunity",
        "community_heading": "Nevidíte zde svůj Garmin?",
        "community_body": "Pokud vaše hodinky Garmin podporují mapy, můžete Terento přesto vyzkoušet. Seznam se rozšiřuje s dalšími sdílenými úspěšnými instalacemi pro konkrétní modely a varianty.",
        "community_download": "Stáhnout",
        "evidence_note": "Výsledky instalací sdílejí s Terento uživatelé; nejde o certifikaci Garmin.",
        "download_status": "Jde o aktuální betu Terento. Podporuje mapy od čtyř poskytovatelů. Stránka Kompatibilita zobrazuje konkrétní modely a varianty s úspěšnými sdílenými instalacemi. Chybějící model neznamená, že zařízení není podporováno.",
    },
    "it": {
        "home": "Leggi la guida completa all’installazione su Mac.",
        "download_guide": "Leggi la guida all’installazione su Mac",
        "download_compatibility": "Verifica la compatibilità",
        "compatibility": "Installi mappe di terze parti per la prima volta? Leggi la guida per Mac",
        "community_eyebrow": "Risultati della community",
        "community_heading": "Non vedi il tuo Garmin?",
        "community_body": "Se il tuo smartwatch Garmin supporta le mappe, puoi comunque provare Terento. L’elenco cresce man mano che vengono condivise installazioni riuscite per altri modelli e varianti esatti.",
        "community_download": "Scarica",
        "evidence_note": "I risultati delle installazioni sono condivisi con Terento dagli utenti; non costituiscono una certificazione Garmin.",
        "download_status": "Questa è la beta attuale di Terento. Supporta le mappe di quattro provider. La pagina Compatibilità mostra i modelli e le varianti esatti con installazioni riuscite condivise. L’assenza di un modello non significa che il dispositivo non sia supportato.",
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


DOWNLOAD_PRESENTATION = {
    "en": ("A native Mac app for installing and managing community maps on Garmin smartwatches with map support.", "Free", "Notarized", "Terento showing a connected Garmin watch on macOS"),
    "de": ("Eine native Mac-App zum Installieren und Verwalten von Community-Karten auf Garmin-Smartwatches mit Kartenunterstützung.", "Kostenlos", "Notarisiert", "Terento zeigt eine verbundene Garmin-Uhr unter macOS"),
    "fr": ("Une application Mac native pour installer et gérer des cartes communautaires sur les montres Garmin prenant en charge les cartes.", "Gratuit", "Notarié", "Terento affiche une montre Garmin connectée sur macOS"),
    "pl": ("Natywna aplikacja na Maca do instalowania i zarządzania mapami społecznościowymi na zegarkach Garmin obsługujących mapy.", "Bezpłatna", "Notaryzowana", "Terento pokazuje podłączony zegarek Garmin w macOS"),
    "cs": ("Nativní aplikace pro Mac k instalaci a správě komunitních map na hodinkách Garmin s podporou map.", "Zdarma", "Notarizovaná", "Terento zobrazuje připojené hodinky Garmin v macOS"),
    "it": ("Un’app Mac nativa per installare e gestire mappe della comunità sugli smartwatch Garmin con supporto alle mappe.", "Gratuita", "Notarizzata", "Terento mostra uno smartwatch Garmin collegato su macOS"),
}


def download_presentation(source: str, locale: str) -> str:
    intro, free, notarized, alt = DOWNLOAD_PRESENTATION[locale]
    source = re.sub(r'<ul class="download-badges">[\s\S]*?</ul>', '', source)
    badges = '<ul class="download-badges">' + ''.join(
        f'<li>{html.escape(label)}</li>' for label in (free, notarized, "Apple Silicon")
    ) + '</ul>'
    source = re.sub(r'<p class="download-intro">[\s\S]*?</p>',
                    f'<p class="download-intro">{html.escape(intro)}</p>{badges}', source, count=1)
    sizes = '(max-width: 899px) min(400px, calc(100vw - 48px)), 400px'
    sources = ''.join(
        f'<source type="image/{fmt}" srcset="' + ', '.join(
            f'/assets/app/optimized/your-garmin-{width}.{fmt}?v=20260905-app-screens-v1 {width}w'
            for width in (640, 960, 1280, 1600)
        ) + f'" sizes="{sizes}">'
        for fmt in ('avif', 'webp')
    )
    visual = ('<div class="download-visual"><figure class="app-shot app-shot--download"><picture>'
              + sources + '<img src="/assets/app/optimized/your-garmin-1600.png?v=20260905-app-screens-v1" '
              + f'width="2198" height="1335" sizes="{sizes}" alt="{html.escape(alt, quote=True)}" decoding="async">'
              + '</picture></figure></div>')
    anchor = r'(<p class="download-release">[\s\S]*?</p></div>)(</div>)'
    source, count = re.subn(anchor, lambda m: m.group(1) + visual + m.group(2), source, count=1)
    if count != 1:
        raise ValueError(f"{locale}: Download image insertion point missing")
    return source


def normalize_download_layout(source: str, locale: str) -> str:
    """Bring Download pages onto a focused actions + technical-details layout."""
    if source.count('class="download-hero"') != 1:
        raise ValueError(f"Download page ({locale}) must use the current download-hero layout")
    source = re.sub(r'\s*<p class="download-trust">[\s\S]*?</p>', '', source, count=1)
    source = re.sub(r'<div class="download-visual">[\s\S]*?</div>', '', source, count=1)
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
    sections = list(re.finditer(r'<section class="download-detail">[\s\S]*?</section>', source))
    if len(sections) < 2:
        raise RuntimeError("Download page must contain a beta-status section")
    status_section = sections[1]
    updated_status = re.sub(
        r'(<h2>[^<]*</h2>\s*)<p>[\s\S]*?</p>',
        rf'\1<p>{html.escape(COPY[locale]["download_status"])}</p>',
        status_section.group(0),
        count=1,
    )
    source = source[:status_section.start()] + updated_status + source[status_section.end():]
    return download_presentation(source, locale)


def replace_download_section_link(source: str, section_index: int, anchor: str) -> str:
    sections = list(re.finditer(r'<section class="download-detail">[\s\S]*?</section>', source))
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
