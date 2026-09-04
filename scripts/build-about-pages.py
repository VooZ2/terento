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
STYLE_VERSION = "20260905-about-story-v1"
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
        "description": "Meet the maker behind Terento and learn why this free, open-source Mac app exists for third-party Garmin maps.",
        "skip": "Skip to content",
        "story_eyebrow": "A note from the maker",
        "story_heading": "Hi, I’m Gediminas",
        "story": [
            "I think I started using Garmin around the time of the fēnix 3, and over the years it became more than a device — it became part of how I travel and spend time outdoors. I especially enjoy mountain hiking, and before a holiday I like to update my watch with maps for the places I’m visiting.",
            "That process was often harder than it should have been: Garmin Express could get stuck, and installing third-party maps meant finding and downloading them separately, then using additional software. Garmin’s own maps also did not always provide the level of detail I needed.",
            "That frustration made me want a simpler way to get the right maps onto my watch. I’m not a software developer, but as more people started solving practical problems with AI-assisted “vibe coding,” I realized I could try to build that solution myself. That experiment became Terento — an all-in-one Mac app for choosing, installing, updating, and managing third-party maps.",
            "I’m making it free and open source because I’m not building a business around it; I want it to help the community. You should not need to be a technical person to get your watch ready for the places you’re going.",
        ],
        "social_eyebrow": "Connect with the maker",
        "linkedin": "LinkedIn",
        "reddit": "Reddit",
        "donate_prompt": "Like the project?",
        "donate": "Donate",
        "section_title": "Focused on the result — not the process.",
        "does_title": "What Terento does",
        "does_items": [
            "Choose maps from Freizeitkarte or OpenTopoMap, or add your own compatible .img map.",
            "Install, update, and manage third-party maps from one place.",
            "Supports Macs with Apple Silicon processors.",
            "Keeps original Garmin maps protected.",
        ],
        "doesnt_title": "What Terento doesn’t",
        "doesnt_items": [
            "It does not send you back to Garmin Express or BaseCamp.",
            "It does not promise compatibility with every Garmin device.",
            "It does not host, mirror, or repackage map files.",
            "It does not require an account or cloud device profile.",
            "It does not support Macs with Intel processors.",
        ],
    },
    "de": {
        "title": "Über Terento — Kostenlose Open-Source-Garmin-Karten für den Mac",
        "description": "Lerne den Menschen hinter Terento kennen und erfahre, warum diese kostenlose Open-Source-Mac-App für Garmin-Karten entstanden ist.",
        "skip": "Zum Inhalt springen",
        "story_eyebrow": "Eine Notiz vom Entwickler",
        "story_heading": "Hallo, ich bin Gediminas",
        "story": [
            "Ich glaube, dass ich ungefähr mit der fēnix 3 angefangen habe, Garmin zu nutzen, und im Laufe der Jahre wurde Garmin mehr als ein Gerät — es wurde Teil davon, wie ich reise und Zeit draußen verbringe. Ich wandere besonders gern in den Bergen und aktualisiere vor einem Urlaub meine Uhr mit Karten für die Orte, die ich besuche.",
            "Dieser Ablauf war oft schwieriger als nötig: Garmin Express konnte hängen bleiben, während die Installation von Drittanbieter-Karten separate Downloads und zusätzliche Software erforderte. Auch die Garmin-eigenen Karten boten nicht immer die Detailtiefe, die ich brauchte.",
            "Diese Frustration hat in mir den Wunsch nach einer einfacheren Möglichkeit geweckt, die richtigen Karten auf meine Uhr zu bekommen. Ich bin kein Softwareentwickler, aber als immer mehr Menschen praktische Probleme mit KI-gestütztem „Vibe Coding“ lösten, dachte ich, dass ich diese Lösung selbst bauen könnte. Aus diesem Experiment entstand Terento — eine Mac-App zum Auswählen, Installieren, Aktualisieren und Verwalten von Drittanbieter-Karten.",
            "Ich entwickle sie kostenlos und als Open Source, weil ich kein Unternehmen daraus machen möchte, sondern der Community helfen will. Du solltest kein technischer Mensch sein müssen, um deine Uhr für die Orte vorzubereiten, an die du unterwegs bist.",
        ],
        "social_eyebrow": "Mit dem Entwickler verbinden",
        "linkedin": "LinkedIn",
        "reddit": "Reddit",
        "donate_prompt": "Gefällt dir das Projekt?",
        "donate": "Spenden",
        "section_title": "Das Ergebnis im Mittelpunkt — nicht der Prozess.",
        "does_title": "Was Terento macht",
        "does_items": [
            "Wähle Karten von Freizeitkarte oder OpenTopoMap oder füge deine eigene kompatible .img-Karte hinzu.",
            "Installiere, aktualisiere und verwalte Drittanbieter-Karten an einem Ort.",
            "Unterstützt Macs mit Apple-Silicon-Prozessoren.",
            "Originale Garmin-Karten bleiben geschützt.",
        ],
        "doesnt_title": "Was Terento nicht macht",
        "doesnt_items": [
            "Terento schickt dich nicht zurück zu Garmin Express oder BaseCamp.",
            "Terento verspricht keine Kompatibilität mit jedem Garmin-Gerät.",
            "Terento hostet, spiegelt oder verpackt Kartendateien nicht neu.",
            "Terento benötigt kein Konto und kein Geräteprofil in der Cloud.",
            "Terento unterstützt keine Macs mit Intel-Prozessoren.",
        ],
    },
    "fr": {
        "title": "À propos de Terento — Cartes Garmin gratuites et open source sur Mac",
        "description": "Découvrez la personne derrière Terento et pourquoi cette application Mac gratuite et open source pour les cartes Garmin existe.",
        "skip": "Aller au contenu",
        "story_eyebrow": "Une note du créateur",
        "story_heading": "Bonjour, je m’appelle Gediminas",
        "story": [
            "Je crois avoir commencé à utiliser Garmin avec la fēnix 3 et, au fil des années, c’est devenu plus qu’un appareil : une partie de ma façon de voyager et de passer du temps dehors. J’aime particulièrement la randonnée en montagne et, avant les vacances, j’aime mettre à jour ma montre avec les cartes des endroits que je vais visiter.",
            "Ce processus était souvent plus compliqué qu’il ne devrait l’être : Garmin Express pouvait se bloquer, tandis que l’installation de cartes tierces demandait de les trouver et de les télécharger séparément, ainsi que d’utiliser des logiciels supplémentaires. Les cartes Garmin ne fournissaient pas toujours non plus le niveau de détail dont j’avais besoin.",
            "Cette frustration m’a donné envie de trouver une manière plus simple d’ajouter les bonnes cartes à ma montre. Je ne suis pas développeur logiciel, mais lorsque de plus en plus de personnes ont commencé à résoudre des problèmes pratiques avec le « vibe coding » assisté par l’IA, je me suis dit que je pouvais essayer de construire cette solution moi-même. Cette expérience a donné naissance à Terento : une application Mac tout-en-un pour choisir, installer, mettre à jour et gérer des cartes tierces.",
            "Je la rends gratuite et open source parce que je ne cherche pas à en faire une entreprise ; je veux aider la communauté. Vous ne devriez pas avoir besoin d’être une personne technique pour préparer votre montre aux endroits où vous allez.",
        ],
        "social_eyebrow": "Se connecter avec le créateur",
        "linkedin": "LinkedIn",
        "reddit": "Reddit",
        "donate_prompt": "Vous aimez le projet ?",
        "donate": "Faire un don",
        "section_title": "Axé sur le résultat — pas sur le processus.",
        "does_title": "Ce que fait Terento",
        "does_items": [
            "Choisir des cartes auprès de Freizeitkarte ou OpenTopoMap, ou ajouter votre propre carte .img compatible.",
            "Installer, mettre à jour et gérer les cartes tierces depuis un seul endroit.",
            "Prend en charge les Mac équipés de processeurs Apple Silicon.",
            "Protège les cartes Garmin d’origine.",
        ],
        "doesnt_title": "Ce que Terento ne fait pas",
        "doesnt_items": [
            "Terento ne vous renvoie pas vers Garmin Express ou BaseCamp.",
            "Terento ne promet pas la compatibilité avec tous les appareils Garmin.",
            "Terento n’héberge pas, ne met pas en miroir et ne reconditionne pas les fichiers cartographiques.",
            "Terento ne nécessite ni compte ni profil d’appareil dans le cloud.",
            "Terento ne prend pas en charge les Mac équipés de processeurs Intel.",
        ],
    },
    "pl": {
        "title": "O Terento — Bezpłatne, otwartoźródłowe mapy Garmina na Macu",
        "description": "Poznaj twórcę Terento i dowiedz się, dlaczego powstała ta bezpłatna aplikacja open source na Maca do obsługi map Garmina.",
        "skip": "Przejdź do treści",
        "story_eyebrow": "Notatka od twórcy",
        "story_heading": "Cześć, jestem Gediminas",
        "story": [
            "Wydaje mi się, że zacząłem korzystać z Garmina około czasów fēnix 3 i przez lata stał się on czymś więcej niż urządzeniem — stał się częścią tego, jak podróżuję i spędzam czas na świeżym powietrzu. Szczególnie lubię górskie wędrówki, a przed urlopem chcę aktualizować zegarek mapami miejsc, które odwiedzam.",
            "Ten proces często był trudniejszy, niż powinien: Garmin Express potrafił się zawiesić, a instalowanie map innych firm wymagało osobnego wyszukiwania i pobierania map oraz dodatkowego oprogramowania. Mapy Garmina również nie zawsze miały poziom szczegółowości, którego potrzebowałem.",
            "Ta frustracja sprawiła, że chciałem znaleźć prostszy sposób na dodanie właściwych map do zegarka. Nie jestem programistą, ale gdy coraz więcej osób zaczęło rozwiązywać praktyczne problemy za pomocą wspomaganego przez AI „vibe codingu”, pomyślałem, że też mogę spróbować zbudować takie rozwiązanie. Tak powstało Terento — kompleksowa aplikacja na Maca do wybierania, instalowania, aktualizowania i zarządzania mapami innych firm.",
            "Tworzę ją bezpłatnie i jako open source, bo nie buduję z tego firmy; chcę pomóc społeczności. Nie powinieneś być osobą techniczną, aby przygotować zegarek na miejsca, do których się wybierasz.",
        ],
        "social_eyebrow": "Połącz się z twórcą",
        "linkedin": "LinkedIn",
        "reddit": "Reddit",
        "donate_prompt": "Podoba Ci się projekt?",
        "donate": "Wesprzyj",
        "section_title": "Liczy się rezultat — nie proces.",
        "does_title": "Co robi Terento",
        "does_items": [
            "Wybieraj mapy z Freizeitkarte lub OpenTopoMap albo dodaj własną kompatybilną mapę .img.",
            "Instaluj, aktualizuj i zarządzaj mapami innych firm w jednym miejscu.",
            "Obsługuje Maci z procesorami Apple Silicon.",
            "Chroni oryginalne mapy Garmina.",
        ],
        "doesnt_title": "Czego Terento nie robi",
        "doesnt_items": [
            "Terento nie odsyła Cię do Garmin Express ani BaseCamp.",
            "Terento nie obiecuje kompatybilności z każdym urządzeniem Garmin.",
            "Terento nie hostuje, nie kopiuje ani nie przepakowuje plików map.",
            "Terento nie wymaga konta ani chmurowego profilu urządzenia.",
            "Terento nie obsługuje Maców z procesorami Intel.",
        ],
    },
    "cs": {
        "title": "O Terento — Bezplatné open-source mapy Garminu na Macu",
        "description": "Poznejte tvůrce Terento a zjistěte, proč tato bezplatná open-source aplikace pro Mac vznikla pro mapy Garmin.",
        "skip": "Přejít k obsahu",
        "story_eyebrow": "Poznámka od tvůrce",
        "story_heading": "Ahoj, jsem Gediminas",
        "story": [
            "Myslím, že jsem Garmin začal používat někdy kolem modelu fēnix 3 a v průběhu let se z něj stalo víc než jen zařízení — stal se součástí toho, jak cestuji a trávím čas venku. Nejraději chodím po horách a před dovolenou si rád aktualizuji hodinky mapami míst, která navštívím.",
            "Tento proces byl často složitější, než by měl být: Garmin Express se mohl zaseknout, zatímco instalace map třetích stran vyžadovala jejich samostatné hledání a stahování i další software. Ani vlastní mapy Garminu mi ne vždy poskytly potřebnou úroveň detailů.",
            "Tato frustrace mě přivedla k myšlence najít jednodušší způsob, jak dostat správné mapy do hodinek. Nejsem softwarový vývojář, ale když stále více lidí začalo řešit praktické problémy pomocí AI asistovaného „vibe codingu“, uvědomil jsem si, že bych mohl zkusit toto řešení vytvořit sám. Z tohoto experimentu vzniklo Terento — komplexní aplikace pro Mac k výběru, instalaci, aktualizaci a správě map třetích stran.",
            "Vytvářím ji bezplatně a jako open source, protože z ní nechci budovat firmu; chci pomoci komunitě. Neměli byste být technicky zaměření, abyste mohli připravit hodinky na místa, kam míříte.",
        ],
        "social_eyebrow": "Spojte se s tvůrcem",
        "linkedin": "LinkedIn",
        "reddit": "Reddit",
        "donate_prompt": "Líbí se vám projekt?",
        "donate": "Přispět",
        "section_title": "Zaměřeno na výsledek — ne na proces.",
        "does_title": "Co Terento dělá",
        "does_items": [
            "Vyberte mapy z Freizeitkarte nebo OpenTopoMap, případně přidejte vlastní kompatibilní mapu .img.",
            "Instalujte, aktualizujte a spravujte mapy třetích stran z jednoho místa.",
            "Podporuje Macy s procesory Apple Silicon.",
            "Chrání originální mapy Garminu.",
        ],
        "doesnt_title": "Co Terento nedělá",
        "doesnt_items": [
            "Terento vás neposílá zpět do Garmin Express nebo BaseCamp.",
            "Terento neslibuje kompatibilitu s každým zařízením Garmin.",
            "Terento mapové soubory nehostuje, nezrcadlí ani znovu nebalí.",
            "Terento nevyžaduje účet ani cloudový profil zařízení.",
            "Terento nepodporuje Macy s procesory Intel.",
        ],
    },
    "it": {
        "title": "Informazioni su Terento — Mappe Garmin gratuite e open source su Mac",
        "description": "Scopri chi c’è dietro Terento e perché esiste questa app gratuita e open source per Mac dedicata alle mappe Garmin.",
        "skip": "Vai al contenuto",
        "story_eyebrow": "Una nota dal creatore",
        "story_heading": "Ciao, sono Gediminas",
        "story": [
            "Credo di aver iniziato a usare Garmin intorno ai tempi del fēnix 3 e, negli anni, è diventato più di un dispositivo: è diventato parte del modo in cui viaggio e trascorro il tempo all’aperto. Amo soprattutto le escursioni in montagna e, prima di una vacanza, mi piace aggiornare l’orologio con le mappe dei luoghi che visiterò.",
            "Questo processo era spesso più complicato del necessario: Garmin Express poteva bloccarsi, mentre installare mappe di terze parti significava cercarle e scaricarle separatamente e usare software aggiuntivo. Anche le mappe Garmin non offrivano sempre il livello di dettaglio di cui avevo bisogno.",
            "Questa frustrazione mi ha fatto desiderare un modo più semplice per portare le mappe giuste sul mio orologio. Non sono uno sviluppatore software, ma quando sempre più persone hanno iniziato a risolvere problemi pratici con il “vibe coding” assistito dall’AI, ho capito che potevo provare a costruire da solo la soluzione che cercavo. Da quell’esperimento è nata Terento — un’app Mac tutto-in-uno per scegliere, installare, aggiornare e gestire mappe di terze parti.",
            "La rendo gratuita e open source perché non sto costruendo un’azienda; voglio aiutare la community. Non dovrebbe servire essere persone tecniche per preparare il proprio orologio ai luoghi verso cui si è diretti.",
        ],
        "social_eyebrow": "Connettiti con il creatore",
        "linkedin": "LinkedIn",
        "reddit": "Reddit",
        "donate_prompt": "Ti piace il progetto?",
        "donate": "Dona",
        "section_title": "Il risultato prima di tutto — non il processo.",
        "does_title": "Cosa fa Terento",
        "does_items": [
            "Scegli mappe da Freizeitkarte o OpenTopoMap oppure aggiungi la tua mappa .img compatibile.",
            "Installa, aggiorna e gestisci le mappe di terze parti da un unico posto.",
            "Supporta i Mac con processori Apple Silicon.",
            "Protegge le mappe Garmin originali.",
        ],
        "doesnt_title": "Cosa non fa Terento",
        "doesnt_items": [
            "Terento non ti rimanda a Garmin Express o BaseCamp.",
            "Terento non promette la compatibilità con ogni dispositivo Garmin.",
            "Terento non ospita, non replica e non riconfeziona i file delle mappe.",
            "Terento non richiede un account né un profilo del dispositivo nel cloud.",
            "Terento non supporta i Mac con processori Intel.",
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
    story = "\n".join(f'          <p>{esc(paragraph)}</p>' for paragraph in copy["story"])
    does = "\n".join(f'              <li>{esc(item)}</li>' for item in copy["does_items"])
    doesnt = "\n".join(f'              <li>{esc(item)}</li>' for item in copy["doesnt_items"])
    social = f'''        <div class="about-socials" aria-label="{esc(copy["social_eyebrow"])}">
          <p class="about-social-label">{esc(copy["social_eyebrow"])}</p>
          <div class="about-social-links">
            <a class="about-social-link" href="https://www.linkedin.com/in/gediminasc/" target="_blank" rel="noopener noreferrer" data-umami-event="social-link-click" data-umami-event-location="about-story" data-umami-event-channel="linkedin"><img src="/assets/social/linkedin.svg" alt="" width="16" height="16"><span>{esc(copy["linkedin"])}</span></a>
            <a class="about-social-link" href="https://www.reddit.com/user/MrDonas/" target="_blank" rel="noopener noreferrer" data-umami-event="social-link-click" data-umami-event-location="about-story" data-umami-event-channel="reddit"><img src="/assets/social/reddit.svg" alt="" width="16" height="16"><span>{esc(copy["reddit"])}</span></a>
          </div>
          <div class="about-donate">
            <span>{esc(copy["donate_prompt"])}</span>
            <a class="about-social-link about-social-link--donate" href="https://buymeacoffee.com/vooz2" target="_blank" rel="noopener noreferrer" data-umami-event="support-link-click" data-umami-event-location="about-story" data-umami-event-channel="donate"><img src="/assets/social/buymeacoffee.svg" alt="" width="16" height="16"><span>{esc(copy["donate"])}</span></a>
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
      <section class="about-story" aria-labelledby="about-title">
        <div class="shell about-story-inner">
          <p class="eyebrow">{esc(copy["story_eyebrow"])}</p>
          <h1 id="about-title">{esc(copy["story_heading"])}</h1>
          <div class="about-story-copy">
{story}
          </div>
{social}
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
