#!/usr/bin/env python3
"""Apply the shared Home information-architecture contract to each locale."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCALES = ("en", "de", "fr", "pl", "cs", "it")
FAQ_KEEP = (0, 1, 4, 5, 6)
PROVIDER_SCRIPT_VERSION = "20260912-bbbike-types-v1"
FEATURE_SCRIPT_VERSION = "20260904-home-workflow-tabs"
EMAIL_URL = "mailto:hello@terento.app?subject=Terento%20installation%20issue"
EMAIL_URL_HTML = EMAIL_URL.replace("@", "&#64;")
HOME_COPY = {
    "en": {
        "scope_href": "/compatibility/",
        "hero_title": "Install maps on Garmin watches, simply",
        "hero_lede": "Install, update, and manage third-party maps from a native macOS app — without manual file transfers.",
        "hero_compatibility": "Check compatibility",
        "experience_label": "How it works",
        "experience_title": "Connect → Install → Done",
        "feature_tabs_label": "Map features",
        "install_tab": "Install maps",
        "manage_tab": "Manage maps",
        "problem": "Installing third-party maps should be simple and fast — without extra software, separate download steps, or technical know-how.",
        "problem_secondary": "Terento brings the whole process together in three simple steps.",
        "scope": "Terento is built for Garmin smartwatches with map support. Compatibility is confirmed for each model and variant using real installation results.",
        "compatibility_answer": "See the <a href=\"/compatibility/\" data-umami-event=\"compatibility-link-click\" data-umami-event-location=\"home-faq-compatibility\">Compatibility page</a> for Garmin models and variants confirmed by real installations.",
        "install_step": "Choose maps from the catalog, or add your own compatible .img map.",
        "install_showcase": "Choose maps from the catalog by region, or add your own compatible .img map.",
        "done_label": "Done",
        "done_step": "Your maps are installed and ready to use on your watch.",
        "manage_showcase": "See what's installed, update maps when newer releases are available, and remove third-party maps managed by Terento. Original Garmin maps remain protected.",
        "basecamp_answer": "Yes. Terento is designed to make third-party map management on macOS simple and fast — from choosing a map to installing, updating, and managing it on your Garmin watch. <a href=\"/guides/install-garmin-maps-mac/\" data-umami-event=\"guide-link-click\" data-umami-event-location=\"home-faq-basecamp\">Read the installation guide.</a>",
        "safety_answer": "Yes. Add a compatible .img map from your Mac and install it on your connected Garmin watch.",
        "update_answer": "Yes. Terento shows when newer releases are available and helps you update Terento-managed third-party maps.",
        "failure_answer": "On the failed installation screen, choose “Report issue”. Terento opens GitHub with the report already filled in. Review it before posting: GitHub issues are public. For help by email, include your watch model, map region and what happened.",
        "provider_eyebrow": "Available maps",
        "provider_title": "Explore available maps.",
        "provider_copy": "Choose maps from available providers. Maps are downloaded from each provider's original source.",
        "download_label": "Download",
        "faq_eyebrow": "Have questions?",
        "faq_questions": ["Which Garmin watches work with Terento?", "Can I install third-party maps on a Garmin watch from a Mac without BaseCamp?", "Can I add my own .img map?", "Can I update maps later?", "What should I do if installation fails?"],
        "final_cta_eyebrow": "Get started today",
        "final_cta_title": "Ready for an easier way to install maps?",
        "final_cta_body": "Download Terento and start managing third-party maps from your Mac.",
        "provider_list_label": "Map providers",
    },
    "de": {
        "scope_href": "/de/compatibility/",
        "hero_title": "Karten einfach auf Garmin-Uhren installieren",
        "hero_lede": "Installiere, aktualisiere und verwalte Drittanbieter-Karten mit einer nativen macOS-App — ohne manuelle Dateiübertragungen.",
        "hero_compatibility": "Kompatibilität prüfen",
        "experience_label": "So funktioniert es",
        "experience_title": "Verbinden → Installieren → Fertig",
        "feature_tabs_label": "Kartenfunktionen",
        "install_tab": "Karten installieren",
        "manage_tab": "Karten verwalten",
        "problem": "Die Installation von Drittanbieter-Karten sollte einfach und schnell sein — ohne zusätzliche Software, separate Download-Schritte oder technisches Vorwissen.",
        "problem_secondary": "Terento bündelt den gesamten Ablauf in drei einfachen Schritten.",
        "scope": "Terento ist für Garmin-Smartwatches mit Kartenunterstützung entwickelt. Die Kompatibilität wird für jedes Modell und jede Variante anhand echter Installationsergebnisse bestätigt.",
        "compatibility_answer": "Auf der <a href=\"/de/compatibility/\" data-umami-event=\"compatibility-link-click\" data-umami-event-location=\"home-faq-compatibility\">Kompatibilitätsseite</a> findest du Garmin-Modelle und Varianten, die durch echte Installationen bestätigt wurden.",
        "install_step": "Wähle Karten aus dem Katalog oder füge deine eigene kompatible .img-Karte hinzu.",
        "install_showcase": "Wähle Karten aus dem Katalog nach Region oder füge deine eigene kompatible .img-Karte hinzu.",
        "done_label": "Fertig",
        "done_step": "Deine Karten sind installiert und auf deiner Uhr einsatzbereit.",
        "manage_showcase": "Sieh, was installiert ist, aktualisiere Karten, wenn neuere Versionen verfügbar sind, und entferne von Terento verwaltete Drittanbieter-Karten. Originale Garmin-Karten bleiben geschützt.",
        "basecamp_answer": "Ja. Terento wurde entwickelt, um die Verwaltung von Drittanbieter-Karten auf macOS einfach und schnell zu machen — von der Kartenauswahl bis zur Installation, Aktualisierung und Verwaltung auf deiner Garmin-Uhr. <a href=\"/de/guides/install-garmin-maps-mac/\" data-umami-event=\"guide-link-click\" data-umami-event-location=\"home-faq-basecamp\">Lies die Installationsanleitung.</a>",
        "safety_answer": "Ja. Füge eine kompatible .img-Karte von deinem Mac hinzu und installiere sie auf deiner verbundenen Garmin-Uhr.",
        "update_answer": "Ja. Terento zeigt, wenn neuere Veröffentlichungen verfügbar sind, und hilft dir, von Terento verwaltete Drittanbieter-Karten zu aktualisieren.",
        "failure_answer": "Wähle nach einer fehlgeschlagenen Installation „Report issue“. Terento öffnet GitHub mit einem bereits ausgefüllten Bericht. Prüfe ihn vor dem Veröffentlichen: GitHub-Issues sind öffentlich. Für Hilfe per E-Mail nenne dein Uhrenmodell, die Kartenregion und den Fehler.",
        "provider_eyebrow": "Verfügbare Karten",
        "provider_title": "Verfügbare Karten entdecken.",
        "provider_copy": "Wähle Karten der verfügbaren Anbieter. Karten werden von der Originalquelle des jeweiligen Anbieters geladen.",
        "download_label": "Herunterladen",
        "faq_eyebrow": "Hast du Fragen?",
        "faq_questions": ["Welche Garmin-Uhren funktionieren mit Terento?", "Kann ich Drittanbieter-Karten von einem Mac ohne BaseCamp auf einer Garmin-Uhr installieren?", "Kann ich meine eigene .img-Karte hinzufügen?", "Kann ich Karten später aktualisieren?", "Was soll ich tun, wenn die Installation fehlschlägt?"],
        "final_cta_eyebrow": "Heute loslegen",
        "final_cta_title": "Bereit für eine einfachere Karteninstallation?",
        "final_cta_body": "Lade Terento herunter und verwalte Drittanbieter-Karten von deinem Mac aus.",
        "provider_list_label": "Kartenanbieter",
    },
    "fr": {
        "scope_href": "/fr/compatibility/",
        "hero_title": "Installez simplement des cartes sur les montres Garmin",
        "hero_lede": "Installez, mettez à jour et gérez des cartes tierces depuis une application macOS native — sans transferts manuels de fichiers.",
        "hero_compatibility": "Vérifier la compatibilité",
        "experience_label": "Comment ça marche",
        "experience_title": "Connecter → Installer → Terminé",
        "feature_tabs_label": "Fonctions cartographiques",
        "install_tab": "Installer des cartes",
        "manage_tab": "Gérer les cartes",
        "problem": "Installer des cartes tierces devrait être simple et rapide — sans logiciel supplémentaire, étapes de téléchargement séparées ni connaissances techniques.",
        "problem_secondary": "Terento réunit tout le parcours en trois étapes simples.",
        "scope": "Terento est conçu pour les montres Garmin compatibles avec les cartes. La compatibilité est confirmée pour chaque modèle et chaque variante à partir de résultats d’installation réels.",
        "compatibility_answer": "Consultez la <a href=\"/fr/compatibility/\" data-umami-event=\"compatibility-link-click\" data-umami-event-location=\"home-faq-compatibility\">page Compatibilité</a> pour voir les modèles et variantes Garmin confirmés par des installations réelles.",
        "install_step": "Choisissez des cartes dans le catalogue ou ajoutez votre propre carte .img compatible.",
        "install_showcase": "Choisissez des cartes dans le catalogue par région ou ajoutez votre propre carte .img compatible.",
        "done_label": "Terminé",
        "done_step": "Vos cartes sont installées et prêtes à être utilisées sur votre montre.",
        "manage_showcase": "Consultez les cartes installées, mettez-les à jour lorsqu’une version plus récente est disponible et supprimez les cartes tierces gérées par Terento. Les cartes Garmin d’origine restent protégées.",
        "basecamp_answer": "Oui. Terento est conçu pour rendre la gestion des cartes tierces sur macOS simple et rapide — du choix de la carte à son installation, sa mise à jour et sa gestion sur votre montre Garmin. <a href=\"/fr/guides/install-garmin-maps-mac/\" data-umami-event=\"guide-link-click\" data-umami-event-location=\"home-faq-basecamp\">Lisez le guide d’installation.</a>",
        "safety_answer": "Oui. Ajoutez une carte .img compatible depuis votre Mac et installez-la sur votre montre Garmin connectée.",
        "update_answer": "Oui. Terento vous indique lorsqu’une version plus récente est disponible et vous aide à mettre à jour les cartes tierces gérées par Terento.",
        "failure_answer": "Sur l’écran d’échec de l’installation, choisissez « Report issue ». Terento ouvre GitHub avec le rapport déjà rempli. Vérifiez-le avant de le publier : les issues GitHub sont publiques. Pour une aide par e-mail, indiquez le modèle de votre montre, la région de la carte et ce qui s’est passé.",
        "provider_eyebrow": "Cartes disponibles",
        "provider_title": "Découvrez les cartes disponibles.",
        "provider_copy": "Choisissez parmi les fournisseurs disponibles. Les cartes sont téléchargées depuis la source d’origine de chaque fournisseur.",
        "download_label": "Télécharger",
        "faq_eyebrow": "Vous avez des questions ?",
        "faq_questions": ["Quelles montres Garmin fonctionnent avec Terento ?", "Puis-je installer des cartes tierces sur une montre Garmin depuis un Mac sans BaseCamp ?", "Puis-je ajouter ma propre carte .img ?", "Puis-je mettre les cartes à jour plus tard ?", "Que dois-je faire si l’installation échoue ?"],
        "final_cta_eyebrow": "Commencez aujourd’hui",
        "final_cta_title": "Prêt pour une façon plus simple d’installer vos cartes ?",
        "final_cta_body": "Téléchargez Terento et gérez vos cartes tierces depuis votre Mac.",
        "provider_list_label": "Fournisseurs de cartes",
    },
    "pl": {
        "scope_href": "/pl/compatibility/",
        "hero_title": "Instaluj mapy na zegarkach Garmin — po prostu",
        "hero_lede": "Instaluj, aktualizuj i zarządzaj mapami innych firm z natywnej aplikacji macOS — bez ręcznego przesyłania plików.",
        "hero_compatibility": "Sprawdź kompatybilność",
        "experience_label": "Jak to działa",
        "experience_title": "Połącz → Zainstaluj → Gotowe",
        "feature_tabs_label": "Funkcje map",
        "install_tab": "Instaluj mapy",
        "manage_tab": "Zarządzaj mapami",
        "problem": "Instalowanie map innych firm powinno być proste i szybkie — bez dodatkowego oprogramowania, osobnych etapów pobierania ani wiedzy technicznej.",
        "problem_secondary": "Terento łączy cały proces w trzech prostych krokach.",
        "scope": "Terento jest przeznaczone dla zegarków Garmin z obsługą map. Kompatybilność każdego modelu i wariantu jest potwierdzana na podstawie rzeczywistych instalacji.",
        "compatibility_answer": "Na <a href=\"/pl/compatibility/\" data-umami-event=\"compatibility-link-click\" data-umami-event-location=\"home-faq-compatibility\">stronie kompatybilności</a> znajdziesz modele i warianty Garmin potwierdzone rzeczywistymi instalacjami.",
        "install_step": "Wybierz mapy z katalogu albo dodaj własną zgodną mapę .img.",
        "install_showcase": "Wybieraj mapy z katalogu według regionu albo dodaj własną zgodną mapę .img.",
        "done_label": "Gotowe",
        "done_step": "Twoje mapy są zainstalowane i gotowe do użycia na zegarku.",
        "manage_showcase": "Sprawdź, co jest zainstalowane, aktualizuj mapy, gdy dostępne są nowsze wydania, i usuwaj mapy innych firm zarządzane przez Terento. Oryginalne mapy Garmin pozostają chronione.",
        "basecamp_answer": "Tak. Terento powstało po to, by instalowanie i zarządzanie mapami innych firm na macOS było proste i szybkie — od wyboru mapy po instalację, aktualizację i zarządzanie nią na zegarku Garmin. <a href=\"/pl/guides/install-garmin-maps-mac/\" data-umami-event=\"guide-link-click\" data-umami-event-location=\"home-faq-basecamp\">Przeczytaj instrukcję instalacji.</a>",
        "safety_answer": "Tak. Dodaj zgodną mapę .img z Maca i zainstaluj ją na podłączonym zegarku Garmin.",
        "update_answer": "Tak. Terento pokazuje, gdy dostępne są nowsze wydania, i pomaga aktualizować mapy innych firm zarządzane przez Terento.",
        "failure_answer": "Na ekranie nieudanej instalacji wybierz „Report issue”. Terento otwiera GitHuba z już wypełnionym raportem. Sprawdź go przed publikacją: zgłoszenia na GitHubie są publiczne. Jeśli potrzebujesz pomocy e-mailem, podaj model zegarka, region mapy i opisz, co się stało.",
        "provider_eyebrow": "Dostępne mapy",
        "provider_title": "Poznaj dostępne mapy.",
        "provider_copy": "Wybieraj mapy od dostępnych dostawców. Mapy są pobierane z oryginalnego źródła każdego dostawcy.",
        "download_label": "Pobierz",
        "faq_eyebrow": "Masz pytania?",
        "faq_questions": ["Jakie zegarki Garmin działają z Terento?", "Czy mogę instalować mapy innych firm na zegarku Garmin z Maca bez BaseCamp?", "Czy mogę dodać własną mapę .img?", "Czy mogę później aktualizować mapy?", "Co zrobić, jeśli instalacja się nie powiedzie?"],
        "final_cta_eyebrow": "Zacznij już dziś",
        "final_cta_title": "Gotowy na prostszy sposób instalowania map?",
        "final_cta_body": "Pobierz Terento i zarządzaj mapami innych firm z Maca.",
        "provider_list_label": "Dostawcy map",
    },
    "cs": {
        "scope_href": "/cs/compatibility/",
        "hero_title": "Instalujte mapy do hodinek Garmin jednoduše",
        "hero_lede": "Instalujte, aktualizujte a spravujte mapy třetích stran z nativní aplikace pro macOS — bez ručních přenosů souborů.",
        "hero_compatibility": "Ověřit kompatibilitu",
        "experience_label": "Jak to funguje",
        "experience_title": "Připojit → Instalovat → Hotovo",
        "feature_tabs_label": "Funkce map",
        "install_tab": "Instalovat mapy",
        "manage_tab": "Spravovat mapy",
        "problem": "Instalace map třetích stran by měla být jednoduchá a rychlá — bez dalšího softwaru, samostatných kroků stahování a technických znalostí.",
        "problem_secondary": "Terento celý proces spojuje do tří jednoduchých kroků.",
        "scope": "Terento je určeno pro hodinky Garmin s podporou map. Kompatibilita každého modelu a varianty se potvrzuje pomocí skutečných výsledků instalace.",
        "compatibility_answer": "Na stránce <a href=\"/cs/compatibility/\" data-umami-event=\"compatibility-link-click\" data-umami-event-location=\"home-faq-compatibility\">Kompatibilita</a> najdete modely a varianty Garmin potvrzené skutečnými instalacemi.",
        "install_step": "Vybírejte mapy z katalogu podle oblasti nebo přidejte vlastní kompatibilní mapu .img.",
        "install_showcase": "Vybírejte mapy z katalogu podle oblasti nebo přidejte vlastní kompatibilní mapu .img.",
        "done_label": "Hotovo",
        "done_step": "Vaše mapy jsou nainstalované a připravené k použití v hodinkách.",
        "manage_showcase": "Prohlédněte si nainstalované mapy, aktualizujte je, když je k dispozici novější vydání, a odstraňte mapy třetích stran spravované aplikací Terento. Původní mapy Garmin zůstávají chráněné.",
        "basecamp_answer": "Ano. Terento je navrženo tak, aby správa map třetích stran v macOS byla jednoduchá a rychlá — od výběru mapy po instalaci, aktualizaci a správu v hodinkách Garmin. <a href=\"/cs/guides/install-garmin-maps-mac/\" data-umami-event=\"guide-link-click\" data-umami-event-location=\"home-faq-basecamp\">Přečtěte si instalační příručku.</a>",
        "safety_answer": "Ano. Přidejte kompatibilní mapu .img z Macu a nainstalujte ji do připojených hodinek Garmin.",
        "update_answer": "Ano. Terento ukáže, když jsou k dispozici novější vydání, a pomůže vám aktualizovat mapy třetích stran spravované aplikací Terento.",
        "failure_answer": "Na obrazovce neúspěšné instalace zvolte „Report issue“. Terento otevře GitHub s již vyplněnou zprávou. Před zveřejněním ji zkontrolujte: hlášení na GitHubu jsou veřejná. Pro pomoc e-mailem uveďte model hodinek, oblast mapy a popis problému.",
        "provider_eyebrow": "Dostupné mapy",
        "provider_title": "Prozkoumejte dostupné mapy.",
        "provider_copy": "Vyberte si mapy od dostupných poskytovatelů. Mapy se stahují z původního zdroje každého poskytovatele.",
        "download_label": "Stáhnout",
        "faq_eyebrow": "Máte otázky?",
        "faq_questions": ["Které hodinky Garmin fungují s Terento?", "Mohu instalovat mapy třetích stran do hodinek Garmin z Macu bez BaseCamp?", "Mohu přidat vlastní mapu .img?", "Mohu mapy aktualizovat později?", "Co mám dělat, když instalace selže?"],
        "final_cta_eyebrow": "Začněte ještě dnes",
        "final_cta_title": "Chcete jednodušší způsob instalace map?",
        "final_cta_body": "Stáhněte si Terento a spravujte mapy třetích stran z Macu.",
        "provider_list_label": "Poskytovatelé map",
    },
    "it": {
        "scope_href": "/it/compatibility/",
        "hero_title": "Installa le mappe sugli smartwatch Garmin, in modo semplice",
        "hero_lede": "Installa, aggiorna e gestisci mappe di terze parti da un’app macOS nativa — senza trasferimenti manuali di file.",
        "hero_compatibility": "Verifica la compatibilità",
        "experience_label": "Come funziona",
        "experience_title": "Connetti → Installa → Fatto",
        "feature_tabs_label": "Funzioni delle mappe",
        "install_tab": "Installa mappe",
        "manage_tab": "Gestisci mappe",
        "problem": "Installare mappe di terze parti dovrebbe essere semplice e veloce — senza software aggiuntivo, passaggi di download separati o competenze tecniche.",
        "problem_secondary": "Terento riunisce l’intero processo in tre semplici passaggi.",
        "scope": "Terento è progettato per gli smartwatch Garmin con supporto alle mappe. La compatibilità di ogni modello e variante viene confermata con risultati di installazione reali.",
        "compatibility_answer": "Consulta la pagina <a href=\"/it/compatibility/\" data-umami-event=\"compatibility-link-click\" data-umami-event-location=\"home-faq-compatibility\">Compatibilità</a> per i modelli e le varianti Garmin confermati da installazioni reali.",
        "install_step": "Scegli le mappe dal catalogo oppure aggiungi la tua mappa .img compatibile.",
        "install_showcase": "Scegli le mappe dal catalogo per regione oppure aggiungi la tua mappa .img compatibile.",
        "done_label": "Fatto",
        "done_step": "Le tue mappe sono installate e pronte per essere usate sullo smartwatch.",
        "manage_showcase": "Visualizza le mappe installate, aggiornatele quando è disponibile una versione più recente e rimuovi le mappe di terze parti gestite da Terento. Le mappe Garmin originali restano protette.",
        "basecamp_answer": "Sì. Terento è progettato per rendere semplice e veloce la gestione delle mappe di terze parti su macOS — dalla scelta della mappa all’installazione, all’aggiornamento e alla gestione sul tuo smartwatch Garmin. <a href=\"/it/guides/install-garmin-maps-mac/\" data-umami-event=\"guide-link-click\" data-umami-event-location=\"home-faq-basecamp\">Leggi la guida all’installazione.</a>",
        "safety_answer": "Sì. Aggiungi una mappa .img compatibile dal tuo Mac e installala sul tuo smartwatch Garmin collegato.",
        "update_answer": "Sì. Terento mostra quando sono disponibili versioni più recenti e ti aiuta ad aggiornare le mappe di terze parti gestite da Terento.",
        "failure_answer": "Nella schermata di installazione non riuscita, scegli “Report issue”. Terento apre GitHub con il rapporto già compilato. Controllalo prima di pubblicarlo: le issue su GitHub sono pubbliche. Per assistenza via e-mail, indica il modello dell’orologio, la regione della mappa e cosa è successo.",
        "provider_eyebrow": "Mappe disponibili",
        "provider_title": "Scopri le mappe disponibili.",
        "provider_copy": "Scegli mappe dei provider disponibili. Le mappe vengono scaricate dalla fonte originale di ciascun provider.",
        "download_label": "Scarica",
        "faq_eyebrow": "Hai domande?",
        "faq_questions": ["Quali smartwatch Garmin funzionano con Terento?", "Posso installare mappe di terze parti su uno smartwatch Garmin da un Mac senza BaseCamp?", "Posso aggiungere la mia mappa .img?", "Posso aggiornare le mappe in un secondo momento?", "Cosa devo fare se l’installazione non riesce?"],
        "final_cta_eyebrow": "Inizia oggi",
        "final_cta_title": "Pronto per un modo più semplice di installare le mappe?",
        "final_cta_body": "Scarica Terento e gestisci le mappe di terze parti dal tuo Mac.",
        "provider_list_label": "Provider di mappe",
    },
}

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
    if faq is None or len(faq.get("mainEntity", [])) not in (5, 10):
        raise ValueError(f"{path}: expected five or ten FAQ schema entries")
    if len(faq["mainEntity"]) == 10:
        faq["mainEntity"] = [faq["mainEntity"][index] for index in FAQ_KEEP]
    answer_keys = ("compatibility_answer", "basecamp_answer", "safety_answer", "update_answer", "failure_answer")
    for index, key in enumerate(answer_keys):
        faq["mainEntity"][index]["name"] = copy["faq_questions"][index]
        faq["mainEntity"][index]["acceptedAnswer"]["text"] = re.sub(r"<[^>]+>", "", copy[key])
    serialized = json.dumps(data, ensure_ascii=False, indent=2)
    indented = "\n".join("      " + line for line in serialized.splitlines())
    replacement = "\n" + indented + "\n    "
    source = source[: match.start(2)] + replacement + source[match.end(2) :]
    return source


def normalize_hero_actions(source: str, path: Path, copy: dict[str, str]) -> str:
    """Keep the Hero Download CTA primary and add one compatibility route."""
    source = re.sub(
        r'<div class="hero-actions">\s*(<a class="download-action hero-download-action"[^>]*>[\s\S]*?</a>)\s*'
        r'<a class="text-link hero-compatibility-link"[^>]*>[\s\S]*?</a>\s*</div>',
        r'\1',
        source,
        count=1,
    )
    compatibility_link = (
        f'<a class="text-link hero-compatibility-link" href="{copy["scope_href"]}" '
        'data-umami-event="compatibility-link-click" '
        'data-umami-event-location="home-hero">'
        f'{copy["hero_compatibility"]} <span aria-hidden="true">→</span></a>'
    )
    source, inserted = re.subn(
        r'(<a class="download-action hero-download-action" href="[^"]+"[^>]*>[\s\S]*?</a>)',
        lambda match: f'<div class="hero-actions">{match.group(1)}{compatibility_link}</div>',
        source,
        count=1,
    )
    if inserted != 1:
        raise ValueError(f"{path}: Hero Download CTA not found for compatibility link")
    return source


def normalize_hero_copy(source: str, path: Path, copy: dict[str, str]) -> str:
    """Keep the Home Hero focused on the installation outcome."""
    source, replaced_h1 = re.subn(
        r'(<h1 id="hero-title">)[^<]*(</h1>)',
        rf'\g<1>{copy["hero_title"]}\g<2>',
        source,
        count=1,
    )
    if replaced_h1 != 1:
        raise ValueError(f"{path}: Home Hero H1 not found")
    source, replaced_lede = re.subn(
        r'(<p class="hero-lede">)[^<]*(</p>)',
        rf'\g<1>{copy["hero_lede"]}\g<2>',
        source,
        count=1,
    )
    if replaced_lede != 1:
        raise ValueError(f"{path}: Home Hero lede not found")
    source = re.sub(r'\s*<p class="hero-requirement">[^<]*</p>', "", source, count=1)
    source = re.sub(r'\s*<p class="hero-status">[^<]*</p>', "", source, count=1)
    return source


def wrap_product_showcases(source: str) -> str:
    """Keep the two Home product stories visually contained and balanced."""
    pattern = re.compile(
        r'<section class="product-showcase product-showcase--muted(?: product-showcase--reverse)?" '
        r'aria-labelledby="(?:install|manage)-maps-title">[\s\S]*?</section>'
    )

    def wrap(match: re.Match[str]) -> str:
        block = match.group(0)
        if 'class="shell product-showcase-panel"' in block:
            return block
        block = block.replace(
            '<div class="shell product-showcase-grid">',
            '<div class="shell product-showcase-panel"><div class="product-showcase-grid">',
            1,
        )
        section_start = block.rfind("</section>")
        last_div_end = block.rfind("</div>", 0, section_start) + len("</div>")
        if last_div_end < len("</div>"):
            raise ValueError("Home product showcase closing container not found")
        return block[:last_div_end] + "</div>" + block[last_div_end:]

    return pattern.sub(wrap, source)


def wrap_map_feature_tabs(source: str, copy: dict[str, str], path: Path) -> str:
    """Present the two product stories as one accessible, switchable feature block."""
    if 'class="map-feature-section"' in source:
        return source
    pattern = re.compile(
        r'(?P<install><section class="product-showcase product-showcase--muted" '
        r'aria-labelledby="install-maps-title">[\s\S]*?</section>)\s*'
        r'(?P<manage><section class="product-showcase product-showcase--muted product-showcase--reverse" '
        r'aria-labelledby="manage-maps-title">[\s\S]*?</section>)'
    )
    match = pattern.search(source)
    if not match:
        raise ValueError(f"{path}: Home map showcase sections not found")

    def panel(section: str, panel_id: str, tab_id: str) -> str:
        section = re.sub(
            r'\s*<p class="eyebrow showcase-number" aria-hidden="true">[^<]+</p>',
            "",
            section,
            count=1,
        )
        return (
            f'<div class="map-feature-panel" id="{panel_id}" role="tabpanel" '
            f'tabindex="0" aria-labelledby="{tab_id}">\n{section}\n        </div>'
        )

    install_panel = panel(match.group("install"), "install-maps-panel", "install-maps-tab")
    manage_panel = panel(match.group("manage"), "manage-maps-panel", "manage-maps-tab")
    replacement = f'''<section class="map-feature-section" aria-label="{copy["feature_tabs_label"]}">
        <div class="shell">
          <div class="map-feature-tabs" data-map-feature-tabs role="tablist" aria-label="{copy["feature_tabs_label"]}">
            <button class="map-feature-tab" type="button" role="tab" id="install-maps-tab" aria-controls="install-maps-panel" aria-selected="true">{copy["install_tab"]}</button>
            <button class="map-feature-tab" type="button" role="tab" id="manage-maps-tab" aria-controls="manage-maps-panel" aria-selected="false">{copy["manage_tab"]}</button>
          </div>
        </div>
        <div class="map-feature-panels">
          {install_panel}
          {manage_panel}
        </div>
      </section>'''
    return source[: match.start()] + replacement + source[match.end() :]



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

def provider_cards_markup(locale: str, copy: dict[str, str]) -> str:
    cards = []
    for provider_id in ("freizeitkarte", "opentopomap", "maprando", "bbbike", "bbbike-ontrail"):
        provider = PROVIDER_CARD_COPY[locale][provider_id]
        fallback_count = {"freizeitkarte": "63", "opentopomap": "177"}.get(provider_id)
        count_markup = provider["count_template"].replace("{count}", fallback_count) if fallback_count else ""
        count_hidden = "" if fallback_count else " hidden"
        benefits = "".join(f"<li>{html.escape(benefit)}</li>" for benefit in provider["benefits"])
        addon = ""
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


def workflow_title_markup(title: str) -> str:
    parts = [html.escape(part.strip()) for part in title.split("→")]
    return ' <span class="workflow-title-arrow" aria-hidden="true">→</span><span class="workflow-title-bullet" aria-hidden="true">•</span> '.join(parts)


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
    answer_keys = ("compatibility_answer", "basecamp_answer", "safety_answer", "update_answer", "failure_answer")
    rewritten_entries = []
    for index, (entry, key) in enumerate(zip(entries, answer_keys)):
        rewritten = re.sub(
            r'(<summary>)[\s\S]*?(</summary>)',
            rf'\g<1>{copy["faq_questions"][index]}\g<2>',
            entry.group(0),
            count=1,
        )
        rewritten_entries.append(re.sub(r'<p>[\s\S]*?</p>', f'<p>{copy[key]}</p>', rewritten, count=1))
    for entry, rewritten in reversed(list(zip(entries, rewritten_entries))):
        faq_body = faq_body[: entry.start()] + rewritten + faq_body[entry.end() :]
    email_label = {"en":"Email support","de":"Support per E-Mail","fr":"Contacter le support","pl":"Napisz do pomocy","cs":"Napsat podpoře","it":"Scrivi all’assistenza"}[locale]
    faq_body = re.sub(r'(<a\b[^>]*href="mailto:[^"]*"[^>]*>)[^<]*', lambda match: match[1] + email_label + " ", faq_body)
    faq_body = faq_body.replace('href="https://github.com/VooZ2/terento/issues"', 'href="https://github.com/VooZ2/terento/issues/new/choose"')
    source = source[: faq_match.start(2)] + faq_body + source[faq_match.end(2) :]
    source = source.replace(f'href="{EMAIL_URL}"', f'href="{EMAIL_URL_HTML}"')
    source = re.sub(
        r'(<section class="faq section"[^>]*>[\s\S]*?<div class="section-heading">\s*<p class="eyebrow">)[^<]*(</p>)',
        rf'\g<1>{copy["faq_eyebrow"]}\g<2>',
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
        r'(<div class="problem-statement">\s*<p>[\s\S]*?</p>\s*<p>)[\s\S]*?(</p>)',
        rf'\g<1>{copy["problem_secondary"]}\g<2>',
        source,
        count=1,
    )
    experience_title_markup = workflow_title_markup(copy["experience_title"])
    source, experience_heading_count = re.subn(
        r'(<div class="section-heading">\s*)'
        r'(?:<p class="eyebrow"[^>]*>[^<]*</p>\s*)?'
        r'(<h2 id="experience-title">)[\s\S]*?(</h2>)',
        rf'\g<1><p class="eyebrow" id="experience-label">{copy["experience_label"]}</p>'
        f'\g<2>{experience_title_markup}\g<3>',
        source,
        count=1,
    )
    if experience_heading_count != 1:
        raise ValueError(f"{path}: How it works heading not found")
    source = re.sub(
        r'(<section class="hero"[\s\S]*?)<a class="text-link" (href="[^"]*download/">[\s\S]*?</a>)',
        r'\1<a class="download-action hero-download-action" \2',
        source,
        count=1,
    )
    source = re.sub(
        r'(<a class="download-action hero-download-action"[^>]*>[\s\S]*?<span aria-hidden="true">)↘(</span></a>)',
        r'\1→\2',
        source,
        count=1,
    )
    hero_image_alts = {
        "en": "Terento showing community map installation progress on macOS",
        "de": "Terento zeigt den Installationsfortschritt von Community-Karten unter macOS",
        "fr": "Terento affiche la progression de l’installation de cartes communautaires sur macOS",
        "pl": "Terento pokazuje postęp instalacji map społecznościowych w macOS",
        "cs": "Terento zobrazuje průběh instalace komunitních map v macOS",
        "it": "Terento mostra l’avanzamento dell’installazione di mappe della comunità su macOS",
    }
    def installing_hero(match):
        hero = match.group(0).replace("your-garmin-", "installing-maps-")
        return re.sub(r'(<img\b[^>]* alt=")[^"]*(")',
                      lambda image: image.group(1) + hero_image_alts[locale] + image.group(2), hero)

    source, hero_count = re.subn(r'<figure class="app-shot app-shot--hero">[\s\S]*?</figure>',
                                 installing_hero, source, count=1)
    if hero_count != 1:
        raise ValueError(f"{path}: expected one Home hero screenshot")
    source = normalize_hero_copy(source, path, copy)
    source = normalize_hero_actions(source, path, copy)
    source = re.sub(
        r'(<section class="experience section"[\s\S]*?<li class="step">[\s\S]*?<li class="step">[\s\S]*?<p>)[\s\S]*?(</p>)',
        rf'\g<1>{copy["install_step"]}\g<2>',
        source,
        count=1,
    )
    source = re.sub(
        r'(<section class="experience section"[\s\S]*?<li class="step">[\s\S]*?<li class="step">[\s\S]*?<li class="step">[\s\S]*?<h3>)[^<]*(</h3>)',
        rf'\g<1>{copy["done_label"]}\g<2>',
        source,
        count=1,
    )
    source = re.sub(
        r'(<section class="experience section"[\s\S]*?<li class="step">[\s\S]*?<li class="step">[\s\S]*?<li class="step">[\s\S]*?<p>)[\s\S]*?(</p>)',
        rf'\g<1>{copy["done_step"]}\g<2>',
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
        r'(<h2 id="manage-maps-title">[\s\S]*?</h2>\s*<p>)[\s\S]*?(</p>)',
        rf'\g<1>{copy["manage_showcase"]}\g<2>',
        source,
        count=1,
    )
    source = re.sub(
        r'(<section class="final-cta"[\s\S]*?<p class="eyebrow">)[^<]*(</p>)',
        rf'\g<1>{copy["final_cta_eyebrow"]}\g<2>',
        source,
        count=1,
    )
    source = re.sub(
        r'(<section class="final-cta"[\s\S]*?<h2 id="final-cta-title">)[^<]*(</h2>)',
        rf'\g<1>{copy["final_cta_title"]}\g<2>',
        source,
        count=1,
    )
    source = re.sub(
        r'(<section class="final-cta"[\s\S]*?<h2 id="final-cta-title">[\s\S]*?</h2>\s*<p>)[^<]*(</p>)',
        rf'\g<1>{copy["final_cta_body"]}\g<2>',
        source,
        count=1,
    )
    source = re.sub(
        r'(<a class="download-action hero-download-action"[^>]*>)[\s\S]*?(<span aria-hidden="true">→</span></a>)',
        rf'\g<1>{copy["download_label"]} \g<2>',
        source,
        count=1,
    )
    source = re.sub(
        r'(<section class="final-cta"[\s\S]*?<a class="download-action"[^>]*>)[^<]*(</a>)',
        rf'\g<1>{copy["download_label"]}\g<2>',
        source,
        count=1,
    )
    def mark_final_cta(match: re.Match[str]) -> str:
        tag = match.group(0)
        if 'data-umami-event="' in tag:
            tag = re.sub(r'data-umami-event="[^"]*"', 'data-umami-event="download-cta-click"', tag, count=1)
        else:
            tag = tag[:-1] + ' data-umami-event="download-cta-click">'
        if 'data-umami-event-location="' in tag:
            tag = re.sub(r'data-umami-event-location="[^"]*"', 'data-umami-event-location="home-final-cta"', tag, count=1)
        else:
            tag = tag[:-1] + ' data-umami-event-location="home-final-cta">'
        return tag

    source = re.sub(
        r'<section class="final-cta"[\s\S]*?<a class="download-action"[^>]*>',
        mark_final_cta,
        source,
        count=1,
    )
    source = re.sub(
        r'<p class="eyebrow">[^<]*</p>(\s*<h2 id="install-maps-title">)',
        r'<p class="eyebrow showcase-number" aria-hidden="true">01</p>\1',
        source,
        count=1,
    )
    source = re.sub(
        r'<p class="eyebrow">[^<]*</p>(\s*<h2 id="manage-maps-title">)',
        r'<p class="eyebrow showcase-number" aria-hidden="true">02</p>\1',
        source,
        count=1,
    )
    source = source.replace(
        '<section class="product-showcase product-showcase--muted" aria-labelledby="manage-maps-title">',
        '<section class="product-showcase product-showcase--muted product-showcase--reverse" aria-labelledby="manage-maps-title">',
        1,
    )
    source = wrap_product_showcases(source)
    source = wrap_map_feature_tabs(source, copy, path)
    source, removed = re.subn(
        r'\s*<section class="scope-section" id="scope"[\s\S]*?</section>',
        "",
        source,
        count=1,
    )
    if removed != 1 and 'class="scope-section"' in source:
        raise ValueError(f"{path}: failed to remove Home Beta scope section")
    source = re.sub(
        r'\s*<section class="provider-section section" id="providers"[\s\S]*?</section>',
        "",
        source,
    )
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
    if 'src="/home-features.js?' not in source:
        source = re.sub(
            r'(<script defer src="/provider-list\.js\?v=[^"\s]+"></script>)',
            rf'\1\n    <script defer src="/home-features.js?v={FEATURE_SCRIPT_VERSION}"></script>',
            source,
            count=1,
        )
    source = re.sub(
        r'(/provider-list\.js\?v=)[^"\s]+',
        rf'\g<1>{PROVIDER_SCRIPT_VERSION}',
        source,
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
