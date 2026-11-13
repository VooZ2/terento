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
PROVIDER_SCRIPT_VERSION = "20261026-osmapa-v1"
FEATURE_SCRIPT_VERSION = "20261105-home-map-switch-v4"
ASSET_VERSION = "20261106-home-watch-srcset"
# Empty until Apple approves the listing; the button renders only once this is set.
APP_STORE_URL = ""
# Hero watch map styles (Königssee previews), self-hosted in site/assets/home/.
# Owner decision 2026-11-05: no visible map credit on the hero.
HERO_MAP_STYLES = (
    ("opentopomap", "OpenTopoMap"),
    ("freizeitkarte", "Freizeitkarte"),
    ("maprando", "MapRando"),
)
# Card thumbnails (High Tatras); plain BBBike has no preview there, so its card stays text-only.
CARD_THUMBNAILS = {
    "freizeitkarte": "freizeitkarte",
    "opentopomap": "opentopomap",
    "maprando": "maprando",
    "bbbike-ontrail": "bbbike-ontrail",
    "bbbike-opentopo": "bbbike-opentopo",
    "bbbike-all": "bbbike-ontrail",
    "osmapa": "osmapa-podstawowa",
}
EDGE_IMAGE = ROOT / "site/assets/home/edge-front.webp"
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
        "compare_styles": "Compare map styles live"
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
        "compare_styles": "Kartenstile live vergleichen"
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
        "compare_styles": "Comparer les styles en direct"
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
        "compare_styles": "Porównaj style map na żywo"
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
        "compare_styles": "Porovnat styly map naživo"
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
        "compare_styles": "Confronta gli stili dal vivo"
    }
}

def home_path(locale: str) -> Path:
    return ROOT / "site" / ("index.html" if locale == "en" else f"{locale}/index.html")


# Visible Home FAQ order; the FAQPage JSON-LD mirrors it exactly.
FAQ_ANSWER_KEYS = (
    "compatibility_answer",
    "basecamp_answer",
    "safety_answer",
    "update_answer",
    "connection_answer",
    "failure_answer",
    "web_installer_answer",
)


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
    if faq is None or not faq.get("mainEntity"):
        raise ValueError(f"{path}: expected FAQ schema entries")
    if len(copy["faq_questions"]) != len(FAQ_ANSWER_KEYS):
        raise ValueError(f"{path}: expected {len(FAQ_ANSWER_KEYS)} FAQ questions")
    faq["mainEntity"] = [
        {
            "@type": "Question",
            "name": question,
            "acceptedAnswer": {"@type": "Answer", "text": re.sub(r"<[^>]+>", "", copy[key])},
        }
        for question, key in zip(copy["faq_questions"], FAQ_ANSWER_KEYS)
    ]
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

# BBBike (OpenTopoMap) ships hidden like the other BBBike types; provider-list.js
# shows it once the catalog lists available opentopo-latin1 maps (catalog v5, app 1.1.0).
BBBIKE_OPENTOPO_CARD_COPY = {
    "en": ("For hiking and cycling in the familiar OpenTopoMap look, also where other maps are missing.", [
        "OpenTopoMap look: trails, paths and land cover",
        "Regional maps updated weekly",
        "Also for countries no other map here covers",
    ], "This map has no contour lines."),
    "de": ("Zum Wandern und Radfahren im bekannten OpenTopoMap-Stil, auch wo andere Karten fehlen.", [
        "OpenTopoMap-Stil: Wege, Pfade und Bodenbedeckung",
        "Wöchentlich aktualisierte Regionalkarten",
        "Auch für Länder, die keine andere Karte hier abdeckt",
    ], "Diese Karte enthält keine Höhenlinien."),
    "fr": ("Pour la randonnée et le vélo dans le style OpenTopoMap, même là où les autres cartes manquent.", [
        "Style OpenTopoMap : sentiers, chemins et occupation du sol",
        "Cartes régionales actualisées chaque semaine",
        "Aussi pour des pays qu’aucune autre carte ne couvre ici",
    ], "Cette carte n’a pas de courbes de niveau."),
    "pl": ("Na piesze i rowerowe wycieczki w znanym stylu OpenTopoMap, także tam, gdzie brakuje innych map.", [
        "Styl OpenTopoMap: szlaki, ścieżki i pokrycie terenu",
        "Mapy regionów aktualizowane co tydzień",
        "Także dla krajów, których nie obejmuje tu żadna inna mapa",
    ], "Ta mapa nie ma poziomic."),
    "cs": ("Na pěší a cyklistické výlety ve známém stylu OpenTopoMap, i tam, kde jiné mapy chybí.", [
        "Styl OpenTopoMap: stezky, cesty a pokryv krajiny",
        "Regionální mapy aktualizované každý týden",
        "Také pro země, které tu žádná jiná mapa nepokrývá",
    ], "Tato mapa nemá vrstevnice."),
    "it": ("Per escursioni a piedi e in bici nello stile OpenTopoMap, anche dove mancano altre mappe.", [
        "Stile OpenTopoMap: sentieri, percorsi e copertura del suolo",
        "Mappe regionali aggiornate ogni settimana",
        "Anche per paesi che nessun’altra mappa copre qui",
    ], "Questa mappa non ha curve di livello."),
}
BBBIKE_OPENTOPO_NOTES = {}
for _locale, (_summary, _benefits, _note) in BBBIKE_OPENTOPO_CARD_COPY.items():
    PROVIDER_CARD_COPY[_locale]["bbbike-opentopo"] = {
        "name": "BBBike (OpenTopoMap)",
        "count_template": PROVIDER_CARD_COPY[_locale]["maprando"]["count_template"],
        "summary": _summary,
        "benefits": _benefits,
    }
    BBBIKE_OPENTOPO_NOTES[_locale] = _note

