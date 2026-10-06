#!/usr/bin/env python3
"""Build the six static Terento map style comparison pages.

English is the meaning source. Areas come from the canonical preview area
contract, and the style descriptions are the home page provider-card copy
(`scripts/normalize-home-ia.py`), so the two pages cannot contradict each
other. Header, footer and page metadata are filled in afterwards by
`normalize-public-shell.py` and `normalize-site-metadata.py`.
"""

from __future__ import annotations

import html
import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLUG = "map-styles/"
AREAS = json.loads((ROOT / "contracts/map-preview-areas.json").read_text(encoding="utf-8"))
HOME = runpy.run_path(str(ROOT / "scripts/normalize-home-ia.py"))
SHELL = runpy.run_path(str(ROOT / "scripts/normalize-public-shell.py"))
PROVIDER_COPY = HOME["PROVIDER_CARD_COPY"]
MAPRANDO_NOTES = HOME["MAPRANDO_LANGUAGE_NOTES"]
LEAFLET_VERSION = "1.9.4"
SCRIPT_VERSION = "20261006-map-styles-v3"
MANIFEST_URL = "https://api.terento.app/maps/previews/manifest.json"
STYLE_IDS = ("freizeitkarte", "opentopomap", "maprando", "bbbike", "bbbike-ontrail")

