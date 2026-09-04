#!/usr/bin/env python3
"""Build the localized public About pages from one shared content source."""

from __future__ import annotations

import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://terento.app"
ABOUT_SLUG = "about/"
SHELL_VERSION = "20260904-pass3-internal-link-events-v1"
STYLE_VERSION = "20260904-pass3-workflow-arrows-v7"
UMAMI_SCRIPT_VERSION = "20260904-public-link-events"
SOCIAL_IMAGE = "/assets/social/terento-og.png"
LOCALES = ("en", "de", "fr", "pl", "cs", "it")
META_LOCALES = {"en": "en_US", "de": "de_DE", "fr": "fr_FR", "pl": "pl_PL", "cs": "cs_CZ", "it": "it_IT"}
SOCIAL_IMAGE_ALTS = {
    "en": "Terento showing a connected Garmin smartwatch on macOS",
    "de": "Terento zeigt eine verbundene Garmin-Smartwatch unter macOS",
    "fr": "Terento affiche une montre Garmin connectée sur macOS",
    "pl": "Terento pokazuje podłączony zegarek Garmin w systemie macOS",
    "cs": "Terento zobrazuje připojené hodinky Garmin v systému macOS",
    "it": "Terento mostra uno smartwatch Garmin collegato su macOS",
}


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def localized_path(locale: str, suffix: str = "") -> str:
    prefix = "" if locale == "en" else f"{locale}/"
    return f"/{prefix}{suffix}"


