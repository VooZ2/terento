#!/usr/bin/env python3
"""Build the localized public About pages from one shared content source."""

from __future__ import annotations

import html
import json
import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = runpy.run_path(str(ROOT / "scripts/page_schema.py"))
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


COPY = {
    "en": {
        "title": "About Terento: Free, Open-Source Garmin Maps",
        "description": "Why a Garmin hiker built Terento: a free, open-source way to get free maps onto Garmin watches and Edge bike computers. No account, no fees.",
        "skip": "Skip to content",
        "h1": "A free map app, made by one Garmin hiker",
        "lede": "Terento puts free community maps on Garmin watches and Edge bike computers. It’s a free, open-source Mac app, plus a web installer that runs in your browser.",
        "download": "Download",
        "story_heading": "Why I made it",
        "story": [
            "I’m Gediminas. I use a Garmin and love hiking in the mountains. Before a trip, I want my watch ready with maps of where I’m going, and getting them onto it took more effort than it should.",
            "I built Terento to make that easier, for me and for anyone else with a Garmin. It’s free and open source because I want it to be useful to the community.",
        ],
        "social_label": "Get in touch",
        "linkedin": "LinkedIn",
        "reddit": "Reddit",
        "email": "Email",
        "donate_text": "Terento is free and stays free. If it helps you, a donation helps pay for the server behind the web installer and map previews, and for the Apple developer membership the Mac app needs. Donations don’t unlock anything.",
        "donate": "Buy me a coffee",
        "main_heading": "What Terento is, and what it isn’t",
        "is_title": "What it is",
        "is_items": [
            "A free Mac app for Apple Silicon Macs with macOS 13 or later.",
            "A {web_installer} for Chrome, Microsoft Edge, Opera or Brave on a Mac, with Linux still in testing.",
            "A way to install, update and remove free maps on Garmin watches and newer Edge bike computers with map support.",
            "Room for your own compatible map (.img) too. Your own maps don’t update automatically.",
            "Free to use, with no account.",
        ],
        "web_installer": "web installer",
        "isnt_title": "What it isn’t",
        "isnt_items": [
            "A Garmin product. Garmin doesn’t make, endorse or certify Terento.",
            "A map maker. The maps come from the community projects listed below.",
            "A navigation app. You navigate on your Garmin, as you always do.",
            "An app for Windows, phones or tablets.",
            "A risk to your original Garmin maps. Terento never touches them.",
            "A promise that every Garmin works. {compatibility} lists the models people have already installed maps on.",
        ],
        "compatibility": "Compatibility",
        "open_heading": "Open code, community maps",
        "open_code": "Terento’s code is public on {github} under the GPL-3.0 licence. You can read it, report a problem or help improve it.",
        "open_maps": "The maps are made by {opentopomap}, {freizeitkarte}, {maprando}, {bbbike} and {osmapapl}, from data by {osm}. Terento gets each map from its original project, and the licences and credits stay with them.",
        "osm": "OpenStreetMap contributors",
    },
    "de": {
        "title": "Über Terento: kostenlose Open-Source-Garmin-Karten",
        "description": "Warum ein Garmin-Wanderer Terento gebaut hat: ein kostenloser, offener Weg, freie Karten auf Garmin-Uhren und Edge-Radcomputer zu bringen. Ohne Konto.",
        "skip": "Zum Inhalt springen",
        "h1": "Eine kostenlose Karten-App, gebaut von einem Garmin-Wanderer",
        "lede": "Terento bringt kostenlose Community-Karten auf Garmin-Uhren und Edge-Radcomputer. Es ist eine kostenlose Open-Source-Mac-App und dazu ein Web-Installer, der im Browser läuft.",
        "download": "Download",
        "story_heading": "Warum ich es gebaut habe",
        "story": [
            "Ich bin Gediminas. Ich nutze eine Garmin und wandere gern in den Bergen. Vor einer Reise möchte ich Karten für mein Ziel auf der Uhr haben, und sie dorthin zu bekommen, war aufwendiger als nötig.",
            "Ich habe Terento gebaut, um das einfacher zu machen, für mich und für alle anderen mit einer Garmin. Es ist kostenlos und quelloffen, weil ich möchte, dass es der Community hilft.",
        ],
        "social_label": "Schreib mir",
        "linkedin": "LinkedIn",
        "reddit": "Reddit",
        "email": "E-Mail",
        "donate_text": "Terento ist kostenlos und bleibt es. Wenn es dir hilft, trägt eine Spende den Server hinter dem Web-Installer und den Kartenvorschauen sowie die Apple-Entwicklermitgliedschaft, die die Mac-App braucht. Spenden schalten nichts frei.",
        "donate": "Spendier mir einen Kaffee",
        "main_heading": "Was Terento ist und was nicht",
        "is_title": "Was es ist",
        "is_items": [
            "Eine kostenlose Mac-App für Macs mit Apple Silicon und macOS 13 oder neuer.",
            "Ein {web_installer} für Chrome, Microsoft Edge, Opera oder Brave auf dem Mac; Linux wird noch getestet.",
            "Ein Weg, kostenlose Karten auf Garmin-Uhren und neueren Edge-Radcomputern mit Kartenunterstützung zu installieren, zu aktualisieren und zu entfernen.",
            "Auch für deine eigene kompatible Karte (.img). Eigene Karten werden nicht automatisch aktualisiert.",
            "Kostenlos nutzbar, ohne Konto.",
        ],
        "web_installer": "Web-Installer",
        "isnt_title": "Was es nicht ist",
        "isnt_items": [
            "Ein Garmin-Produkt. Garmin hat Terento weder entwickelt noch empfohlen oder zertifiziert.",
            "Ein Kartenhersteller. Die Karten stammen von den unten genannten Community-Projekten.",
            "Eine Navigations-App. Du navigierst wie gewohnt auf deiner Garmin.",
            "Eine App für Windows, Smartphones oder Tablets.",
            "Eine Gefahr für deine originalen Garmin-Karten. Terento rührt sie nie an.",
            "Ein Versprechen, dass jede Garmin funktioniert. Die Seite {compatibility} zeigt die Modelle, auf denen schon Karten installiert wurden.",
        ],
        "compatibility": "Kompatibilität",
        "open_heading": "Offener Code, Community-Karten",
        "open_code": "Der Code von Terento ist öffentlich auf {github}, unter der Lizenz GPL-3.0. Du kannst ihn lesen, ein Problem melden oder beim Verbessern helfen.",
        "open_maps": "Die Karten stammen von {opentopomap}, {freizeitkarte}, {maprando}, {bbbike} und {osmapapl}, mit Daten der {osm}. Terento holt jede Karte beim ursprünglichen Projekt; Lizenzen und Quellenangaben bleiben bei ihnen.",
        "osm": "OpenStreetMap-Mitwirkenden",
    },
    "fr": {
        "title": "À propos de Terento : cartes Garmin gratuites et libres",
        "description": "Pourquoi un randonneur Garmin a créé Terento : un moyen gratuit et open source d’installer des cartes libres sur montres et compteurs Edge Garmin.",
        "skip": "Aller au contenu",
        "h1": "Une appli de cartes gratuite, faite par un randonneur Garmin",
        "lede": "Terento installe des cartes communautaires gratuites sur les montres Garmin et les compteurs vélo Edge. C’est une application Mac gratuite et open source, avec un installateur web qui fonctionne dans votre navigateur.",
        "download": "Télécharger",
        "story_heading": "Pourquoi je l’ai créé",
        "story": [
            "Je suis Gediminas. J’utilise une Garmin et j’adore randonner en montagne. Avant un voyage, je veux que ma montre ait les cartes de ma destination, et les y mettre demandait plus d’efforts que nécessaire.",
            "J’ai créé Terento pour simplifier cela, pour moi et pour tous ceux qui ont une Garmin. Il est gratuit et open source parce que je veux qu’il soit utile à la communauté.",
        ],
        "social_label": "Me contacter",
        "linkedin": "LinkedIn",
        "reddit": "Reddit",
        "email": "E-mail",
        "donate_text": "Terento est gratuit et le restera. S’il vous est utile, un don aide à payer le serveur de l’installateur web et des aperçus de cartes, ainsi que l’adhésion développeur Apple nécessaire à l’application Mac. Les dons ne débloquent rien.",
        "donate": "Offrez-moi un café",
        "main_heading": "Ce qu’est Terento, et ce qu’il n’est pas",
        "is_title": "Ce qu’il est",
        "is_items": [
            "Une application Mac gratuite pour les Mac Apple Silicon sous macOS 13 ou version ultérieure.",
            "Un {web_installer} pour Chrome, Microsoft Edge, Opera ou Brave sur Mac ; Linux est encore en test.",
            "Un moyen d’installer, de mettre à jour et de supprimer des cartes gratuites sur les montres Garmin et les compteurs vélo Edge récents compatibles avec les cartes.",
            "Une place aussi pour votre propre carte compatible (.img). Vos cartes personnelles ne se mettent pas à jour automatiquement.",
            "Gratuit, sans compte.",
        ],
        "web_installer": "installateur web",
        "isnt_title": "Ce qu’il n’est pas",
        "isnt_items": [
            "Un produit Garmin. Garmin ne fabrique, ne recommande ni ne certifie Terento.",
            "Un éditeur de cartes. Les cartes viennent des projets communautaires cités plus bas.",
            "Une application de navigation. Vous naviguez sur votre Garmin, comme d’habitude.",
            "Une application pour Windows, téléphones ou tablettes.",
            "Un risque pour vos cartes Garmin d’origine. Terento n’y touche jamais.",
            "Une promesse que chaque Garmin fonctionne. La page {compatibility} liste les modèles sur lesquels des cartes ont déjà été installées.",
        ],
        "compatibility": "Compatibilité",
        "open_heading": "Code ouvert, cartes communautaires",
        "open_code": "Le code de Terento est public sur {github}, sous licence GPL-3.0. Vous pouvez le lire, signaler un problème ou aider à l’améliorer.",
        "open_maps": "Les cartes sont réalisées par {opentopomap}, {freizeitkarte}, {maprando}, {bbbike} et {osmapapl}, à partir des données des {osm}. Terento récupère chaque carte auprès de son projet d’origine ; licences et attributions restent les leurs.",
        "osm": "contributeurs d’OpenStreetMap",
    },
    "pl": {
        "title": "O Terento: darmowe mapy open source na Garmina",
        "description": "Dlaczego turysta z Garminem stworzył Terento: darmowy, otwarty sposób na wgranie darmowych map na zegarki Garmin i liczniki rowerowe Edge. Bez konta.",
        "skip": "Przejdź do treści",
        "h1": "Darmowa aplikacja do map, stworzona przez turystę z Garminem",
        "lede": "Terento wgrywa darmowe mapy społeczności na zegarki Garmin i liczniki rowerowe Edge. To bezpłatna aplikacja open source na Maca oraz instalator webowy działający w przeglądarce.",
        "download": "Pobierz",
        "story_heading": "Dlaczego to zrobiłem",
        "story": [
            "Mam na imię Gediminas. Używam Garmina i uwielbiam górskie wędrówki. Przed wyjazdem chcę mieć w zegarku mapy miejsc, do których jadę, a wgranie ich wymagało więcej wysiłku, niż powinno.",
            "Stworzyłem Terento, żeby to ułatwić sobie i wszystkim innym z Garminem. Jest bezpłatne i open source, bo chcę, żeby służyło społeczności.",
        ],
        "social_label": "Napisz do mnie",
        "linkedin": "LinkedIn",
        "reddit": "Reddit",
        "email": "E-mail",
        "donate_text": "Terento jest bezpłatne i takie zostanie. Jeśli Ci pomaga, darowizna pomaga opłacić serwer instalatora webowego i podglądów map oraz członkostwo w programie deweloperskim Apple, którego wymaga aplikacja na Maca. Darowizny niczego nie odblokowują.",
        "donate": "Postaw mi kawę",
        "main_heading": "Czym Terento jest, a czym nie jest",
        "is_title": "Czym jest",
        "is_items": [
            "Bezpłatną aplikacją dla Maców z Apple Silicon i macOS 13 lub nowszym.",
            "{web_installer} dla Chrome, Microsoft Edge, Opery lub Brave na Macu; Linux jest jeszcze testowany.",
            "Sposobem na instalowanie, aktualizowanie i usuwanie darmowych map na zegarkach Garmin i nowszych licznikach rowerowych Edge obsługujących mapy.",
            "Miejscem także na Twoją własną zgodną mapę (.img). Własne mapy nie aktualizują się automatycznie.",
            "Bezpłatnym narzędziem, bez zakładania konta.",
        ],
        "web_installer": "Instalatorem webowym",
        "isnt_title": "Czym nie jest",
        "isnt_items": [
            "Produktem Garmina. Garmin nie tworzy, nie poleca ani nie certyfikuje Terento.",
            "Twórcą map. Mapy pochodzą od projektów społecznościowych wymienionych niżej.",
            "Aplikacją do nawigacji. Nawigujesz na Garminie, jak zawsze.",
            "Aplikacją na Windows, telefony ani tablety.",
            "Zagrożeniem dla oryginalnych map Garmina. Terento nigdy ich nie dotyka.",
            "Obietnicą, że każdy Garmin zadziała. Strona {compatibility} pokazuje modele, na które już wgrano mapy.",
        ],
        "compatibility": "Kompatybilność",
        "open_heading": "Otwarty kod, mapy społeczności",
        "open_code": "Kod Terento jest publiczny na {github}, na licencji GPL-3.0. Możesz go przeczytać, zgłosić problem lub pomóc go ulepszyć.",
        "open_maps": "Mapy tworzą {opentopomap}, {freizeitkarte}, {maprando}, {bbbike} i {osmapapl} na podstawie danych {osm}. Terento pobiera każdą mapę z jej oryginalnego projektu, a licencje i informacje o autorstwie pozostają przy nich.",
        "osm": "współtwórców OpenStreetMap",
    },
    "cs": {
        "title": "O Terento: bezplatné open-source mapy pro Garmin",
        "description": "Proč turista s Garminem vytvořil Terento: bezplatný a otevřený způsob, jak dostat mapy zdarma do hodinek Garmin a cyklopočítačů Edge. Bez účtu.",
        "skip": "Přejít k obsahu",
        "h1": "Bezplatná aplikace na mapy od jednoho turisty s Garminem",
        "lede": "Terento nahrává bezplatné komunitní mapy do hodinek Garmin a cyklopočítačů Edge. Je to bezplatná open-source aplikace pro Mac a k tomu webový instalátor, který běží v prohlížeči.",
        "download": "Stáhnout",
        "story_heading": "Proč jsem ho vytvořil",
        "story": [
            "Jmenuji se Gediminas. Používám Garmin a rád chodím po horách. Před cestou chci mít v hodinkách mapy míst, kam jedu, a dostat je tam stálo víc úsilí, než by mělo.",
            "Vytvořil jsem Terento, abych to usnadnil sobě i všem ostatním s Garminem. Je zdarma a s otevřeným kódem, protože chci, aby pomáhalo komunitě.",
        ],
        "social_label": "Napište mi",
        "linkedin": "LinkedIn",
        "reddit": "Reddit",
        "email": "E-mail",
        "donate_text": "Terento je zdarma a zdarma zůstane. Pokud vám pomáhá, příspěvek pomůže zaplatit server pro webový instalátor a náhledy map a také členství v Apple Developer Program, které aplikace pro Mac potřebuje. Příspěvky nic neodemykají.",
        "donate": "Kupte mi kávu",
        "main_heading": "Co Terento je a co není",
        "is_title": "Co je",
        "is_items": [
            "Bezplatná aplikace pro Macy s Apple Silicon a macOS 13 nebo novějším.",
            "{web_installer} pro Chrome, Microsoft Edge, Operu nebo Brave na Macu; Linux se ještě testuje.",
            "Způsob, jak instalovat, aktualizovat a odebírat bezplatné mapy v hodinkách Garmin a novějších cyklopočítačích Edge s podporou map.",
            "Místo i pro vaši vlastní kompatibilní mapu (.img). Vlastní mapy se automaticky neaktualizují.",
            "Zdarma, bez účtu.",
        ],
        "web_installer": "Webový instalátor",
        "isnt_title": "Co není",
        "isnt_items": [
            "Produkt Garminu. Garmin Terento nevyrábí, nedoporučuje ani necertifikuje.",
            "Tvůrce map. Mapy pocházejí od komunitních projektů uvedených níže.",
            "Navigační aplikace. Navigujete v Garminu jako obvykle.",
            "Aplikace pro Windows, telefony nebo tablety.",
            "Riziko pro vaše původní mapy Garmin. Terento se jich nikdy nedotkne.",
            "Slib, že bude fungovat každý Garmin. Stránka {compatibility} ukazuje modely, do kterých už někdo mapy nahrál.",
        ],
        "compatibility": "Kompatibilita",
        "open_heading": "Otevřený kód, komunitní mapy",
        "open_code": "Kód Terento je veřejně na {github} pod licencí GPL-3.0. Můžete si ho přečíst, nahlásit problém nebo pomoct s vylepšením.",
        "open_maps": "Mapy vytvářejí {opentopomap}, {freizeitkarte}, {maprando}, {bbbike} a {osmapapl} z dat {osm}. Terento bere každou mapu z jejího původního projektu a licence i uvedení autorů zůstávají u nich.",
        "osm": "přispěvatelů OpenStreetMap",
    },
    "it": {
        "title": "Informazioni su Terento: mappe Garmin gratuite e libere",
        "description": "Perché un escursionista con Garmin ha creato Terento: un modo gratuito e open source per mettere mappe libere su orologi Garmin e ciclocomputer Edge.",
        "skip": "Vai al contenuto",
        "h1": "Un’app di mappe gratuita, fatta da un escursionista con Garmin",
        "lede": "Terento installa mappe gratuite della community su orologi Garmin e ciclocomputer Edge. È un’app Mac gratuita e open source, più un installer web che funziona nel browser.",
        "download": "Scarica",
        "story_heading": "Perché l’ho creato",
        "story": [
            "Sono Gediminas. Uso un Garmin e amo le escursioni in montagna. Prima di un viaggio voglio l’orologio pronto con le mappe di dove vado, e caricarle richiedeva più impegno del necessario.",
            "Ho creato Terento per rendere tutto più semplice, per me e per chiunque abbia un Garmin. È gratuito e open source perché voglio che sia utile alla comunità.",
        ],
        "social_label": "Scrivimi",
        "linkedin": "LinkedIn",
        "reddit": "Reddit",
        "email": "Email",
        "donate_text": "Terento è gratuito e lo resterà. Se ti è utile, una donazione aiuta a pagare il server dell’installer web e delle anteprime delle mappe, e l’iscrizione da sviluppatore Apple di cui ha bisogno l’app Mac. Le donazioni non sbloccano nulla.",
        "donate": "Offrimi un caffè",
        "main_heading": "Cos’è Terento, e cosa non è",
        "is_title": "Cos’è",
        "is_items": [
            "Un’app gratuita per Mac con Apple Silicon e macOS 13 o successivo.",
            "Un {web_installer} per Chrome, Microsoft Edge, Opera o Brave su Mac; Linux è ancora in prova.",
            "Un modo per installare, aggiornare e rimuovere mappe gratuite su orologi Garmin e ciclocomputer Edge recenti con supporto mappe.",
            "Spazio anche per la tua mappa compatibile (.img). Le mappe personali non si aggiornano automaticamente.",
            "Gratuito, senza account.",
        ],
        "web_installer": "installer web",
        "isnt_title": "Cosa non è",
        "isnt_items": [
            "Un prodotto Garmin. Garmin non produce, non approva e non certifica Terento.",
            "Un produttore di mappe. Le mappe vengono dai progetti della community elencati sotto.",
            "Un’app di navigazione. Navighi sul tuo Garmin, come sempre.",
            "Un’app per Windows, telefoni o tablet.",
            "Un rischio per le mappe Garmin originali. Terento non le tocca mai.",
            "Una promessa che ogni Garmin funzioni. La pagina {compatibility} elenca i modelli su cui sono già state installate mappe.",
        ],
        "compatibility": "Compatibilità",
        "open_heading": "Codice aperto, mappe della community",
        "open_code": "Il codice di Terento è pubblico su {github}, con licenza GPL-3.0. Puoi leggerlo, segnalare un problema o aiutare a migliorarlo.",
        "open_maps": "Le mappe sono realizzate da {opentopomap}, {freizeitkarte}, {maprando}, {bbbike} e {osmapapl}, con i dati dei {osm}. Terento prende ogni mappa dal suo progetto originale; licenze e attribuzioni restano loro.",
        "osm": "contributori di OpenStreetMap",
    },
}


