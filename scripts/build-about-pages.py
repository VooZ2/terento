#!/usr/bin/env python3
"""Build the localized public About pages from one shared content source."""

from __future__ import annotations

import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://terento.app"
ABOUT_SLUG = "about/"
SHELL_VERSION = "20260905-in-page-language-v1"
STYLE_VERSION = "20260905-in-page-language-v1"
UMAMI_SCRIPT_VERSION = "20260905-public-link-events-v3"
SOCIAL_IMAGE = "/assets/social/terento-og.png"
EMAIL_ADDRESS = "hello@terento.app"
EMAIL_ADDRESS_HTML = EMAIL_ADDRESS.replace("@", "&#64;")
EMAIL_HREF = f"mailto:{EMAIL_ADDRESS_HTML}"
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


COPY = {'en': {'title': 'About Terento — Free, Open-Source Garmin Maps for Mac',
        'description': 'Terento is a free, open-source Mac app for choosing, installing, and managing '
                       'community maps on compatible Garmin watches. Built to make getting ready for your '
                       'next trip simpler.',
        'skip': 'Skip to content',
        'story_eyebrow': 'A note from the maker',
        'story_heading': 'Why I started Terento',
        'story': ['I’m Gediminas, a Garmin user who enjoys hiking in the mountains. Before a trip, I want my '
                  'watch ready with maps for where I’m going. Getting those maps onto it often took more '
                  'effort than it should.',
                  'I started Terento to make that easier for myself and other Mac users. I’m keeping it free '
                  'and open source because I want this small solution to be useful to the community.'],
        'social_eyebrow': 'Connect with the maker',
        'linkedin': 'LinkedIn',
        'reddit': 'Reddit',
        'email': 'Email',
        'donate_prompt': 'Like the project?',
        'donate': 'Donate',
        'section_title': 'Made for your next trip',
        'does_title': 'Maps, in one place',
        'does_items': ['Choose and install maps from Freizeitkarte or OpenTopoMap.',
                       'Add your own compatible map (.img); custom maps have no automatic updates.',
                       'Update and manage Terento-installed provider maps in one Mac app.',
                       'Keeps original Garmin maps protected.'],
        'doesnt_title': 'Free and open to everyone',
        'doesnt_items': ['Free to use, with no account required.',
                         'Open source: explore the code or help improve it on GitHub.',
                         'Maps come from their providers, with their attribution preserved.'],
        'product_heading': 'Community maps. A simpler way onto your Garmin.',
        'beta': 'Public beta for Apple Silicon Macs. Compatibility is evaluated model by model.',
        'compatibility': 'Check compatibility',
        'download': 'Download'},
 'de': {'title': 'Über Terento — Kostenlose Open-Source-Garmin-Karten für den Mac',
        'description': 'Terento ist eine kostenlose Open-Source-Mac-App zum Auswählen, Installieren und '
                       'Verwalten von Community-Karten auf kompatiblen Garmin-Uhren. Damit die Vorbereitung '
                       'auf deine nächste Reise einfacher wird.',
        'skip': 'Zum Inhalt springen',
        'story_eyebrow': 'Eine Notiz vom Entwickler',
        'story_heading': 'Warum ich Terento gestartet habe',
        'story': ['Ich bin Gediminas, Garmin-Nutzer und gern in den Bergen unterwegs. Vor einer Reise möchte '
                  'ich meine Uhr mit Karten für mein Reiseziel vorbereiten. Diese Karten auf die Uhr zu '
                  'bekommen, war oft aufwendiger als nötig.',
                  'Ich habe Terento gestartet, um das für mich und andere Mac-Nutzer einfacher zu machen. '
                  'Ich halte es kostenlos und quelloffen, weil ich möchte, dass diese kleine Lösung der '
                  'Community hilft.'],
        'social_eyebrow': 'Mit dem Entwickler verbinden',
        'linkedin': 'LinkedIn',
        'reddit': 'Reddit',
        'email': 'E-Mail',
        'donate_prompt': 'Gefällt dir das Projekt?',
        'donate': 'Spenden',
        'section_title': 'Für deine nächste Reise',
        'does_title': 'Karten an einem Ort',
        'does_items': ['Wähle und installiere Karten von Freizeitkarte oder OpenTopoMap.',
                       'Füge deine eigene kompatible Karte (.img) hinzu; eigene Karten erhalten keine '
                       'automatischen Updates.',
                       'Aktualisiere und verwalte mit Terento installierte Anbieterkarten in einer Mac-App.',
                       'Originale Garmin-Karten bleiben geschützt.'],
        'doesnt_title': 'Kostenlos und offen für alle',
        'doesnt_items': ['Kostenlos nutzbar, ohne Konto.',
                         'Open Source: Sieh dir den Code an oder hilf auf GitHub mit.',
                         'Die Karten stammen von ihren Anbietern; deren Quellenangaben bleiben erhalten.'],
        'product_heading': 'Community-Karten. Einfacher auf deiner Garmin.',
        'beta': 'Public Beta für Macs mit Apple Silicon. Die Kompatibilität wird für jedes Modell einzeln '
                'bewertet.',
        'compatibility': 'Kompatibilität prüfen',
        'download': 'Download'},
 'fr': {'title': 'À propos de Terento — Cartes Garmin gratuites et open source sur Mac',
        'description': 'Terento est une application Mac gratuite et open source pour choisir, installer et '
                       'gérer des cartes communautaires sur les montres Garmin compatibles. Pour préparer '
                       'plus simplement votre prochaine escapade.',
        'skip': 'Aller au contenu',
        'story_eyebrow': 'Une note du créateur',
        'story_heading': 'Pourquoi j’ai créé Terento',
        'story': ['Je suis Gediminas, utilisateur de Garmin et amateur de randonnée en montagne. Avant un '
                  'voyage, je veux préparer ma montre avec les cartes de ma destination. Les transférer sur '
                  'ma montre demandait souvent trop d’efforts.',
                  'J’ai créé Terento pour simplifier cela, pour moi et pour les autres utilisateurs de Mac. '
                  'Je le garde gratuit et open source pour que cette petite solution soit utile à la '
                  'communauté.'],
        'social_eyebrow': 'Se connecter avec le créateur',
        'linkedin': 'LinkedIn',
        'reddit': 'Reddit',
        'email': 'E-mail',
        'donate_prompt': 'Vous aimez le projet ?',
        'donate': 'Faire un don',
        'section_title': 'Pour votre prochaine escapade',
        'does_title': 'Vos cartes au même endroit',
        'does_items': ['Choisissez et installez des cartes de Freizeitkarte ou OpenTopoMap.',
                       'Ajoutez votre propre carte compatible (.img) ; les cartes personnelles ne '
                       'bénéficient pas de mises à jour automatiques.',
                       'Mettez à jour et gérez les cartes de fournisseurs installées par Terento dans une '
                       'seule application Mac.',
                       'Protège les cartes Garmin d’origine.'],
        'doesnt_title': 'Gratuit et ouvert à tous',
        'doesnt_items': ['Gratuit, sans compte obligatoire.',
                         'Open source : consultez le code ou contribuez sur GitHub.',
                         'Les cartes proviennent de leurs fournisseurs et conservent leurs attributions.'],
        'product_heading': 'Des cartes communautaires. Plus simplement sur votre Garmin.',
        'beta': 'Bêta publique pour les Mac avec Apple Silicon. La compatibilité est évaluée modèle par '
                'modèle.',
        'compatibility': 'Vérifier la compatibilité',
        'download': 'Télécharger'},
 'pl': {'title': 'O Terento — Bezpłatne, otwartoźródłowe mapy Garmina na Macu',
        'description': 'Terento to bezpłatna aplikacja open source na Maca do wybierania, instalowania i '
                       'zarządzania mapami społecznościowymi na zgodnych zegarkach Garmin. Ułatwia '
                       'przygotowania do kolejnej podróży.',
        'skip': 'Przejdź do treści',
        'story_eyebrow': 'Notatka od twórcy',
        'story_heading': 'Dlaczego stworzyłem Terento',
        'story': ['Mam na imię Gediminas, używam Garmina i lubię górskie wędrówki. Przed podróżą chcę '
                  'przygotować zegarek z mapami miejsc, do których się wybieram. Wgranie tych map często '
                  'wymagało więcej wysiłku, niż powinno.',
                  'Stworzyłem Terento, aby ułatwić to sobie i innym użytkownikom Maca. Projekt pozostaje '
                  'bezpłatny i open source, bo chcę, aby to małe rozwiązanie służyło społeczności.'],
        'social_eyebrow': 'Połącz się z twórcą',
        'linkedin': 'LinkedIn',
        'reddit': 'Reddit',
        'email': 'E-mail',
        'donate_prompt': 'Podoba Ci się projekt?',
        'donate': 'Wesprzyj',
        'section_title': 'Na Twoją kolejną podróż',
        'does_title': 'Mapy w jednym miejscu',
        'does_items': ['Wybieraj i instaluj mapy Freizeitkarte lub OpenTopoMap.',
                       'Dodaj własną zgodną mapę (.img); własne mapy nie mają automatycznych aktualizacji.',
                       'Aktualizuj i zarządzaj mapami dostawców zainstalowanymi przez Terento w jednej '
                       'aplikacji na Maca.',
                       'Chroni oryginalne mapy Garmina.'],
        'doesnt_title': 'Bezpłatne i otwarte dla wszystkich',
        'doesnt_items': ['Bezpłatnie, bez konieczności zakładania konta.',
                         'Open source: przeglądaj kod lub pomóż go ulepszać na GitHubie.',
                         'Mapy pochodzą od ich dostawców, z zachowaniem informacji o autorstwie.'],
        'product_heading': 'Mapy społecznościowe. Prościej na Twoim Garminie.',
        'beta': 'Publiczna beta dla Maców z Apple Silicon. Zgodność jest oceniana dla każdego modelu osobno.',
        'compatibility': 'Sprawdź zgodność',
        'download': 'Pobierz'},
 'cs': {'title': 'O Terento — Bezplatné open-source mapy Garminu na Macu',
        'description': 'Terento je bezplatná open-source aplikace pro Mac k výběru, instalaci a správě '
                       'komunitních map na kompatibilních hodinkách Garmin. Usnadňuje přípravu na další '
                       'cestu.',
        'skip': 'Přejít k obsahu',
        'story_eyebrow': 'Poznámka od tvůrce',
        'story_heading': 'Proč jsem vytvořil Terento',
        'story': ['Jmenuji se Gediminas, používám Garmin a rád chodím po horách. Před cestou chci mít v '
                  'hodinkách mapy míst, kam se chystám. Dostat do nich tyto mapy často vyžadovalo více '
                  'úsilí, než by mělo.',
                  'Vytvořil jsem Terento, abych to usnadnil sobě i ostatním uživatelům Macu. Nechávám ho '
                  'zdarma a s otevřeným kódem, protože chci, aby toto malé řešení pomáhalo komunitě.'],
        'social_eyebrow': 'Spojte se s tvůrcem',
        'linkedin': 'LinkedIn',
        'reddit': 'Reddit',
        'email': 'E-mail',
        'donate_prompt': 'Líbí se vám projekt?',
        'donate': 'Přispět',
        'section_title': 'Pro vaši příští cestu',
        'does_title': 'Mapy na jednom místě',
        'does_items': ['Vyberte a nainstalujte mapy od Freizeitkarte nebo OpenTopoMap.',
                       'Přidejte vlastní kompatibilní mapu (.img); vlastní mapy nemají automatické '
                       'aktualizace.',
                       'Aktualizujte a spravujte mapy poskytovatelů nainstalované přes Terento v jedné '
                       'aplikaci pro Mac.',
                       'Chrání originální mapy Garminu.'],
        'doesnt_title': 'Zdarma a otevřené všem',
        'doesnt_items': ['Zdarma, bez nutnosti účtu.',
                         'Open source: prohlédněte si kód nebo pomozte s jeho vylepšením na GitHubu.',
                         'Mapy pocházejí od svých poskytovatelů a zachovávají údaje o autorství.'],
        'product_heading': 'Komunitní mapy. Jednodušeji do vašeho Garminu.',
        'beta': 'Veřejná beta pro Macy s Apple Silicon. Kompatibilita se posuzuje pro každý model zvlášť.',
        'compatibility': 'Ověřit kompatibilitu',
        'download': 'Stáhnout'},
 'it': {'title': 'Informazioni su Terento — Mappe Garmin gratuite e open source su Mac',
        'description': 'Terento è un’app Mac gratuita e open source per scegliere, installare e gestire '
                       'mappe della comunità sugli orologi Garmin compatibili. Per prepararti più facilmente '
                       'al prossimo viaggio.',
        'skip': 'Vai al contenuto',
        'story_eyebrow': 'Una nota dal creatore',
        'story_heading': 'Perché ho creato Terento',
        'story': ['Sono Gediminas, uso Garmin e amo le escursioni in montagna. Prima di un viaggio voglio '
                  'preparare l’orologio con le mappe dei luoghi che visiterò. Trasferire quelle mappe '
                  'richiedeva spesso più impegno del necessario.',
                  'Ho creato Terento per semplificare tutto questo, per me e per gli altri utenti Mac. Lo '
                  'mantengo gratuito e open source perché voglio che questa piccola soluzione sia utile alla '
                  'comunità.'],
        'social_eyebrow': 'Connettiti con il creatore',
        'linkedin': 'LinkedIn',
        'reddit': 'Reddit',
        'email': 'Email',
        'donate_prompt': 'Ti piace il progetto?',
        'donate': 'Dona',
        'section_title': 'Per il tuo prossimo viaggio',
        'does_title': 'Le mappe in un unico posto',
        'does_items': ['Scegli e installa mappe da Freizeitkarte o OpenTopoMap.',
                       'Aggiungi la tua mappa compatibile (.img); le mappe personali non hanno aggiornamenti '
                       'automatici.',
                       'Aggiorna e gestisci le mappe dei fornitori installate da Terento in un’unica app '
                       'Mac.',
                       'Protegge le mappe Garmin originali.'],
        'doesnt_title': 'Gratuito e aperto a tutti',
        'doesnt_items': ['Gratuito, senza bisogno di un account.',
                         'Open source: esplora il codice o contribuisci su GitHub.',
                         'Le mappe provengono dai loro fornitori e mantengono le attribuzioni.'],
        'product_heading': 'Mappe della comunità. Più semplicemente sul tuo Garmin.',
        'beta': 'Beta pubblica per Mac con Apple Silicon. La compatibilità viene valutata modello per '
                'modello.',
        'compatibility': 'Verifica la compatibilità',
        'download': 'Scarica'}}

