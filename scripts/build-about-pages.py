#!/usr/bin/env python3
"""Build the localized public About pages from one shared content source."""

from __future__ import annotations

import html
import json
import runpy
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = runpy.run_path(str(ROOT / "scripts/page_schema.py"))
COMPONENTS = runpy.run_path(str(ROOT / "scripts/site_components.py"))
LINKEDIN_URL = "https://www.linkedin.com/in/gediminasc/"
REDDIT_URL = "https://www.reddit.com/user/MrDonas/"
BASE_URL = "https://terento.app"
ABOUT_SLUG = "about/"
SHELL_VERSION = "20260905-in-page-language-v1"
STYLE_VERSION = "20261119-site-refresh-v6"
UMAMI_SCRIPT_VERSION = "20261114-umami-monitoring"
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
        "h1": "About Terento",
        "role": "Maker of Terento",
        "lead": "A free map app, made by one Garmin hiker.",
        "maker_heading": "Who makes it",
        "story": [
            "I use a Garmin fēnix. On vacation I like to plan hikes to get to know a country, especially in the mountains of Europe. Before each trip, I wanted maps on my watch. On a Mac, that meant connecting the watch, searching how to add maps, finding them, downloading them and copying them over.",
            "I built Terento to make that simple: connect, install, done.",
            "It’s free and open source because I like my Garmin and want to help people in the same situation.",
        ],
        "contact": "If you have questions or feedback, you can reach me here:",
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
            "A map maker. The maps come from community projects, credited on the {maps} page.",
            "A navigation app. You navigate on your Garmin, as you always do.",
            "An app for Windows, phones or tablets.",
            "A risk to your original Garmin maps. Terento never touches them.",
            "A promise that every Garmin works. {compatibility} lists the models people have already installed maps on.",
        ],
        "compatibility": "Compatibility",
        "maps": "Maps",
        "mentions_heading": "Featured on",
        "mentions_intro": "Thank you to the websites and reviewers who have tried, featured or recommended Terento.",
        "video": "video",
    },
    "de": {
        "title": "Über Terento: kostenlose Open-Source-Garmin-Karten",
        "description": "Warum ein Garmin-Wanderer Terento gebaut hat: ein kostenloser, offener Weg, freie Karten auf Garmin-Uhren und Edge-Radcomputer zu bringen. Ohne Konto.",
        "skip": "Zum Inhalt springen",
        "h1": "Über Terento",
        "role": "Macher von Terento",
        "lead": "Eine kostenlose Karten-App, gebaut von einem Garmin-Wanderer.",
        "maker_heading": "Wer es macht",
        "story": [
            "Ich nutze eine Garmin fēnix. Im Urlaub plane ich gern Wanderungen, um ein Land kennenzulernen, besonders in den Bergen Europas. Vor jeder Reise wollte ich Karten auf meiner Uhr haben. Auf dem Mac hieß das: die Uhr anschließen, suchen, wie man Karten hinzufügt, sie finden, herunterladen und auf die Uhr kopieren.",
            "Ich habe Terento gebaut, um das einfach zu machen: verbinden, installieren, fertig.",
            "Es ist kostenlos und Open Source, weil ich meine Garmin mag und Menschen in derselben Lage helfen möchte.",
        ],
        "contact": "Wenn du Fragen oder Feedback hast, erreichst du mich hier:",
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
            "Ein Kartenhersteller. Die Karten stammen von Community-Projekten, die auf der Seite {maps} genannt sind.",
            "Eine Navigations-App. Du navigierst wie gewohnt auf deiner Garmin.",
            "Eine App für Windows, Smartphones oder Tablets.",
            "Eine Gefahr für deine originalen Garmin-Karten. Terento rührt sie nie an.",
            "Ein Versprechen, dass jede Garmin funktioniert. Die Seite {compatibility} zeigt die Modelle, auf denen schon Karten installiert wurden.",
        ],
        "compatibility": "Kompatibilität",
        "maps": "Karten",
        "mentions_heading": "Vorgestellt auf",
        "mentions_intro": "Danke an die Websites und Tester, die Terento ausprobiert, vorgestellt oder empfohlen haben.",
        "video": "Video",
    },
    "fr": {
        "title": "À propos de Terento : cartes Garmin gratuites et libres",
        "description": "Pourquoi un randonneur Garmin a créé Terento : un moyen gratuit et open source d’installer des cartes libres sur montres et compteurs Edge Garmin.",
        "skip": "Aller au contenu",
        "h1": "À propos de Terento",
        "role": "Créateur de Terento",
        "lead": "Une appli de cartes gratuite, faite par un randonneur Garmin.",
        "maker_heading": "Qui le fait",
        "story": [
            "J’utilise une Garmin fēnix. En vacances, j’aime préparer des randonnées pour découvrir un pays, surtout dans les montagnes d’Europe. Avant chaque voyage, je voulais des cartes sur ma montre. Sur un Mac, il fallait brancher la montre, chercher comment ajouter des cartes, les trouver, les télécharger puis les copier sur la montre.",
            "J’ai créé Terento pour rendre tout cela simple : connecter, installer, terminé.",
            "C’est gratuit et open source parce que j’aime ma Garmin et que je veux aider les personnes dans la même situation.",
        ],
        "contact": "Si vous avez des questions ou des remarques, vous pouvez me joindre ici :",
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
            "Un éditeur de cartes. Les cartes viennent de projets communautaires, cités sur la page {maps}.",
            "Une application de navigation. Vous naviguez sur votre Garmin, comme d’habitude.",
            "Une application pour Windows, téléphones ou tablettes.",
            "Un risque pour vos cartes Garmin d’origine. Terento n’y touche jamais.",
            "Une promesse que chaque Garmin fonctionne. La page {compatibility} liste les modèles sur lesquels des cartes ont déjà été installées.",
        ],
        "compatibility": "Compatibilité",
        "maps": "Cartes",
        "mentions_heading": "Présenté sur",
        "mentions_intro": "Merci aux sites et aux testeurs qui ont essayé, présenté ou recommandé Terento.",
        "video": "vidéo",
    },
    "pl": {
        "title": "O Terento: darmowe mapy open source na Garmina",
        "description": "Dlaczego turysta z Garminem stworzył Terento: darmowy, otwarty sposób na wgranie darmowych map na zegarki Garmin i liczniki rowerowe Edge. Bez konta.",
        "skip": "Przejdź do treści",
        "h1": "O Terento",
        "role": "Twórca Terento",
        "lead": "Darmowa aplikacja do map, stworzona przez turystę z Garminem.",
        "maker_heading": "Kto go tworzy",
        "story": [
            "Używam zegarka Garmin fēnix. Na wakacjach lubię planować wędrówki, żeby poznać dany kraj, zwłaszcza w górach Europy. Przed każdym wyjazdem chciałem mieć mapy na zegarku. Na Macu oznaczało to podłączenie zegarka, szukanie, jak dodać mapy, znalezienie ich, pobranie i skopiowanie na zegarek.",
            "Zrobiłem Terento, żeby to było proste: połącz, zainstaluj, gotowe.",
            "Jest darmowe i open source, bo lubię swojego Garmina i chcę pomóc osobom w tej samej sytuacji.",
        ],
        "contact": "Jeśli masz pytania lub uwagi, możesz się ze mną skontaktować tutaj:",
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
            "Twórcą map. Mapy pochodzą od projektów społecznościowych wymienionych na stronie {maps}.",
            "Aplikacją do nawigacji. Nawigujesz na Garminie, jak zawsze.",
            "Aplikacją na Windows, telefony ani tablety.",
            "Zagrożeniem dla oryginalnych map Garmina. Terento nigdy ich nie dotyka.",
            "Obietnicą, że każdy Garmin zadziała. Strona {compatibility} pokazuje modele, na które już wgrano mapy.",
        ],
        "compatibility": "Kompatybilność",
        "maps": "Mapy",
        "mentions_heading": "Pisali o Terento",
        "mentions_intro": "Dziękuję serwisom i recenzentom, którzy wypróbowali, opisali lub polecili Terento.",
        "video": "wideo",
    },
    "cs": {
        "title": "O Terento: bezplatné open-source mapy pro Garmin",
        "description": "Proč turista s Garminem vytvořil Terento: bezplatný a otevřený způsob, jak dostat mapy zdarma do hodinek Garmin a cyklopočítačů Edge. Bez účtu.",
        "skip": "Přejít k obsahu",
        "h1": "O Terento",
        "role": "Tvůrce Terento",
        "lead": "Bezplatná aplikace na mapy od jednoho turisty s Garminem.",
        "maker_heading": "Kdo ho dělá",
        "story": [
            "Používám hodinky Garmin fēnix. Na dovolené rád plánuji túry, abych poznal zemi, hlavně v evropských horách. Před každou cestou jsem chtěl mít mapy v hodinkách. Na Macu to znamenalo připojit hodinky, hledat, jak přidat mapy, najít je, stáhnout a zkopírovat do hodinek.",
            "Terento jsem vytvořil, aby to bylo jednoduché: připojit, nainstalovat, hotovo.",
            "Je zdarma a open source, protože mám svůj Garmin rád a chci pomoct lidem ve stejné situaci.",
        ],
        "contact": "Pokud máte otázky nebo zpětnou vazbu, můžete se mi ozvat tady:",
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
            "Tvůrce map. Mapy pocházejí od komunitních projektů uvedených na stránce {maps}.",
            "Navigační aplikace. Navigujete v Garminu jako obvykle.",
            "Aplikace pro Windows, telefony nebo tablety.",
            "Riziko pro vaše původní mapy Garmin. Terento se jich nikdy nedotkne.",
            "Slib, že bude fungovat každý Garmin. Stránka {compatibility} ukazuje modely, do kterých už někdo mapy nahrál.",
        ],
        "compatibility": "Kompatibilita",
        "maps": "Mapy",
        "mentions_heading": "Psali o Terento",
        "mentions_intro": "Děkuji webům a recenzentům, kteří Terento vyzkoušeli, představili nebo doporučili.",
        "video": "video",
    },
    "it": {
        "title": "Informazioni su Terento: mappe Garmin gratuite e libere",
        "description": "Perché un escursionista con Garmin ha creato Terento: un modo gratuito e open source per mettere mappe libere su orologi Garmin e ciclocomputer Edge.",
        "skip": "Vai al contenuto",
        "h1": "Informazioni su Terento",
        "role": "Creatore di Terento",
        "lead": "Un’app di mappe gratuita, fatta da un escursionista con Garmin.",
        "maker_heading": "Chi lo fa",
        "story": [
            "Uso un Garmin fēnix. In vacanza mi piace pianificare escursioni per conoscere un paese, soprattutto sulle montagne d’Europa. Prima di ogni viaggio volevo le mappe sull’orologio. Su un Mac significava collegare l’orologio, cercare come aggiungere le mappe, trovarle, scaricarle e copiarle sull’orologio.",
            "Ho creato Terento per rendere tutto semplice: collega, installa, fatto.",
            "È gratuito e open source perché mi piace il mio Garmin e voglio aiutare chi si trova nella stessa situazione.",
        ],
        "contact": "Se hai domande o feedback, puoi contattarmi qui:",
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
            "Un produttore di mappe. Le mappe vengono da progetti della community, citati nella pagina {maps}.",
            "Un’app di navigazione. Navighi sul tuo Garmin, come sempre.",
            "Un’app per Windows, telefoni o tablet.",
            "Un rischio per le mappe Garmin originali. Terento non le tocca mai.",
            "Una promessa che ogni Garmin funzioni. La pagina {compatibility} elenca i modelli su cui sono già state installate mappe.",
        ],
        "compatibility": "Compatibilità",
        "maps": "Mappe",
        "mentions_heading": "In evidenza su",
        "mentions_intro": "Grazie ai siti e ai recensori che hanno provato, presentato o consigliato Terento.",
        "video": "video",
    },
}