COPY = {
    "en": {
        "title": "About Terento — Free, Open-Source Garmin Maps for Mac",
        "description": "Learn why Terento exists: a free, open-source macOS app for installing and managing third-party maps on Garmin smartwatches.",
        "eyebrow": "About Terento",
        "skip": "Skip to content",
        "h1": "A solution, not a process",
        "intro": "Terento is a free, open-source macOS app that makes community maps easier to install and keep current on modern Garmin smartwatches.",
        "section_eyebrow": "The idea",
        "section_title": "Your device, ready for where you’re going.",
        "items": [
            ("Built around the result", "Terento keeps the main path simple: connect your watch, choose a map and get ready to go."),
            ("Open source by default", "Terento is developed in public and released under GPL-3.0-or-later. The project is free to use; the app does not require an account or a cloud device profile."),
            ("Independent and careful", 'The current Beta supports Freizeitkarte and OpenTopoMap. Garmin names are used descriptively for compatibility. Map providers keep their own licences, and map files travel directly from the original provider to your Mac and then to your watch. See <a href="/legal/">Legal</a> and <a href="/privacy/">Privacy</a> for details.'),
            ("Built with the community", 'Compatibility is confirmed model by model using real installation results. If something does not work, share an issue on <a href="https://github.com/VooZ2/terento/issues" target="_blank" rel="noopener noreferrer">GitHub</a> so the project can learn from it.'),
        ],
    },
    "de": {
        "title": "Über Terento — Kostenlose Open-Source-Garmin-Karten für den Mac",
        "description": "Warum es Terento gibt: eine kostenlose Open-Source-macOS-App zum Installieren und Verwalten von Drittanbieter-Karten auf Garmin-Smartwatches.",
        "eyebrow": "Über Terento",
        "skip": "Zum Inhalt springen",
        "h1": "Eine Lösung, kein Prozess",
        "intro": "Terento ist eine kostenlose Open-Source-macOS-App, die Community-Karten auf modernen Garmin-Smartwatches einfacher installieren und aktuell halten lässt.",
        "section_eyebrow": "Die Idee",
        "section_title": "Dein Gerät, bereit für dein nächstes Ziel.",
        "items": [
            ("Das Ergebnis im Mittelpunkt", "Terento hält den Ablauf einfach: Uhr verbinden, Karte auswählen und loslegen."),
            ("Open Source als Grundlage", "Terento wird öffentlich entwickelt und unter GPL-3.0-or-later veröffentlicht. Das Projekt ist kostenlos; die App benötigt kein Konto und kein Geräteprofil in der Cloud."),
            ("Unabhängig und sorgfältig", 'Die aktuelle Beta unterstützt Freizeitkarte und OpenTopoMap. Garmin-Namen werden beschreibend für Kompatibilität verwendet. Kartenanbieter behalten ihre eigenen Lizenzen. Kartendateien werden direkt vom ursprünglichen Anbieter auf deinen Mac und anschließend auf deine Uhr übertragen. Details stehen unter <a href="/legal/">Rechtliches</a> und <a href="/privacy/">Datenschutz</a>.'),
            ("Mit der Community entwickelt", 'Die Kompatibilität wird für jedes Modell einzeln anhand echter Installationsergebnisse bestätigt. Wenn etwas nicht funktioniert, teile ein Issue auf <a href="https://github.com/VooZ2/terento/issues" target="_blank" rel="noopener noreferrer">GitHub</a>, damit das Projekt daraus lernen kann.'),
        ],
    },
    "fr": {
        "title": "À propos de Terento — Cartes Garmin gratuites et open source sur Mac",
        "description": "Découvrez pourquoi Terento existe : une application macOS gratuite et open source pour installer et gérer des cartes tierces sur les montres Garmin.",
        "eyebrow": "À propos de Terento",
        "skip": "Aller au contenu",
        "h1": "Une solution, pas un processus",
        "intro": "Terento est une application macOS gratuite et open source qui simplifie l’installation et la mise à jour de cartes communautaires sur les montres Garmin modernes.",
        "section_eyebrow": "L’idée",
        "section_title": "Votre appareil, prêt pour votre prochaine aventure.",
        "items": [
            ("Pensé pour le résultat", "Terento simplifie le parcours : connectez la montre, choisissez une carte et partez."),
            ("Open source par choix", "Terento est développé publiquement et publié sous GPL-3.0-or-later. Le projet est gratuit ; l’application ne nécessite ni compte ni profil d’appareil dans le cloud."),
            ("Indépendant et prudent", 'La bêta actuelle prend en charge Freizeitkarte et OpenTopoMap. Les noms Garmin sont utilisés à titre descriptif pour la compatibilité. Les fournisseurs conservent leurs propres licences et les fichiers cartographiques vont directement du fournisseur d’origine vers votre Mac, puis votre montre. Consultez les <a href="/legal/">mentions légales</a> et la <a href="/privacy/">confidentialité</a>.'),
            ("Construit avec la communauté", 'La compatibilité est confirmée modèle par modèle grâce à des résultats d’installation réels. Si quelque chose ne fonctionne pas, partagez une issue sur <a href="https://github.com/VooZ2/terento/issues" target="_blank" rel="noopener noreferrer">GitHub</a> pour aider le projet à progresser.'),
        ],
    },
    "pl": {
        "title": "O Terento — Bezpłatne, otwartoźródłowe mapy Garmina na Macu",
        "description": "Dowiedz się, dlaczego powstało Terento: bezpłatna aplikacja macOS open source do instalowania i zarządzania mapami innych firm na zegarkach Garmin.",
        "eyebrow": "O Terento",
        "skip": "Przejdź do treści",
        "h1": "Rozwiązanie, nie proces",
        "intro": "Terento to bezpłatna aplikacja macOS open source, która ułatwia instalowanie i aktualizowanie map społecznościowych na nowoczesnych zegarkach Garmin.",
        "section_eyebrow": "Pomysł",
        "section_title": "Twoje urządzenie gotowe na kolejną trasę.",
        "items": [
            ("Liczy się rezultat", "Terento upraszcza cały proces: podłącz zegarek, wybierz mapę i ruszaj."),
            ("Open source od podstaw", "Terento jest rozwijane publicznie i wydawane na licencji GPL-3.0-or-later. Projekt jest bezpłatny; aplikacja nie wymaga konta ani profilu urządzenia w chmurze."),
            ("Niezależnie i ostrożnie", 'Aktualna beta obsługuje Freizeitkarte i OpenTopoMap. Nazwy Garmin są używane opisowo w kontekście kompatybilności. Dostawcy zachowują własne licencje, a pliki map trafiają bezpośrednio od dostawcy na Maca, a następnie na zegarek. Szczegóły znajdziesz w sekcjach <a href="/legal/">Informacje prawne</a> i <a href="/privacy/">Prywatność</a>.'),
            ("Tworzone ze społecznością", 'Kompatybilność jest potwierdzana dla każdego modelu na podstawie rzeczywistych wyników instalacji. Jeśli coś nie działa, zgłoś problem na <a href="https://github.com/VooZ2/terento/issues" target="_blank" rel="noopener noreferrer">GitHubie</a>, aby projekt mógł się na tym uczyć.'),
        ],
    },
    "cs": {
        "title": "O Terento — Bezplatné open-source mapy Garminu na Macu",
        "description": "Zjistěte, proč Terento vzniklo: bezplatná open-source aplikace pro macOS k instalaci a správě map třetích stran na hodinkách Garmin.",
        "eyebrow": "O Terento",
        "skip": "Přejít k obsahu",
        "h1": "Řešení, ne proces",
        "intro": "Terento je bezplatná open-source aplikace pro macOS, která usnadňuje instalaci a aktualizaci komunitních map na moderních hodinkách Garmin.",
        "section_eyebrow": "Myšlenka",
        "section_title": "Vaše zařízení připravené na další cestu.",
        "items": [
            ("Důležitý je výsledek", "Terento udržuje postup jednoduchý: připojte hodinky, vyberte mapu a vyrazte."),
            ("Open source jako základ", "Terento vzniká veřejně a je vydáváno pod licencí GPL-3.0-or-later. Projekt je bezplatný; aplikace nevyžaduje účet ani cloudový profil zařízení."),
            ("Nezávisle a opatrně", 'Aktuální beta podporuje Freizeitkarte a OpenTopoMap. Názvy Garmin používáme popisně kvůli kompatibilitě. Poskytovatelé si ponechávají vlastní licence a mapové soubory putují přímo od původního poskytovatele do vašeho Macu a poté do hodinek. Podrobnosti najdete v sekcích <a href="/legal/">Právní informace</a> a <a href="/privacy/">Soukromí</a>.'),
            ("Tvoříme s komunitou", 'Kompatibilita se potvrzuje pro každý model na základě skutečných výsledků instalace. Pokud něco nefunguje, otevřete issue na <a href="https://github.com/VooZ2/terento/issues" target="_blank" rel="noopener noreferrer">GitHubu</a>, aby se z toho projekt mohl poučit.'),
        ],
    },
    "it": {
        "title": "Informazioni su Terento — Mappe Garmin gratuite e open source su Mac",
        "description": "Scopri perché esiste Terento: un’app macOS gratuita e open source per installare e gestire mappe di terze parti sugli smartwatch Garmin.",
        "eyebrow": "Informazioni su Terento",
        "skip": "Vai al contenuto",
        "h1": "Una soluzione, non un processo",
        "intro": "Terento è un’app macOS gratuita e open source che semplifica l’installazione e l’aggiornamento delle mappe della community sugli smartwatch Garmin moderni.",
        "section_eyebrow": "L’idea",
        "section_title": "Il tuo dispositivo, pronto per la prossima meta.",
        "items": [
            ("Il risultato prima di tutto", "Terento mantiene il percorso semplice: collega l’orologio, scegli una mappa e parti."),
            ("Open source alla base", "Terento è sviluppato pubblicamente e rilasciato con licenza GPL-3.0-or-later. Il progetto è gratuito; l’app non richiede un account né un profilo del dispositivo nel cloud."),
            ("Indipendente e prudente", 'La beta attuale supporta Freizeitkarte e OpenTopoMap. I nomi Garmin sono usati in modo descrittivo per la compatibilità. I provider mantengono le proprie licenze e i file delle mappe passano direttamente dal provider originale al tuo Mac e poi all’orologio. Per i dettagli, vedi <a href="/legal/">Note legali</a> e <a href="/privacy/">Privacy</a>.'),
            ("Costruito con la community", 'La compatibilità viene confermata modello per modello usando risultati reali di installazione. Se qualcosa non funziona, apri una issue su <a href="https://github.com/VooZ2/terento/issues" target="_blank" rel="noopener noreferrer">GitHub</a> per aiutare il progetto a migliorare.'),
        ],
    },
}