MAP_PROJECTS = {
    "opentopomap": ("OpenTopoMap", "https://garmin.opentopomap.org/"),
    "freizeitkarte": ("Freizeitkarte", "https://www.freizeitkarte-osm.de/"),
    "maprando": ("MapRando", "https://ravenfeld.gitlab.io/open-garmin-map/"),
    "bbbike": ("BBBike", "https://garmin.bbbike.org"),
    "osmapapl": ("OSMapaPL", "https://osmapa-garmin.las.org.pl/"),
}


def with_links(text: str, links: dict[str, str]) -> str:
    """Escape copy, then swap {name} placeholders for ready-made link markup."""
    out = esc(text)
    for name, markup in links.items():
        out = out.replace("{" + name + "}", markup)
    assert "{" not in out, f"unfilled placeholder in: {text}"
    return out


def isnt_item(text: str, links: dict[str, str]) -> str:
    """Bold the short lead phrase so the list scans as 'not X. Why.'"""
    lead, _, rest = text.partition(". ")
    if not rest:
        return f"<strong>{with_links(text, links)}</strong>"
    return f"<strong>{with_links(lead, links)}.</strong> {with_links(rest, links)}"


def render(locale: str, copy: dict[str, object]) -> str:
    canonical = f"{BASE_URL}{localized_path(locale, ABOUT_SLUG)}"
    meta_locale = META_LOCALES[locale]
    alternate_links = "\n".join(
        f'    <link rel="alternate" hreflang="{candidate}" href="{BASE_URL}{localized_path(candidate, ABOUT_SLUG)}">'
        for candidate in LOCALES
    )
    links = {
        "web_installer": f'<a class="text-link" href="{localized_path(locale, "install/")}" data-umami-event="web-installer-link-click" data-umami-event-location="about-main">{esc(copy["web_installer"])}</a>',
        "compatibility": f'<a class="text-link" href="{localized_path(locale, "compatibility/")}" data-umami-event="compatibility-link-click" data-umami-event-location="about-main">{esc(copy["compatibility"])}</a>',
        "github": '<a class="text-link" href="https://github.com/VooZ2/terento">GitHub</a>',
        "osm": f'<a class="text-link" href="https://www.openstreetmap.org/copyright">{esc(copy["osm"])}</a>',
        **{key: f'<a class="text-link" href="{url}">{name}</a>' for key, (name, url) in MAP_PROJECTS.items()},
    }
    story = "\n".join(f'            <p>{esc(paragraph)}</p>' for paragraph in copy["story"])
    is_items = "\n".join(f'              <li>{with_links(item, links)}</li>' for item in copy["is_items"])
    isnt_items = "\n".join(f'              <li>{isnt_item(item, links)}</li>' for item in copy["isnt_items"])
    social = f'''          <div class="about-socials" aria-labelledby="about-social-title">
            <h3 class="about-social-label" id="about-social-title">{esc(copy["social_label"])}</h3>
            <div class="about-social-links">
              <a class="about-social-link" href="https://www.linkedin.com/in/gediminasc/" target="_blank" rel="noopener noreferrer" data-umami-event="social-link-click" data-umami-event-location="about-story" data-umami-event-channel="linkedin"><img src="/assets/social/linkedin.svg" alt="" width="16" height="16"><span>{esc(copy["linkedin"])}</span></a>
              <a class="about-social-link" href="https://www.reddit.com/user/MrDonas/" target="_blank" rel="noopener noreferrer" data-umami-event="social-link-click" data-umami-event-location="about-story" data-umami-event-channel="reddit"><img src="/assets/social/reddit.svg" alt="" width="16" height="16"><span>{esc(copy["reddit"])}</span></a>
              <a class="about-social-link about-email-link" href="{EMAIL_HREF}" data-umami-event="support-link-click" data-umami-event-location="about-story" data-umami-event-channel="email"><img src="/assets/social/email.svg" alt="" width="16" height="16"><span>{esc(copy["email"])}</span></a>
            </div>
            <div class="about-donate">
              <p>{esc(copy["donate_text"])}</p>
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
{SCHEMA["json_ld_block"](locale, ABOUT_SLUG, "AboutPage")}


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
        <div class="shell about-intro-text">
            <h1 id="about-title">{esc(copy["h1"])}</h1>
            <p class="about-intro-copy">{esc(copy["lede"])}</p>
            <div class="hero-actions"><a class="download-action" href="{localized_path(locale, 'download/')}" data-umami-event="download-cta-click" data-umami-event-location="about-intro">{esc(copy["download"])}</a></div>
          </div>
      </section>
      <section class="about-story" aria-labelledby="about-story-title">
        <div class="shell about-story-inner">
          <h2 id="about-story-title">{esc(copy["story_heading"])}</h2>
          <div class="about-story-copy">
{story}
          </div>
{social}
        </div>
      </section>
      <section class="about-main" aria-labelledby="about-principle-title">
        <div class="shell about-grid">
          <div class="section-heading about-slogan"><h2 id="about-principle-title">{esc(copy["main_heading"])}</h2></div>
          <div class="about-list">
            <section class="about-item about-item--group" aria-labelledby="about-is-title"><h3 id="about-is-title">{esc(copy["is_title"])}</h3><ul class="about-bullet-list">
{is_items}
            </ul></section>
            <section class="about-item about-item--group" aria-labelledby="about-isnt-title"><h3 id="about-isnt-title">{esc(copy["isnt_title"])}</h3><ul class="about-bullet-list">
{isnt_items}
            </ul></section>
          </div>
        </div>
      </section>
      <section class="about-v2-open" aria-labelledby="about-open-title">
        <div class="shell">
          <h2 id="about-open-title">{esc(copy["open_heading"])}</h2>
          <p>{with_links(copy["open_code"], links)}</p>
          <p>{with_links(copy["open_maps"], links)}</p>
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
