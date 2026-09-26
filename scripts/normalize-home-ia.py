#!/usr/bin/env python3
"""Apply the shared Home information-architecture contract to each locale."""

from __future__ import annotations

import html
import json
import re
from string import Template
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCALES = ("en", "de", "fr", "pl", "cs", "it")
PROVIDER_SCRIPT_VERSION = "20260912-bbbike-types-v1"
FEATURE_SCRIPT_VERSION = "20260904-home-workflow-tabs"
EMAIL_URL = "mailto:hello@terento.app?subject=Terento%20installation%20issue"
EMAIL_URL_HTML = EMAIL_URL.replace("@", "&#64;")
HOME_COPY = json.loads((ROOT / "scripts/templates/home-copy.json").read_text())

PROVIDER_CARD_COPY = {
    "en": {
        "freizeitkarte": {
            "name": "Freizeitkarte",
            "count_template": "{count} map packages",
            "summary": "For walks, bike rides, and days out.",
            "benefits": [
                "Routes for walking and cycling",
                "Contour lines included",
                "Places to visit, bus stops, and train stations"
            ]
        },
        "opentopomap": {
            "name": "OpenTopoMap",
            "count_template": "{count} map packages",
            "summary": "For hikes where terrain matters.",
            "benefits": [
                "Topographic detail for roads and paths",
                "Elevation data and shaded relief",
                "Optional contour lines for extra terrain detail"
            ]
        },
        "maprando": {
            "name": "MapRando",
            "count_template": "{count} map packages",
            "summary": "For exploring smaller trails on foot.",
            "benefits": [
                "Small paths beyond the main trails",
                "Map styling designed for hiking",
                "New editions bring in OpenStreetMap changes"
            ]
        },
        "contours": {
            "badge": "Optional add-on for OpenTopoMap",
            "name": "Contour lines",
            "description": "Add lines that show elevation and help you read slopes. Choose this add-on when installing an OpenTopoMap region in Terento.",
            "count_template": "Available for {count} map packages · Uses additional storage."
        },
        "previous": "Previous map provider",
        "next": "Next map provider"
    },
    "de": {
        "freizeitkarte": {
            "name": "Freizeitkarte",
            "count_template": "{count} Kartenpakete",
            "summary": "Für Spaziergänge, Radtouren und Ausflüge.",
            "benefits": [
                "Routen für Fußgänger und Radfahrer",
                "Höhenlinien bereits enthalten",
                "Ausflugsziele, Bushaltestellen und Bahnhöfe"
            ]
        },
        "opentopomap": {
            "name": "OpenTopoMap",
            "count_template": "{count} Kartenpakete",
            "summary": "Für Wanderungen, bei denen das Gelände zählt.",
            "benefits": [
                "Topografische Details für Straßen und Wege",
                "Höhendaten und Geländeschummerung",
                "Optionale Höhenlinien für zusätzliche Geländedetails"
            ]
        },
        "maprando": {
            "name": "MapRando",
            "count_template": "{count} Kartenpakete",
            "summary": "Zum Erkunden kleinerer Wege zu Fuß.",
            "benefits": [
                "Kleine Pfade abseits der Hauptwege",
                "Für Wanderungen gestaltete Karte",
                "Neue Ausgaben übernehmen Änderungen aus OpenStreetMap"
            ]
        },
        "contours": {
            "badge": "Optionales Extra für OpenTopoMap",
            "name": "Höhenlinien",
            "description": "Ergänze Höhenlinien, um Höhen und Hänge besser zu erkennen. Wähle dieses Extra bei der Installation einer OpenTopoMap-Region in Terento.",
            "count_template": "Für {count} Kartenpakete verfügbar · Benötigt zusätzlichen Speicherplatz."
        },
        "previous": "Vorheriger Kartenanbieter",
        "next": "Nächster Kartenanbieter"
    },
    "fr": {
        "freizeitkarte": {
            "name": "Freizeitkarte",
            "count_template": "{count} paquets de cartes",
            "summary": "Pour les balades, le vélo et les sorties.",
            "benefits": [
                "Itinéraires à pied et à vélo",
                "Courbes de niveau incluses",
                "Lieux à visiter, arrêts de bus et gares"
            ]
        },
        "opentopomap": {
            "name": "OpenTopoMap",
            "count_template": "{count} paquets de cartes",
            "summary": "Pour les randonnées où le relief compte.",
            "benefits": [
                "Détails topographiques des routes et chemins",
                "Données d’altitude et relief ombré",
                "Courbes de niveau en option pour détailler le relief"
            ]
        },
        "maprando": {
            "name": "MapRando",
            "count_template": "{count} paquets de cartes",
            "summary": "Pour explorer les petits sentiers à pied.",
            "benefits": [
                "Petits chemins au-delà des sentiers principaux",
                "Un style de carte conçu pour la randonnée",
                "Les nouvelles éditions intègrent les modifications OpenStreetMap"
            ]
        },
        "contours": {
            "badge": "Complément facultatif pour OpenTopoMap",
            "name": "Courbes de niveau",
            "description": "Ajoutez des courbes d’altitude pour mieux lire les pentes. Choisissez ce complément lors de l’installation d’une région OpenTopoMap dans Terento.",
            "count_template": "Disponible pour {count} cartes · Utilise de l’espace supplémentaire."
        },
        "previous": "Fournisseur de cartes précédent",
        "next": "Fournisseur de cartes suivant"
    },
    "pl": {
        "freizeitkarte": {
            "name": "Freizeitkarte",
            "count_template": "Pakiety map: {count}",
            "summary": "Na spacery, przejażdżki rowerowe i wycieczki.",
            "benefits": [
                "Trasy piesze i rowerowe",
                "Poziomice w zestawie",
                "Miejsca warte odwiedzenia, przystanki i stacje kolejowe"
            ]
        },
        "opentopomap": {
            "name": "OpenTopoMap",
            "count_template": "Pakiety map: {count}",
            "summary": "Na wędrówki, podczas których liczy się rzeźba terenu.",
            "benefits": [
                "Topograficzne szczegóły dróg i ścieżek",
                "Dane wysokościowe i cieniowanie terenu",
                "Opcjonalne poziomice ze szczegółami rzeźby terenu"
            ]
        },
        "maprando": {
            "name": "MapRando",
            "count_template": "Pakiety map: {count}",
            "summary": "Do odkrywania mniejszych szlaków pieszo.",
            "benefits": [
                "Małe ścieżki poza głównymi szlakami",
                "Styl mapy opracowany z myślą o wędrówkach",
                "Nowe wydania uwzględniają zmiany w OpenStreetMap"
            ]
        },
        "contours": {
            "badge": "Opcjonalny dodatek do OpenTopoMap",
            "name": "Poziomice",
            "description": "Dodaj linie wysokości, które pomagają odczytać nachylenie terenu. Wybierz ten dodatek podczas instalacji regionu OpenTopoMap w Terento.",
            "count_template": "Dostępne dla {count} pakietów map · Zajmują dodatkowe miejsce."
        },
        "previous": "Poprzedni dostawca map",
        "next": "Następny dostawca map"
    },
    "cs": {
        "freizeitkarte": {
            "name": "Freizeitkarte",
            "count_template": "Mapové balíčky: {count}",
            "summary": "Na procházky, vyjížďky na kole a výlety.",
            "benefits": [
                "Trasy pro pěší i cyklisty",
                "Vrstevnice jsou součástí mapy",
                "Místa k návštěvě, autobusové zastávky a nádraží"
            ]
        },
        "opentopomap": {
            "name": "OpenTopoMap",
            "count_template": "Mapové balíčky: {count}",
            "summary": "Na túry, při kterých záleží na terénu.",
            "benefits": [
                "Topografické detaily silnic a cest",
                "Výšková data a stínovaný reliéf",
                "Volitelné vrstevnice pro podrobnější zobrazení terénu"
            ]
        },
        "maprando": {
            "name": "MapRando",
            "count_template": "Mapové balíčky: {count}",
            "summary": "Pro pěší objevování menších stezek.",
            "benefits": [
                "Drobné pěšiny mimo hlavní stezky",
                "Mapový styl navržený pro pěší turistiku",
                "Nová vydání zahrnují změny z OpenStreetMap"
            ]
        },
        "contours": {
            "badge": "Volitelný doplněk pro OpenTopoMap",
            "name": "Vrstevnice",
            "description": "Přidejte výškové čáry, které pomáhají rozpoznat svahy. Tento doplněk vyberte při instalaci regionu OpenTopoMap v Terento.",
            "count_template": "Dostupné pro {count} mapových balíčků · Zabírají další místo."
        },
        "previous": "Předchozí poskytovatel map",
        "next": "Další poskytovatel map"
    },
    "it": {
        "freizeitkarte": {
            "name": "Freizeitkarte",
            "count_template": "{count} pacchetti di mappe",
            "summary": "Per passeggiate, giri in bici e gite.",
            "benefits": [
                "Percorsi a piedi e in bicicletta",
                "Curve di livello incluse",
                "Luoghi da visitare, fermate degli autobus e stazioni"
            ]
        },
        "opentopomap": {
            "name": "OpenTopoMap",
            "count_template": "{count} pacchetti di mappe",
            "summary": "Per escursioni in cui il terreno conta.",
            "benefits": [
                "Dettagli topografici di strade e sentieri",
                "Dati altimetrici e rilievo ombreggiato",
                "Curve di livello opzionali per maggiori dettagli del terreno"
            ]
        },
        "maprando": {
            "name": "MapRando",
            "count_template": "{count} pacchetti di mappe",
            "summary": "Per esplorare i sentieri minori a piedi.",
            "benefits": [
                "Piccoli sentieri oltre i percorsi principali",
                "Stile cartografico pensato per l’escursionismo",
                "Le nuove edizioni integrano le modifiche di OpenStreetMap"
            ]
        },
        "contours": {
            "badge": "Componente aggiuntivo opzionale per OpenTopoMap",
            "name": "Curve di livello",
            "description": "Aggiungi linee altimetriche per leggere meglio le pendenze. Scegli questo componente durante l’installazione di una regione OpenTopoMap in Terento.",
            "count_template": "Disponibile per {count} pacchetti di mappe · Occupa spazio aggiuntivo."
        },
        "previous": "Provider di mappe precedente",
        "next": "Provider di mappe successivo"
    }
}