COPY: dict[str, dict[str, object]] = {
    "en": {
        "skip": "Skip to content",
        "eyebrow": "Map styles",
        "h1": "Compare free Garmin maps before you install",
        "lead": "See how five free map styles draw the same place. Pick a popular area, trail or city, then compare contour lines, trails, streets and labels.",
        "region": "Map style comparison",
        "kind": {"place": "Place", "route": "Trail", "city": "City"},
        "tabs": {"places": "Places", "routes": "Trails", "cities": "Cities", "country": "By country"},
        "browse": "Browse places",
        "choose": "Choose a place",
        "search_label": "Search places",
        "search_placeholder": "Search a place or country",
        "change": "Change place",
        "close": "Close place list",
        "count": {"place": {"one": "{n} place", "other": "{n} places"}, "route": {"one": "{n} trail", "other": "{n} trails"}, "city": {"one": "{n} city", "other": "{n} cities"}},
        "no_match": "No places match “{q}”. Try a country name, such as Italy or Nepal.",
        "best": "Best for comparing",
        "styles_of": "{n} of 5 styles",
        "styles_short": "styles",
        "view": "View",
        "modes": {"single": "One map", "split": "Side by side", "swipe": "Swipe"},
        "copy_link": "Copy link to this view",
        "copied": "Link copied",
        "copy_fallback": "Copy this link:",
        "style_group": "Map style",
        "left": "Left",
        "right": "Right",
        "left_style": "Left map style",
        "right_style": "Right map style",
        "swap": "Swap left and right styles",
        "split_caption": "Both maps move together. Pick a style for each side.",
        "swipe_caption": "Drag the divider to compare the two styles.",
        "not_covered": "{style} has no map for {place}",
        "not_covered_detail": "Pick another style to compare this place.",
        "pending": "The {style} preview for {place} is being prepared",
        "pending_detail": "Check back soon or pick another style.",
        "pending_short": "Preview coming soon",
        "not_covered_short": "No map here",
        "not_here": "not available here",
        "load_error": "Map previews could not be loaded. Check your connection and try again.",
        "retry": "Try again",
        "zoom_in": "Zoom in",
        "zoom_out": "Zoom out",
        "zoom": "Zoom",
        "divider": "Divider position",
        "map_label": "Map preview. Drag or use the arrow keys to move, plus and minus to zoom.",
        "showing": "Showing {style} for {place}",
        "about": "About the five map styles",
        "about_note": "Previews are close, not exact: your watch draws the map itself, so colours and detail can differ with the watch model and its map settings.",
        "noscript": "Turn on JavaScript to compare the map styles on the map.",
        "continents": {"europe": "Europe", "north-america": "North America", "south-america": "South America", "africa": "Africa", "asia": "Asia", "oceania": "Oceania"},
        "tags": {"mountains": "Mountains", "glaciers": "Glaciers", "lakes": "Lakes", "coast": "Coast", "forest": "Forest", "volcano": "Volcano", "canyon": "Canyon", "dunes": "Dunes", "river": "River", "highlands": "Highlands", "island": "Island", "rocks": "Rock formations", "city": "City", "cycling": "Cycling", "parks": "Parks", "old-town": "Old town", "non-latin-labels": "Non-Latin labels", "long-distance-trail": "Long-distance trail", "pilgrim-route": "Pilgrim route"},
    },
    "de": {
        "skip": "Zum Inhalt springen",
        "eyebrow": "Kartenstile",
        "h1": "Kostenlose Garmin-Karten vor der Installation vergleichen",
        "lead": "Sieh, wie fünf kostenlose Kartenstile denselben Ort darstellen. Wähle ein beliebtes Gebiet, einen Weg oder eine Stadt und vergleiche Höhenlinien, Wege, Straßen und Beschriftungen.",
        "region": "Vergleich der Kartenstile",
        "kind": {"place": "Ort", "route": "Weg", "city": "Stadt"},
        "tabs": {"places": "Orte", "routes": "Wege", "cities": "Städte", "country": "Nach Land"},
        "browse": "Orte durchsuchen",
        "choose": "Ort wählen",
        "search_label": "Orte suchen",
        "search_placeholder": "Ort oder Land suchen",
        "change": "Ort ändern",
        "close": "Ortsliste schließen",
        "count": {"place": {"one": "{n} Ort", "other": "{n} Orte"}, "route": {"one": "{n} Weg", "other": "{n} Wege"}, "city": {"one": "{n} Stadt", "other": "{n} Städte"}},
        "no_match": "Keine Orte passen zu „{q}“. Versuche einen Ländernamen wie Italien oder Nepal.",
        "best": "Am besten zum Vergleichen",
        "styles_of": "{n} von 5 Stilen",
        "styles_short": "Stile",
        "view": "Ansicht",
        "modes": {"single": "Eine Karte", "split": "Nebeneinander", "swipe": "Schieberegler"},
        "copy_link": "Link zu dieser Ansicht kopieren",
        "copied": "Link kopiert",
        "copy_fallback": "Diesen Link kopieren:",
        "style_group": "Kartenstil",
        "left": "Links",
        "right": "Rechts",
        "left_style": "Kartenstil links",
        "right_style": "Kartenstil rechts",
        "swap": "Stile links und rechts tauschen",
        "split_caption": "Beide Karten bewegen sich gemeinsam. Wähle für jede Seite einen Stil.",
        "swipe_caption": "Ziehe die Trennlinie, um beide Stile zu vergleichen.",
        "not_covered": "{style} hat keine Karte für {place}",
        "not_covered_detail": "Wähle einen anderen Stil, um diesen Ort zu vergleichen.",
        "pending": "Die {style}-Vorschau für {place} wird vorbereitet",
        "pending_detail": "Schau bald wieder vorbei oder wähle einen anderen Stil.",
        "pending_short": "Vorschau folgt bald",
        "not_covered_short": "Hier keine Karte",
        "not_here": "hier nicht verfügbar",
        "load_error": "Die Kartenvorschauen konnten nicht geladen werden. Prüfe deine Verbindung und versuche es erneut.",
        "retry": "Erneut versuchen",
        "zoom_in": "Vergrößern",
        "zoom_out": "Verkleinern",
        "zoom": "Zoom",
        "divider": "Position der Trennlinie",
        "map_label": "Kartenvorschau. Ziehen oder Pfeiltasten zum Bewegen, Plus und Minus zum Zoomen.",
        "showing": "{style} für {place} wird angezeigt",
        "about": "Über die fünf Kartenstile",
        "about_note": "Vorschauen sind nah dran, aber nicht exakt: Deine Uhr zeichnet die Karte selbst, daher können Farben und Details je nach Modell und Karteneinstellungen abweichen.",
        "noscript": "Aktiviere JavaScript, um die Kartenstile auf der Karte zu vergleichen.",
        "continents": {"europe": "Europa", "north-america": "Nordamerika", "south-america": "Südamerika", "africa": "Afrika", "asia": "Asien", "oceania": "Ozeanien"},
        "tags": {"mountains": "Berge", "glaciers": "Gletscher", "lakes": "Seen", "coast": "Küste", "forest": "Wald", "volcano": "Vulkan", "canyon": "Schlucht", "dunes": "Dünen", "river": "Fluss", "highlands": "Hochland", "island": "Insel", "rocks": "Felsformationen", "city": "Stadt", "cycling": "Radfahren", "parks": "Parks", "old-town": "Altstadt", "non-latin-labels": "Nicht-lateinische Beschriftung", "long-distance-trail": "Fernwanderweg", "pilgrim-route": "Pilgerweg"},
    },
    "fr": {
        "skip": "Aller au contenu",
        "eyebrow": "Styles de carte",
        "h1": "Comparez les cartes Garmin gratuites avant de les installer",
        "lead": "Voyez comment cinq styles de carte gratuits représentent le même lieu. Choisissez une zone, un sentier ou une ville populaire, puis comparez courbes de niveau, sentiers, rues et libellés.",
        "region": "Comparaison des styles de carte",
        "kind": {"place": "Lieu", "route": "Sentier", "city": "Ville"},
        "tabs": {"places": "Lieux", "routes": "Sentiers", "cities": "Villes", "country": "Par pays"},
        "browse": "Parcourir les lieux",
        "choose": "Choisir un lieu",
        "search_label": "Rechercher des lieux",
        "search_placeholder": "Rechercher un lieu ou un pays",
        "change": "Changer de lieu",
        "close": "Fermer la liste des lieux",
        "count": {"place": {"one": "{n} lieu", "other": "{n} lieux"}, "route": {"one": "{n} sentier", "other": "{n} sentiers"}, "city": {"one": "{n} ville", "other": "{n} villes"}},
        "no_match": "Aucun lieu ne correspond à « {q} ». Essayez un nom de pays, comme Italie ou Népal.",
        "best": "Idéal pour comparer",
        "styles_of": "{n} styles sur 5",
        "styles_short": "styles",
        "view": "Affichage",
        "modes": {"single": "Une carte", "split": "Côte à côte", "swipe": "Curseur"},
        "copy_link": "Copier le lien de cette vue",
        "copied": "Lien copié",
        "copy_fallback": "Copiez ce lien :",
        "style_group": "Style de carte",
        "left": "Gauche",
        "right": "Droite",
        "left_style": "Style de la carte de gauche",
        "right_style": "Style de la carte de droite",
        "swap": "Inverser les styles gauche et droite",
        "split_caption": "Les deux cartes se déplacent ensemble. Choisissez un style pour chaque côté.",
        "swipe_caption": "Faites glisser le séparateur pour comparer les deux styles.",
        "not_covered": "{style} n’a pas de carte pour {place}",
        "not_covered_detail": "Choisissez un autre style pour comparer ce lieu.",
        "pending": "L’aperçu {style} pour {place} est en préparation",
        "pending_detail": "Revenez bientôt ou choisissez un autre style.",
        "pending_short": "Aperçu bientôt disponible",
        "not_covered_short": "Pas de carte ici",
        "not_here": "non disponible ici",
        "load_error": "Les aperçus de carte n’ont pas pu être chargés. Vérifiez votre connexion et réessayez.",
        "retry": "Réessayer",
        "zoom_in": "Zoom avant",
        "zoom_out": "Zoom arrière",
        "zoom": "Zoom",
        "divider": "Position du séparateur",
        "map_label": "Aperçu de carte. Faites glisser ou utilisez les flèches pour vous déplacer, plus et moins pour zoomer.",
        "showing": "Affichage de {style} pour {place}",
        "about": "À propos des cinq styles de carte",
        "about_note": "Les aperçus sont proches, mais pas exacts : votre montre dessine elle-même la carte, les couleurs et le niveau de détail peuvent donc varier selon le modèle et ses réglages de carte.",
        "noscript": "Activez JavaScript pour comparer les styles sur la carte.",
        "continents": {"europe": "Europe", "north-america": "Amérique du Nord", "south-america": "Amérique du Sud", "africa": "Afrique", "asia": "Asie", "oceania": "Océanie"},
        "tags": {"mountains": "Montagnes", "glaciers": "Glaciers", "lakes": "Lacs", "coast": "Côte", "forest": "Forêt", "volcano": "Volcan", "canyon": "Canyon", "dunes": "Dunes", "river": "Rivière", "highlands": "Hautes terres", "island": "Île", "rocks": "Formations rocheuses", "city": "Ville", "cycling": "Vélo", "parks": "Parcs", "old-town": "Vieille ville", "non-latin-labels": "Libellés non latins", "long-distance-trail": "Grande randonnée", "pilgrim-route": "Chemin de pèlerinage"},
    },
    "pl": {
        "skip": "Przejdź do treści",
        "eyebrow": "Style map",
        "h1": "Porównaj darmowe mapy Garmin przed instalacją",
        "lead": "Zobacz, jak pięć darmowych stylów map przedstawia to samo miejsce. Wybierz popularny obszar, szlak lub miasto i porównaj poziomice, szlaki, ulice oraz opisy.",
        "region": "Porównanie stylów map",
        "kind": {"place": "Miejsce", "route": "Szlak", "city": "Miasto"},
        "tabs": {"places": "Miejsca", "routes": "Szlaki", "cities": "Miasta", "country": "Według kraju"},
        "browse": "Przeglądaj miejsca",
        "choose": "Wybierz miejsce",
        "search_label": "Szukaj miejsc",
        "search_placeholder": "Szukaj miejsca lub kraju",
        "change": "Zmień miejsce",
        "close": "Zamknij listę miejsc",
        "count": {"place": {"one": "{n} miejsce", "few": "{n} miejsca", "many": "{n} miejsc", "other": "{n} miejsca"}, "route": {"one": "{n} szlak", "few": "{n} szlaki", "many": "{n} szlaków", "other": "{n} szlaku"}, "city": {"one": "{n} miasto", "few": "{n} miasta", "many": "{n} miast", "other": "{n} miasta"}},
        "no_match": "Brak miejsc pasujących do „{q}”. Spróbuj nazwy kraju, np. Włochy lub Nepal.",
        "best": "Najlepsze do porównania",
        "styles_of": "{n} z 5 stylów",
        "styles_short": "stylów",
        "view": "Widok",
        "modes": {"single": "Jedna mapa", "split": "Obok siebie", "swipe": "Suwak"},
        "copy_link": "Kopiuj link do tego widoku",
        "copied": "Link skopiowany",
        "copy_fallback": "Skopiuj ten link:",
        "style_group": "Styl mapy",
        "left": "Lewa",
        "right": "Prawa",
        "left_style": "Styl lewej mapy",
        "right_style": "Styl prawej mapy",
        "swap": "Zamień style lewej i prawej mapy",
        "split_caption": "Obie mapy przesuwają się razem. Wybierz styl dla każdej strony.",
        "swipe_caption": "Przeciągnij separator, aby porównać oba style.",
        "not_covered": "{style} nie ma mapy dla miejsca {place}",
        "not_covered_detail": "Wybierz inny styl, aby porównać to miejsce.",
        "pending": "Podgląd {style} dla miejsca {place} jest w przygotowaniu",
        "pending_detail": "Zajrzyj wkrótce lub wybierz inny styl.",
        "pending_short": "Podgląd wkrótce",
        "not_covered_short": "Brak mapy w tym miejscu",
        "not_here": "niedostępne tutaj",
        "load_error": "Nie udało się wczytać podglądów map. Sprawdź połączenie i spróbuj ponownie.",
        "retry": "Spróbuj ponownie",
        "zoom_in": "Przybliż",
        "zoom_out": "Oddal",
        "zoom": "Powiększenie",
        "divider": "Położenie separatora",
        "map_label": "Podgląd mapy. Przeciągnij lub użyj strzałek, aby przesuwać, plus i minus, aby zmieniać powiększenie.",
        "showing": "Wyświetlono {style} dla miejsca {place}",
        "about": "O pięciu stylach map",
        "about_note": "Podglądy są zbliżone, ale nie dokładne: zegarek sam rysuje mapę, więc kolory i szczegóły mogą się różnić w zależności od modelu i ustawień mapy.",
        "noscript": "Włącz JavaScript, aby porównać style na mapie.",
        "continents": {"europe": "Europa", "north-america": "Ameryka Północna", "south-america": "Ameryka Południowa", "africa": "Afryka", "asia": "Azja", "oceania": "Oceania"},
        "tags": {"mountains": "Góry", "glaciers": "Lodowce", "lakes": "Jeziora", "coast": "Wybrzeże", "forest": "Las", "volcano": "Wulkan", "canyon": "Kanion", "dunes": "Wydmy", "river": "Rzeka", "highlands": "Wyżyny", "island": "Wyspa", "rocks": "Formacje skalne", "city": "Miasto", "cycling": "Rower", "parks": "Parki", "old-town": "Stare miasto", "non-latin-labels": "Opisy niełacińskie", "long-distance-trail": "Szlak długodystansowy", "pilgrim-route": "Szlak pielgrzymkowy"},
    },
    "cs": {
        "skip": "Přejít k obsahu",
        "eyebrow": "Styly map",
        "h1": "Porovnejte bezplatné mapy Garmin před instalací",
        "lead": "Podívejte se, jak pět bezplatných stylů map zobrazuje stejné místo. Vyberte oblíbenou oblast, stezku nebo město a porovnejte vrstevnice, stezky, ulice a popisky.",
        "region": "Porovnání stylů map",
        "kind": {"place": "Místo", "route": "Stezka", "city": "Město"},
        "tabs": {"places": "Místa", "routes": "Stezky", "cities": "Města", "country": "Podle země"},
        "browse": "Procházet místa",
        "choose": "Vyberte místo",
        "search_label": "Hledat místa",
        "search_placeholder": "Hledat místo nebo zemi",
        "change": "Změnit místo",
        "close": "Zavřít seznam míst",
        "count": {"place": {"one": "{n} místo", "few": "{n} místa", "many": "{n} místa", "other": "{n} míst"}, "route": {"one": "{n} stezka", "few": "{n} stezky", "many": "{n} stezky", "other": "{n} stezek"}, "city": {"one": "{n} město", "few": "{n} města", "many": "{n} města", "other": "{n} měst"}},
        "no_match": "Hledání „{q}“ neodpovídá žádné místo. Zkuste název země, například Itálie nebo Nepál.",
        "best": "Nejlepší k porovnání",
        "styles_of": "{n} z 5 stylů",
        "styles_short": "stylů",
        "view": "Zobrazení",
        "modes": {"single": "Jedna mapa", "split": "Vedle sebe", "swipe": "Posuvník"},
        "copy_link": "Kopírovat odkaz na toto zobrazení",
        "copied": "Odkaz zkopírován",
        "copy_fallback": "Zkopírujte tento odkaz:",
        "style_group": "Styl mapy",
        "left": "Vlevo",
        "right": "Vpravo",
        "left_style": "Styl levé mapy",
        "right_style": "Styl pravé mapy",
        "swap": "Prohodit styly vlevo a vpravo",
        "split_caption": "Obě mapy se pohybují společně. Vyberte styl pro každou stranu.",
        "swipe_caption": "Přetáhněte dělicí čáru a porovnejte oba styly.",
        "not_covered": "{style} nemá mapu pro {place}",
        "not_covered_detail": "Vyberte jiný styl a porovnejte toto místo.",
        "pending": "Náhled {style} pro {place} se připravuje",
        "pending_detail": "Vraťte se brzy nebo vyberte jiný styl.",
        "pending_short": "Náhled brzy",
        "not_covered_short": "Zde není mapa",
        "not_here": "zde není k dispozici",
        "load_error": "Náhledy map se nepodařilo načíst. Zkontrolujte připojení a zkuste to znovu.",
        "retry": "Zkusit znovu",
        "zoom_in": "Přiblížit",
        "zoom_out": "Oddálit",
        "zoom": "Přiblížení",
        "divider": "Poloha dělicí čáry",
        "map_label": "Náhled mapy. Posouvejte tažením nebo šipkami, přibližujte plusem a minusem.",
        "showing": "Zobrazeno {style} pro {place}",
        "about": "O pěti stylech map",
        "about_note": "Náhledy jsou blízké, ale ne přesné: hodinky kreslí mapu samy, takže barvy a podrobnosti se mohou lišit podle modelu a nastavení mapy.",
        "noscript": "Zapněte JavaScript a porovnejte styly na mapě.",
        "continents": {"europe": "Evropa", "north-america": "Severní Amerika", "south-america": "Jižní Amerika", "africa": "Afrika", "asia": "Asie", "oceania": "Oceánie"},
        "tags": {"mountains": "Hory", "glaciers": "Ledovce", "lakes": "Jezera", "coast": "Pobřeží", "forest": "Les", "volcano": "Sopka", "canyon": "Kaňon", "dunes": "Duny", "river": "Řeka", "highlands": "Vysočina", "island": "Ostrov", "rocks": "Skalní útvary", "city": "Město", "cycling": "Cyklistika", "parks": "Parky", "old-town": "Staré město", "non-latin-labels": "Nelatinkové popisky", "long-distance-trail": "Dálková trasa", "pilgrim-route": "Poutní cesta"},
    },
    "it": {
        "skip": "Vai al contenuto",
        "eyebrow": "Stili di mappa",
        "h1": "Confronta le mappe Garmin gratuite prima di installarle",
        "lead": "Guarda come cinque stili di mappa gratuiti disegnano lo stesso luogo. Scegli una zona, un sentiero o una città popolare, poi confronta curve di livello, sentieri, strade ed etichette.",
        "region": "Confronto degli stili di mappa",
        "kind": {"place": "Luogo", "route": "Sentiero", "city": "Città"},
        "tabs": {"places": "Luoghi", "routes": "Sentieri", "cities": "Città", "country": "Per paese"},
        "browse": "Sfoglia i luoghi",
        "choose": "Scegli un luogo",
        "search_label": "Cerca luoghi",
        "search_placeholder": "Cerca un luogo o un paese",
        "change": "Cambia luogo",
        "close": "Chiudi l’elenco dei luoghi",
        "count": {"place": {"one": "{n} luogo", "other": "{n} luoghi"}, "route": {"one": "{n} sentiero", "other": "{n} sentieri"}, "city": {"one": "{n} città", "other": "{n} città"}},
        "no_match": "Nessun luogo corrisponde a “{q}”. Prova con il nome di un paese, come Italia o Nepal.",
        "best": "Ideali per il confronto",
        "styles_of": "{n} stili su 5",
        "styles_short": "stili",
        "view": "Vista",
        "modes": {"single": "Una mappa", "split": "Affiancate", "swipe": "Cursore"},
        "copy_link": "Copia il link a questa vista",
        "copied": "Link copiato",
        "copy_fallback": "Copia questo link:",
        "style_group": "Stile di mappa",
        "left": "Sinistra",
        "right": "Destra",
        "left_style": "Stile della mappa a sinistra",
        "right_style": "Stile della mappa a destra",
        "swap": "Scambia gli stili di sinistra e destra",
        "split_caption": "Le due mappe si muovono insieme. Scegli uno stile per ogni lato.",
        "swipe_caption": "Trascina il divisore per confrontare i due stili.",
        "not_covered": "{style} non ha una mappa per {place}",
        "not_covered_detail": "Scegli un altro stile per confrontare questo luogo.",
        "pending": "L’anteprima {style} per {place} è in preparazione",
        "pending_detail": "Torna presto o scegli un altro stile.",
        "pending_short": "Anteprima in arrivo",
        "not_covered_short": "Nessuna mappa qui",
        "not_here": "non disponibile qui",
        "load_error": "Non è stato possibile caricare le anteprime delle mappe. Controlla la connessione e riprova.",
        "retry": "Riprova",
        "zoom_in": "Ingrandisci",
        "zoom_out": "Riduci",
        "zoom": "Zoom",
        "divider": "Posizione del divisore",
        "map_label": "Anteprima della mappa. Trascina o usa le frecce per spostarti, più e meno per lo zoom.",
        "showing": "Visualizzazione di {style} per {place}",
        "about": "Informazioni sui cinque stili di mappa",
        "about_note": "Le anteprime sono vicine, ma non identiche: l’orologio disegna la mappa da sé, quindi colori e dettagli possono variare in base al modello e alle impostazioni della mappa.",
        "noscript": "Attiva JavaScript per confrontare gli stili sulla mappa.",
        "continents": {"europe": "Europa", "north-america": "Nord America", "south-america": "Sud America", "africa": "Africa", "asia": "Asia", "oceania": "Oceania"},
        "tags": {"mountains": "Montagne", "glaciers": "Ghiacciai", "lakes": "Laghi", "coast": "Costa", "forest": "Foresta", "volcano": "Vulcano", "canyon": "Canyon", "dunes": "Dune", "river": "Fiume", "highlands": "Altopiani", "island": "Isola", "rocks": "Formazioni rocciose", "city": "Città", "cycling": "Bici", "parks": "Parchi", "old-town": "Centro storico", "non-latin-labels": "Etichette non latine", "long-distance-trail": "Sentiero a lunga percorrenza", "pilgrim-route": "Cammino di pellegrinaggio"},
    },
}


