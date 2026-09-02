#!/usr/bin/env python3
"""Apply the shared Home information-architecture contract to each locale."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCALES = ("en", "de", "fr", "pl", "cs", "it")
FAQ_KEEP = (0, 1, 4, 5, 6)
PROVIDER_SCRIPT_VERSION = "20260902-provider-catalog"
HOME_COPY = {
    "en": {
        "scope_href": "/compatibility/",
        "problem": "Installing third-party maps should not require old software or manual file transfers.",
        "scope": "Terento is built for Garmin smartwatches with map support. Compatibility is confirmed for each model and variant using real installation results.",
        "compatibility_answer": "See the <a href=\"/compatibility/\">Compatibility page</a> for Garmin models and variants confirmed by real installations.",
        "install_step": "Choose the map you need.",
        "install_showcase": "Browse supported maps by region and review the storage impact before installing.",
        "basecamp_answer": "Yes. Terento takes you from choosing a map to installing it on your watch. You can also add a compatible map file from your Mac. Apple Silicon is required. <a href=\"/guides/install-garmin-maps-mac/\">Read the installation guide.</a>",
        "safety_answer": "Yes. Garmin and system maps remain protected. Terento changes only supported third-party maps after you confirm the action.",
        "provider_answer": "Terento uses the supported providers shown above. Maps are downloaded directly from the original provider.",
        "failure_answer": "Open a GitHub issue or email the diagnostic log. It contains what we need to investigate the problem.",
        "provider_eyebrow": "Available today",
        "provider_title": "Choose a map and get moving.",
        "provider_copy": "Terento connects you directly to supported map providers. This list stays current as support grows.",
        "provider_list_label": "Supported map providers",
    },
    "de": {
        "scope_href": "/de/compatibility/",
        "problem": "Die Installation von Drittanbieter-Karten sollte keine alten Programme oder manuelle Dateiübertragung erfordern.",
        "scope": "Terento ist für Garmin-Smartwatches mit Kartenunterstützung entwickelt. Die Kompatibilität wird für jedes Modell und jede Variante anhand echter Installationsergebnisse bestätigt.",
        "compatibility_answer": "Auf der <a href=\"/de/compatibility/\">Kompatibilitätsseite</a> findest du Garmin-Modelle und Varianten, die durch echte Installationen bestätigt wurden.",
        "install_step": "Wähle die Karte, die du brauchst.",
        "install_showcase": "Durchsuche unterstützte Karten nach Region und prüfe den Speicherbedarf vor der Installation.",
        "basecamp_answer": "Ja. Terento führt dich von der Kartenauswahl bis zur Installation auf der Uhr. Du kannst auch eine kompatible Kartendatei von deinem Mac hinzufügen. Apple Silicon ist erforderlich. <a href=\"/de/guides/install-garmin-maps-mac/\">Lies die Installationsanleitung.</a>",
        "safety_answer": "Ja. Garmin- und Systemkarten bleiben geschützt. Terento ändert nur unterstützte Drittanbieter-Karten, nachdem du die Aktion bestätigt hast.",
        "provider_answer": "Terento nutzt die oben genannten unterstützten Kartenanbieter. Karten werden direkt vom ursprünglichen Anbieter geladen.",
        "failure_answer": "Öffne ein GitHub-Issue oder sende das Diagnoseprotokoll per E-Mail. Es enthält die Informationen, die wir zur Untersuchung benötigen.",
        "provider_eyebrow": "Heute verfügbar",
        "provider_title": "Wähle eine Karte und leg los.",
        "provider_copy": "Terento verbindet dich direkt mit unterstützten Kartenanbietern. Die Liste bleibt aktuell, wenn weitere Anbieter dazukommen.",
        "provider_list_label": "Unterstützte Kartenanbieter",
    },
    "fr": {
        "scope_href": "/fr/compatibility/",
        "problem": "Installer des cartes tierces ne devrait pas nécessiter d’anciens logiciels ni de transferts manuels.",
        "scope": "Terento est conçu pour les montres Garmin compatibles avec les cartes. La compatibilité est confirmée pour chaque modèle et chaque variante à partir de résultats d’installation réels.",
        "compatibility_answer": "Consultez la <a href=\"/fr/compatibility/\">page Compatibilité</a> pour voir les modèles et variantes Garmin confirmés par des installations réelles.",
        "install_step": "Choisissez la carte dont vous avez besoin.",
        "install_showcase": "Parcourez les cartes prises en charge par région et vérifiez l’espace nécessaire avant l’installation.",
        "basecamp_answer": "Oui. Terento vous guide du choix de la carte jusqu’à son installation sur la montre. Vous pouvez aussi ajouter un fichier cartographique compatible depuis votre Mac. Apple Silicon est requis. <a href=\"/fr/guides/install-garmin-maps-mac/\">Lisez le guide d’installation.</a>",
        "safety_answer": "Oui. Les cartes Garmin et système restent protégées. Terento ne modifie que les cartes tierces prises en charge après votre confirmation.",
        "provider_answer": "Terento utilise les fournisseurs de cartes pris en charge présentés ci-dessus. Les cartes sont téléchargées directement depuis leur source d’origine.",
        "failure_answer": "Ouvrez une issue GitHub ou envoyez le journal de diagnostic par e-mail. Il contient les informations nécessaires à l’analyse.",
        "provider_eyebrow": "Disponible aujourd’hui",
        "provider_title": "Choisissez une carte et partez.",
        "provider_copy": "Terento vous connecte directement aux fournisseurs de cartes pris en charge. La liste reste à jour à mesure que la prise en charge progresse.",
        "provider_list_label": "Fournisseurs de cartes pris en charge",
    },
    "pl": {
        "scope_href": "/pl/compatibility/",
        "problem": "Instalowanie map innych firm nie powinno wymagać starych programów ani ręcznego przesyłania plików.",
        "scope": "Terento jest przeznaczone dla zegarków Garmin z obsługą map. Kompatybilność każdego modelu i wariantu jest potwierdzana na podstawie rzeczywistych instalacji.",
        "compatibility_answer": "Na <a href=\"/pl/compatibility/\">stronie kompatybilności</a> znajdziesz modele i warianty Garmin potwierdzone rzeczywistymi instalacjami.",
        "install_step": "Wybierz mapę, której potrzebujesz.",
        "install_showcase": "Przeglądaj obsługiwane mapy według regionu i sprawdź potrzebne miejsce przed instalacją.",
        "basecamp_answer": "Tak. Terento prowadzi od wyboru mapy do instalacji na zegarku. Możesz też dodać zgodny plik mapy z Maca. Wymagany jest Apple Silicon. <a href=\"/pl/guides/install-garmin-maps-mac/\">Przeczytaj instrukcję instalacji.</a>",
        "safety_answer": "Tak. Mapy Garmin i systemowe pozostają chronione. Terento zmienia tylko obsługiwane mapy innych firm po potwierdzeniu działania.",
        "provider_answer": "Terento korzysta z obsługiwanych dostawców pokazanych powyżej. Mapy są pobierane bezpośrednio z oryginalnego źródła.",
        "failure_answer": "Otwórz zgłoszenie na GitHubie lub wyślij log diagnostyczny e-mailem. Zawiera informacje potrzebne do zbadania problemu.",
        "provider_eyebrow": "Dostępne dziś",
        "provider_title": "Wybierz mapę i ruszaj.",
        "provider_copy": "Terento łączy Cię bezpośrednio z obsługiwanymi dostawcami map. Lista pozostaje aktualna, gdy rośnie zakres obsługi.",
        "provider_list_label": "Obsługiwani dostawcy map",
    },
    "cs": {
        "scope_href": "/cs/compatibility/",
        "problem": "Instalace map třetích stran by neměla vyžadovat staré programy ani ruční přenos souborů.",
        "scope": "Terento je určeno pro hodinky Garmin s podporou map. Kompatibilita každého modelu a varianty se potvrzuje pomocí skutečných výsledků instalace.",
        "compatibility_answer": "Na stránce <a href=\"/cs/compatibility/\">Kompatibilita</a> najdete modely a varianty Garmin potvrzené skutečnými instalacemi.",
        "install_step": "Vyberte mapu, kterou potřebujete.",
        "install_showcase": "Procházejte podporované mapy podle oblasti a před instalací zkontrolujte potřebné místo.",
        "basecamp_answer": "Ano. Terento vás provede od výběru mapy až po instalaci do hodinek. Z Macu můžete také přidat kompatibilní mapový soubor. Je vyžadován Apple Silicon. <a href=\"/cs/guides/install-garmin-maps-mac/\">Přečtěte si instalační příručku.</a>",
        "safety_answer": "Ano. Garmin a systémové mapy zůstávají chráněné. Terento mění pouze podporované mapy třetích stran po potvrzení akce.",
        "provider_answer": "Terento využívá podporované poskytovatele uvedené výše. Mapy se stahují přímo z původního zdroje.",
        "failure_answer": "Otevřete issue na GitHubu nebo pošlete diagnostický log e-mailem. Obsahuje informace potřebné k prošetření problému.",
        "provider_eyebrow": "Dostupné dnes",
        "provider_title": "Vyberte mapu a vyrazte.",
        "provider_copy": "Terento vás propojí přímo s podporovanými poskytovateli map. Seznam zůstává aktuální, jak se podpora rozšiřuje.",
        "provider_list_label": "Podporovaní poskytovatelé map",
    },
    "it": {
        "scope_href": "/it/compatibility/",
        "problem": "Installare mappe di terze parti non dovrebbe richiedere vecchi programmi o trasferimenti manuali.",
        "scope": "Terento è progettato per gli smartwatch Garmin con supporto alle mappe. La compatibilità di ogni modello e variante viene confermata con risultati di installazione reali.",
        "compatibility_answer": "Consulta la pagina <a href=\"/it/compatibility/\">Compatibilità</a> per i modelli e le varianti Garmin confermati da installazioni reali.",
        "install_step": "Scegli la mappa che ti serve.",
        "install_showcase": "Sfoglia le mappe supportate per regione e controlla lo spazio necessario prima dell’installazione.",
        "basecamp_answer": "Sì. Terento ti guida dalla scelta della mappa all’installazione sullo smartwatch. Puoi anche aggiungere dal Mac un file cartografico compatibile. È richiesto Apple Silicon. <a href=\"/it/guides/install-garmin-maps-mac/\">Leggi la guida all’installazione.</a>",
        "safety_answer": "Sì. Le mappe Garmin e di sistema restano protette. Terento modifica solo le mappe di terze parti supportate dopo la tua conferma.",
        "provider_answer": "Terento usa i provider supportati mostrati sopra. Le mappe vengono scaricate direttamente dalla fonte originale.",
        "failure_answer": "Apri una issue su GitHub oppure invia il log diagnostico via e-mail. Contiene le informazioni necessarie per analizzare il problema.",
        "provider_eyebrow": "Disponibili oggi",
        "provider_title": "Scegli una mappa e parti.",
        "provider_copy": "Terento ti collega direttamente ai provider di mappe supportati. L’elenco resta aggiornato man mano che il supporto cresce.",
        "provider_list_label": "Provider di mappe supportati",
    },
}


def home_path(locale: str) -> Path:
    return ROOT / "site" / ("index.html" if locale == "en" else f"{locale}/index.html")


def reduce_visible_faq(source: str, path: Path) -> str:
    section_match = re.search(
        r'(<section class="faq section" id="faq"[\s\S]*?<div class="faq-list">)([\s\S]*?)(</div>\s*</div>\s*</section>)',
        source,
    )
    if not section_match:
        raise ValueError(f"{path}: Home FAQ section not found")
    body = section_match.group(2)
    entries = list(re.finditer(r'<details>[\s\S]*?</details>', body))
    if len(entries) not in (5, 10):
        raise ValueError(f"{path}: expected five or ten FAQ entries, found {len(entries)}")
    cleaned_prefix = body[: entries[0].start()].rstrip()
    indent_match = re.search(r"\n([ \t]+)(?:\n[ \t]*)?$", body[: entries[0].start()])
    entry_indent = indent_match.group(1) if indent_match else "            "
    indexes = FAQ_KEEP if len(entries) == 10 else range(len(entries))
    kept = "\n".join(entry_indent + entries[index].group(0).strip() for index in indexes)
    body = cleaned_prefix + "\n" + kept + "\n" + entry_indent
    source = source[: section_match.start(2)] + body + source[section_match.end(2) :]
    return source


def reduce_faq_schema(source: str, path: Path, copy: dict[str, str], description: str) -> str:
    pattern = re.compile(r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)([\s\S]*?)(</script>)', re.IGNORECASE)
    match = pattern.search(source)
    if not match:
        raise ValueError(f"{path}: JSON-LD block not found")
    data = json.loads(match.group(2).strip())
    graph = data.get("@graph", [])
    for schema_type in ("SoftwareApplication", "WebSite"):
        entity = next((item for item in graph if item.get("@type") == schema_type), None)
        if entity is None:
            raise ValueError(f"{path}: {schema_type} schema entry not found")
        entity["description"] = description
    faq = next((item for item in graph if item.get("@type") == "FAQPage"), None)
    if faq is None or len(faq.get("mainEntity", [])) not in (5, 10):
        raise ValueError(f"{path}: expected five or ten FAQ schema entries")
    if len(faq["mainEntity"]) == 10:
        faq["mainEntity"] = [faq["mainEntity"][index] for index in FAQ_KEEP]
    for index, key in enumerate(("compatibility_answer", "basecamp_answer", "safety_answer", "provider_answer", "failure_answer")):
        faq["mainEntity"][index]["acceptedAnswer"]["text"] = re.sub(r"<[^>]+>", "", copy[key])
    serialized = json.dumps(data, ensure_ascii=False, indent=2)
    indented = "\n".join("      " + line for line in serialized.splitlines())
    replacement = "\n" + indented + "\n    "
    source = source[: match.start(2)] + replacement + source[match.end(2) :]
    return source


def normalize_home(source: str, path: Path, locale: str) -> str:
    copy = HOME_COPY[locale]
    metadata = json.loads((ROOT / "site" / "metadata.json").read_text(encoding="utf-8"))
    relative = str(path.relative_to(ROOT))
    description = next(page["description"] for page in metadata["pages"] if page["file"] == relative)
    source = source.replace('class="experience section" id="about"', 'class="experience section" id="how-it-works"')
    source = source.replace("              <h3>Install</h3>\n              <h3>Install</h3>", "              <h3>Install</h3>")
    source = reduce_visible_faq(source, path)
    faq_match = re.search(r'(<section class="faq section" id="faq"[\s\S]*?<div class="faq-list">)([\s\S]*?)(</div>\s*</div>\s*</section>)', source)
    if not faq_match:
        raise ValueError(f"{path}: Home FAQ section not found after reduction")
    faq_body = faq_match.group(2)
    entries = list(re.finditer(r'<details>[\s\S]*?</details>', faq_body))
    answer_keys = ("compatibility_answer", "basecamp_answer", "safety_answer", "provider_answer", "failure_answer")
    rewritten_entries = []
    for entry, key in zip(entries, answer_keys):
        rewritten_entries.append(re.sub(r'<p>[\s\S]*?</p>', f'<p>{copy[key]}</p>', entry.group(0), count=1))
    for entry, rewritten in reversed(list(zip(entries, rewritten_entries))):
        faq_body = faq_body[: entry.start()] + rewritten + faq_body[entry.end() :]
    source = source[: faq_match.start(2)] + faq_body + source[faq_match.end(2) :]
    source = re.sub(
        r'(<p class="scope-copy">)[\s\S]*?(</p>)',
        rf'\g<1>{copy["scope"]}\g<2>',
        source,
        count=1,
    )
    source = re.sub(
        r'(<div class="problem-statement">\s*<p>)[\s\S]*?(</p>)',
        rf'\g<1>{copy["problem"]}\g<2>',
        source,
        count=1,
    )
    source = re.sub(
        r'(<section class="hero"[\s\S]*?)<a class="text-link" (href="[^"]*download/">[\s\S]*?</a>)',
        r'\1<a class="download-action hero-download-action" \2',
        source,
        count=1,
    )
    source = re.sub(
        r'(<section class="experience section"[\s\S]*?<li class="step">[\s\S]*?<li class="step">[\s\S]*?<p>)[\s\S]*?(</p>)',
        rf'\g<1>{copy["install_step"]}\g<2>',
        source,
        count=1,
    )
    source = re.sub(
        r'(<h2 id="install-maps-title">[\s\S]*?</h2>\s*<p>)[\s\S]*?(</p>)',
        rf'\g<1>{copy["install_showcase"]}\g<2>',
        source,
        count=1,
    )
    source = re.sub(
        r'(<a class="text-link scope-link" href=")[^"]+("[^>]*>)',
        rf'\g<1>{copy["scope_href"]}\g<2>',
        source,
        count=1,
    )
    source, removed = re.subn(
        r'\s*<div class="scope-list"[^>]*>(?:\s*<div class="scope-item">[\s\S]*?</div>){3,4}\s*</div>',
        "",
        source,
        count=1,
    )
    if removed != 1 and 'class="scope-list"' in source:
        raise ValueError(f"{path}: failed to remove Home scope cards")
    source = re.sub(
        r'\s*<section class="provider-section section" id="providers"[\s\S]*?</section>',
        "",
        source,
    )
    provider_section = f'''<section class="provider-section section" id="providers" aria-labelledby="providers-title">
        <div class="shell provider-grid">
          <div class="section-heading"><p class="eyebrow">{copy["provider_eyebrow"]}</p><h2 id="providers-title">{copy["provider_title"]}</h2></div>
          <div class="provider-copy"><p>{copy["provider_copy"]}</p><ul class="provider-list" data-provider-list aria-label="{copy["provider_list_label"]}"><li>Freizeitkarte</li><li>OpenTopoMap</li></ul></div>
        </div>
      </section>'''
    marker = '\n      <section class="faq section"'
    if marker not in source:
        raise ValueError(f"{path}: Home FAQ insertion point not found")
    source = source.replace(marker, f"\n      {provider_section}{marker}", 1)
    if 'src="/provider-list.js?' not in source:
        source = re.sub(
            r'(<script defer src="/privacy-consent\.js\?v=[^"\s]+"></script>)',
            rf'\1\n    <script defer src="/provider-list.js?v={PROVIDER_SCRIPT_VERSION}"></script>',
            source,
            count=1,
        )
    return reduce_faq_schema(source, path, copy, description)


def main() -> None:
    for locale in LOCALES:
        path = home_path(locale)
        source = path.read_text(encoding="utf-8")
        path.write_text(normalize_home(source, path, locale), encoding="utf-8")
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