def home_path(locale: str) -> Path:
    return ROOT / "site" / ("index.html" if locale == "en" else f"{locale}/index.html")


def reduce_faq_schema(source: str, path: Path, copy: dict[str, str], description: str) -> str:
    pattern = re.compile(r'(<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>)([\s\S]*?)(</script>)', re.IGNORECASE)
    match = pattern.search(source)
    if not match:
        raise ValueError(f"{path}: JSON-LD block not found")
    data = json.loads(match.group(2).strip())
    graph = data.get("@graph", [])
    application = next((item for item in graph if item.get("@type") == "SoftwareApplication"), None)
    website = next((item for item in graph if item.get("@type") == "WebSite"), None)
    if application is None:
        raise ValueError(f"{path}: SoftwareApplication schema entry not found")
    if website is None:
        raise ValueError(f"{path}: WebSite schema entry not found")
    application["description"] = description
    website["description"] = description
    release = json.loads((ROOT / "site" / "updates" / "macos-arm64.json").read_text(encoding="utf-8"))
    application["softwareVersion"] = release["releaseLabel"]
    application["downloadUrl"] = release["downloadURL"]
    application["releaseNotes"] = release["releaseNotesURL"]
    faq = next((item for item in graph if item.get("@type") == "FAQPage"), None)
    if faq is None or len(faq.get("mainEntity", [])) != 5:
        raise ValueError(f"{path}: expected five FAQ schema entries")
    answer_keys = ("compatibility_answer", "basecamp_answer", "safety_answer", "update_answer", "failure_answer")
    for index, key in enumerate(answer_keys):
        faq["mainEntity"][index]["name"] = copy["faq_questions"][index]
        faq["mainEntity"][index]["acceptedAnswer"]["text"] = re.sub(r"<[^>]+>", "", copy[key])
    serialized = json.dumps(data, ensure_ascii=False, indent=2)
    indented = "\n".join("      " + line for line in serialized.splitlines())
    replacement = "\n" + indented + "\n    "
    source = source[: match.start(2)] + replacement + source[match.end(2) :]
    return source