# "Featured on" mentions, shared by all six locales. Add a new one as a new entry
# at the end. Source labels and titles stay in English; "kind" is "article" or
# "video" (video adds the localized word after the source name).
MENTIONS = (
    {
        "source": "the5krunner (Indie Spotlight)",
        "title": "Terento Makes Installing Custom Maps on Garmin Watches Effortless for Mac Users",
        "url": "https://the5krunner.com/2026/09/22/garmin-mac-custom-maps-terento/",
        "kind": "article",
    },
    {
        "source": "HikingGuy",
        "title": "Garmin Fenix 9 Pro Review",
        "url": "https://hikingguy.com/gear/garmin-fenix-9-pro-review/",
        "kind": "article",
    },
    {
        "source": "HikingGuy",
        "title": "Garmin Fenix: 17 Tips I Wish I Knew Sooner",
        "url": "https://www.youtube.com/watch?v=szqwPHHWiTM",
        "kind": "video",
    },
)
MENTION_LANGUAGE = "en"


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


def mention_card(locale: str, copy: dict[str, object], mention: dict[str, str]) -> str:
    """One "Featured on" card: the source as a small label, the original title as the link."""
    assert mention["kind"] in ("article", "video"), f"unknown mention kind: {mention['kind']}"
    assert mention["url"].startswith("https://"), f"mention URL must be https: {mention['url']}"
    source = esc(mention["source"])
    if mention["kind"] == "video":
        source += f' ({esc(copy["video"])})'
    language = "" if locale == MENTION_LANGUAGE else f' lang="{MENTION_LANGUAGE}"'
    return (f'<li class="card about-mention"><p class="about-mention-source">{source}</p>'
            f'<a class="text-link" href="{esc(mention["url"])}"{language}>{esc(mention["title"])}</a></li>')