# Home shows BBBike as one card covering all its map types; provider-list.js counts every available BBBike map.
BBBIKE_MERGED_CARD_COPY = {
    "en": ("Weekly-updated regional maps for cycling and walking, also where other maps are missing.", [
        "Ontrail: compact, with small roads and paths",
        "OpenTopoMap look: trails and land cover",
        "Covers countries no other map here does",
    ]),
    "de": ("Wöchentlich aktualisierte Regionalkarten fürs Radfahren und Wandern, auch wo andere Karten fehlen.", [
        "Ontrail: kompakt, mit kleinen Straßen und Wegen",
        "OpenTopoMap-Stil: Wege und Bodenbedeckung",
        "Auch für Länder, die keine andere Karte hier abdeckt",
    ]),
    "fr": ("Des cartes régionales mises à jour chaque semaine pour le vélo et la marche, même là où les autres manquent.", [
        "Ontrail : compacte, avec petites routes et chemins",
        "Style OpenTopoMap : sentiers et occupation du sol",
        "Couvre des pays qu’aucune autre carte ne couvre ici",
    ]),
    "pl": ("Mapy regionów aktualizowane co tydzień, na rower i piesze wycieczki, także tam, gdzie brakuje innych map.", [
        "Ontrail: kompaktowa, z mniejszymi drogami i ścieżkami",
        "Styl OpenTopoMap: szlaki i pokrycie terenu",
        "Obejmuje kraje, których nie ma tu żadna inna mapa",
    ]),
    "cs": ("Regionální mapy aktualizované každý týden, na kolo i pěšky, i tam, kde jiné mapy chybí.", [
        "Ontrail: kompaktní, s menšími silnicemi a cestami",
        "Styl OpenTopoMap: stezky a pokryv krajiny",
        "Pokrývá země, které tu žádná jiná mapa nemá",
    ]),
    "it": ("Mappe regionali aggiornate ogni settimana, per bici e cammino, anche dove mancano altre mappe.", [
        "Ontrail: compatta, con strade minori e sentieri",
        "Stile OpenTopoMap: sentieri e copertura del suolo",
        "Copre paesi che nessun’altra mappa copre qui",
    ]),
}
for _locale, (_summary, _benefits) in BBBIKE_MERGED_CARD_COPY.items():
    PROVIDER_CARD_COPY[_locale]["bbbike-all"] = {
        "name": "BBBike",
        "count_template": PROVIDER_CARD_COPY[_locale]["maprando"]["count_template"],
        "summary": _summary,
        "benefits": _benefits,
    }