ICONS = {
    "search": '<path d="M11 4.5a6.5 6.5 0 1 1 0 13 6.5 6.5 0 0 1 0-13Z"/><path d="m20 20-4.2-4.2"/>',
    "close": '<path d="M6 6l12 12M18 6 6 18"/>',
    "pin": '<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11Z"/><circle cx="12" cy="10" r="2.3"/>',
    "single": '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/>',
    "split": '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M12 4.5v15"/>',
    "swipe": '<path d="m9 7-5 5 5 5M15 7l5 5-5 5"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "swap": '<path d="M7 7h12l-3.5-3.5M17 17H5l3.5 3.5"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5h.01"/>',
    "chevron": '<path d="m9 6 6 6-6 6"/>',
}


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def icon(name: str) -> str:
    return f'<svg class="map-styles-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">{ICONS[name]}</svg>'


def localized_path(locale: str, suffix: str = "") -> str:
    return "/" + ("" if locale == "en" else f"{locale}/") + suffix


def style_copy(locale: str) -> list[dict[str, object]]:
    styles = []
    for style_id in STYLE_IDS:
        provider = PROVIDER_COPY[locale][style_id]
        styles.append({
            "id": style_id,
            "name": provider["name"],
            "summary": provider["summary"],
            "benefits": list(provider["benefits"]),
            "note": MAPRANDO_NOTES[locale] if style_id == "maprando" else None,
        })
    return styles