def render(locale: str, copy: dict[str, object]) -> str:
    canonical = f"{BASE_URL}{localized_path(locale, ABOUT_SLUG)}"
    meta_locale = META_LOCALES[locale]
    alternate_links = "\n".join(
        f'    <link rel="alternate" hreflang="{candidate}" href="{BASE_URL}{localized_path(candidate, ABOUT_SLUG)}">'
        for candidate in LOCALES
    )
    items = "\n".join(
        f'            <section class="about-item"><h2>{esc(title)}</h2><p>{body}</p></section>'
        for title, body in copy["items"]
    )
    return f'''<!doctype html>
<html lang="{locale}" data-language="{locale}" data-page="about">
  <head>
    <script defer src="/site-shell.js?v={SHELL_VERSION}"></script>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="theme-color" content="#F7F3EC">
    <meta name="theme-color" media="(prefers-color-scheme: dark)" content="#222A2B">
    <meta name="description" content="{esc(copy["description"])}">
    <meta name="robots" content="index,follow">
    <link rel="canonical" href="{canonical}">
{alternate_links}
    <link rel="alternate" hreflang="x-default" href="{BASE_URL}/{ABOUT_SLUG}">
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="Terento">
    <meta property="og:title" content="{esc(copy["title"])}">
    <meta property="og:description" content="{esc(copy["description"])}">
    <meta property="og:url" content="{canonical}">
    <meta property="og:image" content="{BASE_URL}{SOCIAL_IMAGE}">
    <meta property="og:image:type" content="image/png">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <meta property="og:image:alt" content="{esc(SOCIAL_IMAGE_ALTS[locale])}">
    <meta property="og:locale" content="{meta_locale}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{esc(copy["title"])}">
    <meta name="twitter:description" content="{esc(copy["description"])}">
    <meta name="twitter:image" content="{BASE_URL}{SOCIAL_IMAGE}">
    <title>{esc(copy["title"])}</title>


    <link rel="icon" href="/favicon.ico?v=20260820-4" sizes="any">
    <link rel="icon" href="/favicon.svg?v=20260820-4" type="image/svg+xml">
    <link rel="apple-touch-icon" href="/apple-touch-icon.png?v=20260820-4">
    <link rel="manifest" href="/manifest.webmanifest">
    <link rel="stylesheet" href="/styles.css?v={STYLE_VERSION}">
    <script defer src="/privacy-consent.js?v={UMAMI_SCRIPT_VERSION}"></script>
</head>
  <body class="about-page">
    <a class="skip-link" href="#main-content">{esc(copy["skip"])}</a>
    <header class="site-header"></header>
    <main id="main-content">
      <section class="compatibility-hero about-hero" aria-labelledby="about-title">
        <div class="shell compatibility-hero-inner"><div class="compatibility-hero-copy">
          <p class="eyebrow">{esc(copy["eyebrow"])}</p>
          <h1 id="about-title">{esc(copy["h1"])}</h1>
          <p class="hero-lede">{esc(copy["intro"])}</p>
        </div></div>
      </section>
      <section class="about-main">
        <div class="shell about-grid">
          <div class="section-heading"><p class="eyebrow">{esc(copy["section_eyebrow"])}</p><h2>{esc(copy["section_title"])}</h2></div>
          <div class="about-list">
{items}
          </div>
        </div>
      </section>
    </main>
    <footer class="site-footer"></footer>
  </body>
</html>
'''


def main() -> None:
    for locale in LOCALES:
        output = ROOT / "site" / localized_path(locale, ABOUT_SLUG).lstrip("/") / "index.html"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render(locale, COPY[locale]), encoding="utf-8")
        print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