def maker_row(copy: dict[str, object]) -> str:
    return (f'<p class="about-maker"><span class="about-maker-name">Gediminas</span>'
            f'<span class="about-maker-role">{esc(copy["role"])}</span></p>')


def about_json_ld(locale: str) -> str:
    """The shared web-page graph plus the person who made Terento, linked as its founder.
    sameAs only lists the profiles linked on the page; no e-mail address."""
    graph = SCHEMA["page_graph"](locale, ABOUT_SLUG, "AboutPage")
    person_id = f"{BASE_URL}/{ABOUT_SLUG}#person"
    person = {"@type": "Person", "@id": person_id, "name": "Gediminas",
              "url": f"{BASE_URL}{localized_path(locale, ABOUT_SLUG)}", "sameAs": [LINKEDIN_URL, REDDIT_URL]}
    organization = graph["@graph"][0]
    organization["founder"] = {"@id": person_id}
    graph["@graph"].insert(1, person)
    page = next(node for node in graph["@graph"] if node.get("@type") == "AboutPage")
    page["mainEntity"] = {"@id": person_id}
    payload = json.dumps(graph, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return f'    <script type="application/ld+json">\n{textwrap.indent(payload, "      ")}\n    </script>'


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
        "maps": f'<a class="text-link" href="{localized_path(locale, "map-styles/")}" data-umami-event="maps-link-click" data-umami-event-location="about-main">{esc(copy["maps"])}</a>',
    }
    story = "\n".join(f'            <p>{esc(paragraph)}</p>' for paragraph in copy["story"])
    is_items = "\n".join(f'              <li>{with_links(item, links)}</li>' for item in copy["is_items"])
    isnt_items = "\n".join(f'              <li>{isnt_item(item, links)}</li>' for item in copy["isnt_items"])
    mentions = "\n".join(f'            {mention_card(locale, copy, mention)}' for mention in MENTIONS)
    social = f'''          <div class="about-socials">
            <p class="about-social-label">{esc(copy["contact"])}</p>
            <div class="about-social-links">
              <a class="about-social-link" href="{LINKEDIN_URL}" target="_blank" rel="noopener noreferrer" data-umami-event="social-link-click" data-umami-event-location="about-story" data-umami-event-channel="linkedin" data-umami-event-destination="linkedin.com"><img src="/assets/social/linkedin.svg" alt="" width="16" height="16"><span>{esc(copy["linkedin"])}</span></a>
              <a class="about-social-link" href="{REDDIT_URL}" target="_blank" rel="noopener noreferrer" data-umami-event="social-link-click" data-umami-event-location="about-story" data-umami-event-channel="reddit" data-umami-event-destination="reddit.com"><img src="/assets/social/reddit.svg" alt="" width="16" height="16"><span>{esc(copy["reddit"])}</span></a>
              <a class="about-social-link about-email-link" href="{EMAIL_HREF}" data-umami-event="support-link-click" data-umami-event-location="about-story" data-umami-event-channel="email"><img src="/assets/social/email.svg" alt="" width="16" height="16"><span>{esc(copy["email"])}</span></a>
            </div>
          </div>'''
    # Round 6 (owner): the donation block is a card in the right third, top-aligned with the story.
    donate = f'''        <div class="card about-donate">
          <p>{esc(copy["donate_text"])}</p>
          <a class="about-social-link about-social-link--donate" href="https://buymeacoffee.com/vooz2" target="_blank" rel="noopener noreferrer" data-umami-event="donate" data-umami-event-location="about-story" data-umami-event-channel="donate"><img src="/assets/social/buymeacoffee.svg" alt="" width="16" height="16"><span>{esc(copy["donate"])}</span></a>
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
{about_json_ld(locale)}


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
    <main id="main-content" class="about-v3">
      <section class="page-hero about-hero" aria-labelledby="about-title">
        <div class="shell"><div class="hero-copy">
          <h1 id="about-title">{esc(copy["h1"])}</h1>
          <p class="hero-lede">{esc(copy["lead"])}</p>
        </div></div>
      </section>
      <section class="block about-main" aria-labelledby="about-principle-title">
        <div class="shell">
          <div class="section-head"><h2 id="about-principle-title">{esc(copy["main_heading"])}</h2></div>
          <div class="grid about-list">
            <section class="card col-6 about-item about-item--group" aria-labelledby="about-is-title"><h3 id="about-is-title">{esc(copy["is_title"])}</h3><ul class="about-bullet-list">
{is_items}
            </ul></section>
            <section class="card col-6 about-item about-item--group" aria-labelledby="about-isnt-title"><h3 id="about-isnt-title">{esc(copy["isnt_title"])}</h3><ul class="about-bullet-list">
{isnt_items}
            </ul></section>
          </div>
        </div>
      </section>
      <section class="block about-story" aria-labelledby="about-maker-title">
        <div class="shell about-story-grid">
        <div class="about-story-main">
          <div class="about-story-copy">
            <h2 id="about-maker-title">{esc(copy["maker_heading"])}</h2>
            {maker_row(copy)}
{story}
          </div>
{social}
        </div>
{donate}
        </div>
      </section>
      <section class="block about-v2-mentions" aria-labelledby="about-mentions-title">
        <div class="shell">
          <div class="section-head"><h2 id="about-mentions-title">{esc(copy["mentions_heading"])}</h2><p>{esc(copy["mentions_intro"])}</p></div>
          <ul class="grid about-mentions">
{mentions}
          </ul>
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