BBBIKE_CARD_COPY = {
    "en": [
        "For exploring streets, cycle paths, and their surroundings.",
        "For walks and bike rides when storage matters.",
        [
            "Distinct styling for roads, cycle paths, and footpaths",
            "Buildings, parks, and woodland for context",
            "Regional maps updated weekly"
        ],
        [
            "Compact maps that save device space",
            "Smaller roads and paths included",
            "Supports navigation along mapped roads and paths"
        ]
    ],
    "de": [
        "Zum Erkunden von Straßen, Radwegen und ihrer Umgebung.",
        "Für Wanderungen und Radtouren bei wenig Speicherplatz.",
        [
            "Unterschiedliche Darstellung von Straßen, Rad- und Fußwegen",
            "Gebäude, Parks und Wälder zur Orientierung",
            "Wöchentlich aktualisierte Regionalkarten"
        ],
        [
            "Kompakte Karten sparen Gerätespeicher",
            "Auch kleinere Straßen und Wege enthalten",
            "Navigation entlang kartierter Straßen und Wege"
        ]
    ],
    "fr": [
        "Pour explorer les rues, les pistes cyclables et leurs environs.",
        "Pour marcher et pédaler en économisant le stockage.",
        [
            "Styles distincts pour routes, pistes cyclables et chemins piétons",
            "Bâtiments, parcs et forêts pour se repérer",
            "Cartes régionales actualisées chaque semaine"
        ],
        [
            "Des cartes compactes qui économisent de l’espace",
            "Petites routes et chemins inclus",
            "Navigation le long des routes et chemins cartographiés"
        ]
    ],
    "pl": [
        "Do odkrywania ulic, dróg rowerowych i ich okolic.",
        "Na piesze i rowerowe wycieczki, gdy liczy się miejsce.",
        [
            "Odrębne oznaczenia dróg, dróg rowerowych i ścieżek pieszych",
            "Budynki, parki i lasy ułatwiające orientację",
            "Mapy regionów aktualizowane co tydzień"
        ],
        [
            "Kompaktowe mapy oszczędzające pamięć urządzenia",
            "Uwzględnione mniejsze drogi i ścieżki",
            "Nawigacja po drogach i ścieżkach zaznaczonych na mapie"
        ]
    ],
    "cs": [
        "Pro objevování ulic, cyklostezek a jejich okolí.",
        "Na pěší a cyklistické výlety, když záleží na místě.",
        [
            "Odlišné zobrazení silnic, cyklostezek a pěšin",
            "Budovy, parky a lesy pro orientaci",
            "Regionální mapy aktualizované každý týden"
        ],
        [
            "Kompaktní mapy šetří úložiště zařízení",
            "Zahrnuty i menší silnice a cesty",
            "Navigace po zmapovaných silnicích a cestách"
        ]
    ],
    "it": [
        "Per esplorare strade, piste ciclabili e dintorni.",
        "Per camminare e pedalare quando lo spazio conta.",
        [
            "Stili distinti per strade, piste ciclabili e percorsi pedonali",
            "Edifici, parchi e boschi per orientarsi",
            "Mappe regionali aggiornate ogni settimana"
        ],
        [
            "Mappe compatte che risparmiano spazio sul dispositivo",
            "Incluse anche strade e sentieri minori",
            "Navigazione lungo strade e sentieri presenti sulla mappa"
        ]
    ]
}