# OSMapaPL ships hidden; provider-list.js shows it once the catalog lists the provider as active.
OSMAPA_CARD_COPY = {
    "en": ("For trips across Poland, on foot or by bike.", [
        "Detailed map of Poland, also with border areas",
        "Three styles: with Polish letters, without them, or a lighter, smaller map",
        "Contour lines as a separate package",
    ]),
    "de": ("Für Touren durch ganz Polen, zu Fuß oder mit dem Rad.", [
        "Detaillierte Karte von Polen, auch mit Grenzgebieten",
        "Drei Stile: mit polnischen Sonderzeichen, ohne sie oder als leichtere, kleinere Karte",
        "Höhenlinien als eigenes Paket",
    ]),
    "fr": ("Pour parcourir la Pologne à pied ou à vélo.", [
        "Carte détaillée de la Pologne, aussi avec les zones frontalières",
        "Trois styles : avec les lettres polonaises, sans elles, ou une carte plus légère et plus petite",
        "Courbes de niveau dans un paquet séparé",
    ]),
    "pl": ("Na piesze i rowerowe wycieczki po całej Polsce.", [
        "Szczegółowa mapa Polski, także z terenami przygranicznymi",
        "Trzy style: z polskimi znakami, bez nich lub lżejsza, mniejsza mapa",
        "Poziomice jako osobny pakiet",
    ]),
    "cs": ("Na pěší a cyklistické výlety po celém Polsku.", [
        "Podrobná mapa Polska, také s příhraničními oblastmi",
        "Tři styly: s polskými znaky, bez nich, nebo lehčí a menší mapa",
        "Vrstevnice jako samostatný balíček",
    ]),
    "it": ("Per girare la Polonia a piedi o in bici.", [
        "Mappa dettagliata della Polonia, anche con le zone di confine",
        "Tre stili: con le lettere polacche, senza, oppure una mappa più leggera e più piccola",
        "Curve di livello in un pacchetto separato",
    ]),
}
for _locale, (_summary, _benefits) in OSMAPA_CARD_COPY.items():
    PROVIDER_CARD_COPY[_locale]["osmapa"] = {
        "name": "OSMapaPL",
        "count_template": PROVIDER_CARD_COPY[_locale]["maprando"]["count_template"],
        "summary": _summary,
        "benefits": _benefits,
    }

MAPRANDO_LANGUAGE_NOTES = {'en': 'Some map labels are in French.', 'de': 'Einige Kartenbeschriftungen sind auf Französisch.', 'fr': 'Certains libellés de la carte sont en français.', 'pl': 'Niektóre opisy na mapie są po francusku.', 'cs': 'Některé popisky mapy jsou ve francouzštině.', 'it': 'Alcune etichette della mappa sono in francese.'}

def provider_card_addon(locale: str, provider_id: str, contour_count: bool = True) -> str:
    """The note or add-on under a provider card's benefits; the map styles page reuses it."""
    if provider_id == "maprando":
        return f'<p class="provider-language-note"><span aria-hidden="true">ⓘ</span><span>{html.escape(MAPRANDO_LANGUAGE_NOTES[locale])}</span></p>'
    if provider_id == "bbbike-opentopo":
        return f'<p class="provider-language-note"><span aria-hidden="true">ⓘ</span><span>{html.escape(BBBIKE_OPENTOPO_NOTES[locale])}</span></p>'
    if provider_id == "opentopomap":
        contour = PROVIDER_CARD_COPY[locale]["contours"]
        count = f'''
                <p class="provider-addon-count" data-contour-count data-count-template="{contour["count_template"]}">{contour["count_template"].replace("{count}", "157")}</p>''' if contour_count else ""
        return f'''<details class="provider-addon" data-provider-addon="contours">
                <summary class="provider-addon-toggle"><span><span class="provider-card-badge">{contour["badge"]}</span> <span class="provider-addon-title">{contour["name"]}</span></span></summary>
                <p class="provider-addon-copy">{contour["description"]}</p>{count}
              </details>'''
    return ""