def render(locale: str, copy: dict[str, object]) -> str:
    canonical = f"{BASE_URL}{localized_path(locale, ABOUT_SLUG)}"
    meta_locale = META_LOCALES[locale]
    alternate_links = "\n".join(
        f'    <link rel="alternate" hreflang="{candidate}" href="{BASE_URL}{localized_path(candidate, ABOUT_SLUG)}">'
        for candidate in LOCALES
    )
    story = "\n".join(f'          <p>{esc(paragraph)}</p>' for paragraph in copy["story"])
    does = "\n".join(f'              <li>{esc(item)}</li>' for item in copy["does_items"])
    doesnt = "\n".join(f'              <li>{esc(item)}</li>' for item in copy["doesnt_items"])
    social = f'''        <div class="about-socials" aria-label="{esc(copy["social_eyebrow"])}">
          <p class="about-social-label">{esc(copy["social_eyebrow"])}</p>
          <div class="about-social-links">
            <a class="about-social-link" href="https://www.linkedin.com/in/gediminasc/" target="_blank" rel="noopener noreferrer" data-umami-event="social-link-click" data-umami-event-location="about-story" data-umami-event-channel="linkedin"><img src="/assets/social/linkedin.svg" alt="" width="16" height="16"><span>{esc(copy["linkedin"])}</span></a>
            <a class="about-social-link" href="https://www.reddit.com/user/MrDonas/" target="_blank" rel="noopener noreferrer" data-umami-event="social-link-click" data-umami-event-location="about-story" data-umami-event-channel="reddit"><img src="/assets/social/reddit.svg" alt="" width="16" height="16"><span>{esc(copy["reddit"])}</span></a>
            <a class="about-social-link about-email-link" href="{EMAIL_HREF}" data-umami-event="support-link-click" data-umami-event-location="about-story" data-umami-event-channel="email"><img src="/assets/social/email.svg" alt="" width="16" height="16"><span>{esc(copy["email"])}</span></a>
          </div>
          <div class="about-donate">
            <span>{esc(copy["donate_prompt"])}</span>
            <a class="about-social-link about-social-link--donate" href="https://buymeacoffee.com/vooz2" target="_blank" rel="noopener noreferrer" data-umami-event="donate" data-umami-event-location="about-story" data-umami-event-channel="donate"><img src="/assets/social/buymeacoffee.svg" alt="" width="16" height="16"><span>{esc(copy["donate"])}</span></a>
          </div>
        </div>'''
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
      <section class="about-intro" aria-labelledby="about-title">
        <div class="shell">
          <p class="eyebrow"><span class="status-dot" aria-hidden="true"></span>Terento</p>
          <h1 id="about-title">{esc(copy["product_heading"])}</h1>
          <p class="about-intro-copy">{esc(copy["description"])}</p>
          <p class="about-beta">{esc(copy["beta"])} <a class="text-link" href="{localized_path(locale, 'compatibility/')}" data-umami-event="compatibility-link-click" data-umami-event-location="about-intro">{esc(copy["compatibility"])}</a></p>
          <div class="hero-actions"><a class="download-action" href="{localized_path(locale, 'download/')}" data-umami-event="download-cta-click" data-umami-event-location="about-intro">{esc(copy["download"])}</a></div>
        </div>
      </section>
      <section class="about-main" aria-labelledby="about-principle-title">
        <div class="shell about-grid">
          <div class="section-heading about-slogan"><h2 id="about-principle-title">{esc(copy["section_title"])}</h2></div>
          <div class="about-list">
            <section class="about-item about-item--group"><h2>{esc(copy["does_title"])}</h2><ul class="about-bullet-list">
{does}
            </ul></section>
            <section class="about-item about-item--group"><h2>{esc(copy["doesnt_title"])}</h2><ul class="about-bullet-list">
{doesnt}
            </ul></section>
          </div>
        </div>
      </section>
      <section class="about-story" aria-labelledby="about-story-title">
        <div class="shell about-story-inner">
          <p class="eyebrow"><span class="status-dot" aria-hidden="true"></span>{esc(copy["story_eyebrow"])}</p>
          <h2 id="about-story-title">{esc(copy["story_heading"])}</h2>
          <div class="about-story-copy">
{story}
          </div>
{social}
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