for _locale, (_base_summary, _trail_summary, _base_benefits, _trail_benefits) in BBBIKE_CARD_COPY.items():
    for _key, _name, _summary, _benefits in (
        ("bbbike", "BBBike", _base_summary, _base_benefits),
        ("bbbike-ontrail", "BBBike (Ontrail)", _trail_summary, _trail_benefits),
    ):
        PROVIDER_CARD_COPY[_locale][_key] = {
            "name": _name,
            "count_template": PROVIDER_CARD_COPY[_locale]["maprando"]["count_template"],
            "summary": _summary,
            "benefits": _benefits,
        }

MAPRANDO_LANGUAGE_NOTES = {'en': 'Some map labels are in French.', 'de': 'Einige Kartenbeschriftungen sind auf Französisch.', 'fr': 'Certains libellés de la carte sont en français.', 'pl': 'Niektóre opisy na mapie są po francusku.', 'cs': 'Některé popisky mapy jsou ve francouzštině.', 'it': 'Alcune etichette della mappa sono in francese.'}

def provider_cards_markup(locale: str, copy: dict[str, str]) -> str:
    cards = []
    for provider_id in ("freizeitkarte", "opentopomap", "maprando", "bbbike", "bbbike-ontrail"):
        provider = PROVIDER_CARD_COPY[locale][provider_id]
        fallback_count = {"freizeitkarte": "63", "opentopomap": "177"}.get(provider_id)
        count_markup = provider["count_template"].replace("{count}", fallback_count) if fallback_count else ""
        count_hidden = "" if fallback_count else " hidden"
        benefits = "".join(f"<li>{html.escape(benefit)}</li>" for benefit in provider["benefits"])
        addon = ""
        if provider_id == "maprando":
            addon = f'<p class="provider-language-note"><span aria-hidden="true">ⓘ</span><span>{html.escape(MAPRANDO_LANGUAGE_NOTES[locale])}</span></p>'
        if provider_id == "opentopomap":
            contour = PROVIDER_CARD_COPY[locale]["contours"]
            addon = f'''<details class="provider-addon" data-provider-addon="contours">
                <summary class="provider-addon-toggle"><span><span class="provider-card-badge">{contour["badge"]}</span> <span class="provider-addon-title">{contour["name"]}</span></span></summary>
                <p class="provider-addon-copy">{contour["description"]}</p>
                <p class="provider-addon-count" data-contour-count data-count-template="{contour["count_template"]}">{contour["count_template"].replace("{count}", "157")}</p>
              </details>'''
        catalog_provider_id = "bbbike" if provider_id.startswith("bbbike") else provider_id
        type_attributes = ""
        if provider_id.startswith("bbbike"):
            map_type = "ontrail-latin1" if provider_id == "bbbike-ontrail" else "bbbike-latin1"
            type_attributes = f' data-provider-type="{map_type}" hidden'
        cards.append(
            f'''<article class="provider-card" data-provider-card="{catalog_provider_id}"{type_attributes}>
              <div class="provider-card-header">
                <h3>{provider["name"]}</h3>
                <p class="provider-count" data-provider-count data-count-template="{provider["count_template"]}"{count_hidden}>{count_markup}</p>
              </div>
              <p class="provider-summary">{provider["summary"]}</p>
              <ul class="provider-benefits">{benefits}</ul>
              {addon}
            </article>'''
        )
    return "\n".join(cards).replace("\n              \n", "\n")