def provider_cards_markup(locale: str, copy: dict[str, str]) -> str:
    cards = []
    for provider_id in ("freizeitkarte", "opentopomap", "maprando", "bbbike-all", "osmapa"):
        provider = PROVIDER_CARD_COPY[locale][provider_id]
        fallback_count = {"freizeitkarte": "63", "opentopomap": "177"}.get(provider_id)
        count_markup = provider["count_template"].replace("{count}", fallback_count) if fallback_count else ""
        count_hidden = "" if fallback_count else " hidden"
        benefits = "".join(f"<li>{html.escape(benefit)}</li>" for benefit in provider["benefits"])
        addon = provider_card_addon(locale, provider_id)
        catalog_provider_id = "bbbike" if provider_id.startswith("bbbike") else provider_id
        type_attributes = ""
        if provider_id == "bbbike-all":
            type_attributes = " hidden"
        elif provider_id.startswith("bbbike"):
            map_type = {"bbbike-ontrail": "ontrail-latin1", "bbbike-opentopo": "opentopo-latin1"}.get(provider_id, "bbbike-latin1")
            type_attributes = f' data-provider-type="{map_type}" hidden'
        if provider_id == "osmapa":
            type_attributes = " hidden"
        thumb = CARD_THUMBNAILS.get(provider_id)
        thumb_markup = f'''<img class="home-card-map" src="/assets/home/maps-{thumb}.webp?v={ASSET_VERSION}" width="640" height="400" alt="{html.escape(copy["card_map_alt"].replace("{name}", provider["name"]))}" loading="lazy" decoding="async">
              ''' if thumb else ""
        cards.append(
            f'''<article class="provider-card" data-provider-card="{catalog_provider_id}"{type_attributes}>
              {thumb_markup}<div class="provider-card-header">
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
          <div class="section-heading provider-intro"><h2 id="providers-title">{copy["provider_title"]}</h2><p class="provider-copy">{copy["provider_copy"]}</p></div>
          <div class="provider-cards" id="provider-cards" data-provider-cards role="region" tabindex="0" aria-label="{copy["provider_list_label"]}">
            {provider_cards}
          </div>
          <p class="provider-compare"><a class="text-link" href="{"/map-styles/" if locale == "en" else f"/{locale}/map-styles/"}" data-umami-event="maps-link-click" data-umami-event-location="home-providers">{PROVIDER_CARD_COPY[locale]["compare_styles"]}</a></p>
        </div>
      </section>'''
    values = {**copy, "provider_section": provider_section, "asset_version": ASSET_VERSION}
    def map_switch(alt: str, first: int, location: str) -> str:
        return "".join(
            f'<button type="button" class="home-switch-button" data-map-style="{style}" data-map-alt="{html.escape(alt.replace("{name}", name))}" aria-pressed="{str(index == first).lower()}" data-umami-event="map-style-switch" data-umami-event-location="{location}" data-umami-event-style="{style}">{name}</button>'
            for index, (style, name) in enumerate(HERO_MAP_STYLES)
        )
    values["hero_map_alt"] = html.escape(copy["hero_map_alt"].replace("{name}", HERO_MAP_STYLES[0][1]))
    values["hero_switch_buttons"] = map_switch(copy["hero_map_alt"], 0, "home-hero")
    app_store = (
        f'<a class="home-app-store" href="{APP_STORE_URL}" data-umami-event="app-store-click" data-umami-event-location="{{location}}">{html.escape(copy["app_store_label"])}</a>'
        if APP_STORE_URL else ""
    )
    values["app_store_hero"] = app_store.replace("{location}", "home-hero")
    values["edge_guide_href"] = "/guides/install-garmin-maps-edge-mac/" if locale == "en" else f"/{locale}/guides/install-garmin-maps-edge-mac/"
    # Freizeitkarte first on the Edge so the two devices open on different maps.
    values["edge_visual"] = (
        f'<figure class="home-device home-edge-figure" data-map-switch><div class="home-edge-screen">'
        f'<img class="home-edge-map" data-map-image src="/assets/home/edge-freizeitkarte.webp?v={ASSET_VERSION}" width="520" height="520" alt="{html.escape(copy["edge_map_alt"].replace("{name}", HERO_MAP_STYLES[1][1]))}" loading="lazy" decoding="async">'
        f'<img class="home-edge-body" src="/assets/home/edge-front.webp?v={ASSET_VERSION}" width="800" height="1200" alt="" loading="lazy" decoding="async"></div>'
        f'<figcaption><span class="home-switch" role="group" aria-label="{html.escape(copy["edge_switch_label"])}">{map_switch(copy["edge_map_alt"], 1, "home-edge")}</span></figcaption></figure>'
        if EDGE_IMAGE.exists() else ""
    )
    values.update({f"faq_question_{i}": question for i, question in enumerate(copy["faq_questions"])})
    template = Template((ROOT / "scripts/templates/home.html").read_text())
    source = re.sub(r'/home-features\.js\?v=[^"]+', f"/home-features.js?v={FEATURE_SCRIPT_VERSION}", source)
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