def area_name(area: dict, locale: str) -> str:
    return area["name"].get(locale) or area["name"]["en"]


def about_markup(locale: str, copy: dict[str, object], styles: list[dict[str, object]]) -> str:
    cards = []
    for style in styles:
        benefits = "".join(f"<li>{esc(item)}</li>" for item in style["benefits"])
        note = (
            f'<p class="map-styles-about-language">{icon("info")}<span>{esc(style["note"])}</span></p>'
            if style["note"] else ""
        )
        cards.append(
            f'<article class="map-styles-about-card" data-style-card="{esc(style["id"])}">'
            f'<h3>{esc(style["name"])}</h3>'
            f'<p class="map-styles-about-summary">{esc(style["summary"])}</p>'
            f'<ul>{benefits}</ul>{note}'
            "</article>"
        )
    return "".join(cards)


def page_data(locale: str, copy: dict[str, object], styles: list[dict[str, object]]) -> str:
    document = {
        "locale": locale,
        "manifestUrl": MANIFEST_URL,
        "areas": [
            {
                "id": area["id"],
                "kind": area["kind"],
                "name": area_name(area, locale),
                "countryCodes": area["countryCodes"],
                "continent": area["continent"],
                "center": area["center"],
                "tags": area["tags"],
                "routeName": area.get("routeName"),
                "featured": bool(area.get("featured")),
                "zoom": AREAS["zoom"][area["kind"]],
                "sizeKm": area.get("sizeKm") or AREAS["areaSizesKm"][area["kind"]],
            }
            for area in AREAS["areas"]
        ],
        "styles": [{key: style[key] for key in ("id", "name", "summary")} for style in styles],
        "copy": {key: value for key, value in copy.items() if key not in {"h1", "lead", "eyebrow", "skip", "noscript", "about", "about_note"}},
    }
    return json.dumps(document, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def render(locale: str) -> str:
    copy = COPY[locale]
    styles = style_copy(locale)
    default = next(area for area in AREAS["areas"] if area["id"] == "dolomites-tre-cime")
    tabs = "".join(
        f'<button type="button" role="tab" aria-selected="{"true" if key == "places" else "false"}" data-tab="{key}">{esc(label)}</button>'
        for key, label in copy["tabs"].items()
    )
    modes = "".join(
        f'<button type="button" class="map-styles-mode" data-mode="{key}" aria-pressed="{"true" if key == "swipe" else "false"}" aria-label="{esc(label)}">{icon(key)}<span class="map-styles-mode-text">{esc(label)}</span></button>'
        for key, label in copy["modes"].items()
    )
    return f'''<!doctype html>
<html lang="{locale}" data-language="{locale}" data-page="map-styles">
  <head>
    <script defer src="/site-shell.js?v={SHELL["SHELL_VERSION"]}"></script>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="theme-color" content="#F7F3EC">
    <meta name="theme-color" media="(prefers-color-scheme: dark)" content="#222A2B">
    <title>Terento</title>
    <link rel="icon" href="/favicon.ico?v=20260820-4" sizes="any">
    <link rel="icon" href="/favicon.svg?v=20260820-4" type="image/svg+xml">
    <link rel="apple-touch-icon" href="/apple-touch-icon.png?v=20260820-4">
    <link rel="mask-icon" href="/safari-pinned-tab.svg?v=20260820-4" color="#7898A8">
    <link rel="manifest" href="/manifest.webmanifest">
    <link rel="stylesheet" href="/styles.css?v={SHELL["STYLE_VERSION"]}">
    <link rel="stylesheet" href="/assets/vendor/leaflet-{LEAFLET_VERSION}/leaflet.css">
    <script defer src="/language.js?v={SHELL["LANGUAGE_VERSION"]}"></script>
    <script defer src="/privacy-consent.js?v={SHELL["UMAMI_SCRIPT_VERSION"]}"></script>
    <script defer src="/assets/vendor/leaflet-{LEAFLET_VERSION}/leaflet.js"></script>
    <script defer src="/map-styles/map-styles-data.js?v={SCRIPT_VERSION}"></script>
    <script defer src="/map-styles/map-styles.js?v={SCRIPT_VERSION}"></script>
  </head>
  <body>
    <a class="skip-link" href="#main-content">{esc(copy["skip"])}</a>
    <header class="site-header"></header>
    <main id="main-content" class="map-styles-main">
      <section class="map-styles-hero" aria-labelledby="map-styles-title">
        <div class="shell">
          <p class="eyebrow"><span class="status-dot" aria-hidden="true"></span>{esc(copy["eyebrow"])}</p>
          <h1 id="map-styles-title">{esc(copy["h1"])}</h1>
          <p class="hero-lede map-styles-lead">{esc(copy["lead"])}</p>
        </div>
      </section>

      <section class="map-styles-frame" aria-label="{esc(copy["region"])}">
        <div class="map-styles-viewer" id="map-styles" data-mode="swipe">
          <div class="map-styles-stage" id="map-styles-stage" data-mode="swipe">
            <div class="map-styles-pane map-styles-pane-a"><div class="map-styles-map" id="map-styles-map-a" role="application" aria-roledescription="map" aria-label="{esc(copy["map_label"])}"></div><span class="map-styles-pane-label" id="map-styles-label-a"></span><div class="map-styles-notice" id="map-styles-notice-a" hidden></div></div>
            <div class="map-styles-pane map-styles-pane-b"><div class="map-styles-map" id="map-styles-map-b" role="application" aria-roledescription="map" aria-label="{esc(copy["map_label"])}"></div><span class="map-styles-pane-label" id="map-styles-label-b"></span><div class="map-styles-notice" id="map-styles-notice-b" hidden></div></div>
            <div class="map-styles-divider" id="map-styles-divider"><div class="map-styles-knob" id="map-styles-knob" role="slider" tabindex="0" aria-label="{esc(copy["divider"])}" aria-valuemin="5" aria-valuemax="95" aria-valuenow="50">{icon("swipe")}</div></div>
          </div>

          <div class="map-styles-overlay map-styles-place" id="map-styles-place" data-open="false">
            <div class="map-styles-place-card" id="map-styles-place-card">
              <p class="map-styles-overlay-eyebrow" id="map-styles-place-kind">{esc(copy["kind"][default["kind"]])}</p>
              <h2 id="map-styles-area-title">{esc(area_name(default, locale))}</h2>
              <p class="map-styles-place-meta" id="map-styles-area-meta"></p>
              <button type="button" class="map-styles-change" id="map-styles-open-places" aria-expanded="false" aria-controls="map-styles-browser">{icon("search")}<span>{esc(copy["change"])}</span></button>
            </div>
            <div class="map-styles-browser" id="map-styles-browser" hidden>
              <div class="map-styles-browser-head">
                <h2>{esc(copy["choose"])}</h2>
                <button type="button" class="map-styles-icon-button" id="map-styles-close-places" aria-label="{esc(copy["close"])}">{icon("close")}</button>
              </div>
              <div class="map-styles-tabs" role="tablist" aria-label="{esc(copy["browse"])}">{tabs}</div>
              <div class="map-styles-search">
                {icon("search")}
                <label class="sr-only" for="map-styles-search">{esc(copy["search_label"])}</label>
                <input id="map-styles-search" type="search" placeholder="{esc(copy["search_placeholder"])}" autocomplete="off">
              </div>
              <p class="map-styles-count" id="map-styles-count" aria-live="polite"></p>
              <div class="map-styles-list" id="map-styles-list"></div>
            </div>
          </div>

          <div class="map-styles-overlay map-styles-tools" role="group" aria-label="{esc(copy["view"])}">
            {modes}
            <span class="map-styles-tools-separator" aria-hidden="true"></span>
            <button type="button" class="map-styles-mode" id="map-styles-copy-link" aria-label="{esc(copy["copy_link"])}" title="{esc(copy["copy_link"])}">{icon("link")}</button>
          </div>

          <div class="map-styles-overlay map-styles-dock" id="map-styles-dock">
            <div class="map-styles-pills" role="radiogroup" aria-label="{esc(copy["style_group"])}" id="map-styles-pills" hidden></div>
            <div class="map-styles-compare" id="map-styles-compare">
              <span class="map-styles-side" aria-hidden="true">{esc(copy["left"])}</span>
              <label class="sr-only" for="map-styles-style-a">{esc(copy["left_style"])}</label>
              <select id="map-styles-style-a"></select>
              <button type="button" class="map-styles-icon-button" id="map-styles-swap" aria-label="{esc(copy["swap"])}">{icon("swap")}</button>
              <label class="sr-only" for="map-styles-style-b">{esc(copy["right_style"])}</label>
              <select id="map-styles-style-b"></select>
              <span class="map-styles-side" aria-hidden="true">{esc(copy["right"])}</span>
            </div>
            <p class="map-styles-caption" id="map-styles-caption"></p>
          </div>

          <div class="map-styles-zoom" role="group" aria-label="{esc(copy["zoom"])}">
            <button type="button" id="map-styles-zoom-in" aria-label="{esc(copy["zoom_in"])}">{icon("plus")}</button>
            <span class="map-styles-zoom-level" id="map-styles-zoom-level">100%</span>
            <button type="button" id="map-styles-zoom-out" aria-label="{esc(copy["zoom_out"])}">{icon("minus")}</button>
          </div>
          <p class="map-styles-attribution" id="map-styles-attribution"></p>
          <div class="map-styles-error" id="map-styles-error" hidden><p>{esc(copy["load_error"])}</p><button type="button" id="map-styles-retry">{esc(copy["retry"])}</button></div>
        </div>
        <p class="sr-only" id="map-styles-live" aria-live="polite"></p>
        <div class="map-styles-toast" id="map-styles-toast" role="status" hidden></div>
        <noscript><p class="shell map-styles-noscript">{esc(copy["noscript"])}</p></noscript>
      </section>

      <section class="shell map-styles-about" aria-label="{esc(copy["about"])}">
        <details class="map-styles-about-details" id="map-styles-about">
          <summary><span class="map-styles-about-label">{icon("info")}<span>{esc(copy["about"])}</span></span></summary>
          <div class="map-styles-about-grid">{about_markup(locale, copy, styles)}</div>
          <p class="map-styles-about-note">{esc(copy["about_note"])}</p>
        </details>
      </section>
    </main>
    <footer class="site-footer"></footer>
    <script type="application/json" id="map-styles-data">{page_data(locale, copy, styles)}</script>
  </body>
</html>
'''


def main() -> None:
    for locale in COPY:
        path = ROOT / "site" / ("" if locale == "en" else locale) / SLUG / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(locale), encoding="utf-8")
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