def normalize_home(source: str, path: Path, locale: str) -> str:
    copy = HOME_COPY[locale]
    provider_cards = provider_cards_markup(locale, copy)
    provider_section = f'''<section class="provider-section section" id="providers" aria-labelledby="providers-title">
        <div class="shell">
          <div class="section-heading provider-intro"><p class="eyebrow">{copy["provider_eyebrow"]}</p><h2 id="providers-title">{copy["provider_title"]}</h2><p class="provider-copy">{copy["provider_copy"]}</p></div>
          <div class="provider-cards" id="provider-cards" data-provider-cards role="region" tabindex="0" aria-label="{copy["provider_list_label"]}">
            {provider_cards}
          </div>
          <div class="provider-controls" data-provider-controls hidden>
            <button type="button" data-provider-previous aria-controls="provider-cards">{PROVIDER_CARD_COPY[locale]["previous"]}</button>
            <button type="button" data-provider-next aria-controls="provider-cards">{PROVIDER_CARD_COPY[locale]["next"]}</button>
          </div>
        </div>
      </section>'''
    values = {**copy, "provider_section": provider_section}
    values.update({f"faq_question_{i}": question for i, question in enumerate(copy["faq_questions"])})
    template = Template((ROOT / "scripts/templates/home.html").read_text())
    source, count = re.subn(r"<main\b[\s\S]*?</main>", lambda _: template.substitute(values).rstrip(), source, count=1)
    if count != 1:
        raise ValueError(f"{path}: expected one Home main element")
    metadata = json.loads((ROOT / "site/metadata.json").read_text())
    description = next(page["description"] for page in metadata["pages"] if page["file"] == str(path.relative_to(ROOT)))
    return reduce_faq_schema(source, path, copy, description)


def main() -> None:
    for locale in LOCALES:
        path = home_path(locale)
        source = path.read_text(encoding="utf-8")
        path.write_text(normalize_home(source, path, locale), encoding="utf-8")
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
