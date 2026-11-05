#!/usr/bin/env python3
"""Render the deterministic public compatibility snapshot into six locale pages."""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = runpy.run_path(str(ROOT / "scripts/page_schema.py"))
SNAPSHOT_PATH = ROOT / "site/compatibility/public-models.snapshot.json"
LOCALES = ("en", "de", "fr", "pl", "cs", "it")
# The compatibility script cache versions have one owner: normalize-public-shell.py
# runs after this generator in the full site build, while the scheduled snapshot
# refresh runs only this generator. Both must write the same query strings.
SHELL = runpy.run_path(str(ROOT / "scripts/normalize-public-shell.py"))
ASSET_VERSION = SHELL["COMPATIBILITY_VERSION"]
LOCALES_ASSET_VERSION = SHELL["COMPATIBILITY_LOCALES_VERSION"]
FALLBACK_IMAGE_URL = "/assets/generic-garmin-watch.png?v=20260826-1"


COPY = {
    "en": {
        "title": "Garmin watch and Edge compatibility", "meta_title": "Garmin Watch & Edge Compatibility: Successful Installs — Terento", "meta_description": "Terento is designed for Garmin smartwatches and newer Edge bike computers with map support. See exact models and variants with successful map installs.", "hero": "Terento works with Garmin watches and newer Garmin Edge bike computers with map support. Below are the exact models where people have already installed a map with Terento. The list grows as more installs are shared.", "missing": "Not seeing your model? That doesn’t mean it won’t work. It may be that no one has shared a successful install from it yet.", "model_one": "model with successful installs", "model_many": "models with successful installs", "successes": "successful installs", "latest": "Latest successful install", "how_summary": "How this list works", "how_text": "This list is built from real successful Terento installations shared by users. It shows only exact Garmin models and variants with at least one successful third-party map installation. It is not a complete list of every Garmin watch or Edge Terento can work with.", "certification": "Installation results are shared with Terento by users. They are not Garmin certification.", "providers": "The current version includes every map provider in the catalog. This product information is separate from the device results shown here.", "search": "Search models", "filter_successful": "Filter by successful installs", "all_successful": "All successful installs", "one_two": "1–2 successful installs", "three_four": "3–4 successful installs", "five_plus": "5+ successful installs", "filter_family": "Filter by family", "all_families": "All families", "sort": "Sort models", "most_successful": "Most successful installs", "name": "A–Z", "clear": "Clear filters", "model_one_result": "model", "model_many_result": "models", "of": "of", "no_match": "No models match these filters.", "error": "Compatibility results are temporarily unavailable. Please try again later.", "card_latest": "Latest successful install", "card_smartwatch": "Smartwatch", "noscript": "Showing the latest published installation results. Enable JavaScript for live updates and filtering.", "refresh_stale": "Could not refresh. Showing the latest published installation results; counts may be outdated.", "refresh_unavailable": "Could not load published installation results.", "last_loaded": "Last loaded", "retry": "Retry", "community_eyebrow": "Community results", "community_heading": "Don’t see your Garmin here?", "community_body": "If your Garmin watch or Edge bike computer supports maps, you can still try Terento. Each successful install you share adds your model to this list.", "guide_link": "First time? Read the Mac install guide", "download": "Download", "date_locale": "en-US",
    },
    "de": {
        "title": "Kompatibilität von Garmin-Uhren und Edge", "meta_title": "Garmin-Uhren & Edge: erfolgreiche Installationen — Terento", "meta_description": "Terento ist für Garmin-Smartwatches und neuere Edge-Radcomputer mit Kartenunterstützung gemacht. Hier stehen Modelle mit erfolgreichen Karteninstallationen.", "hero": "Terento funktioniert mit Garmin-Uhren und neueren Garmin Edge Fahrradcomputern mit Kartenunterstützung. Unten stehen die genauen Modelle, auf denen schon jemand eine Karte mit Terento installiert hat. Die Liste wächst mit jeder geteilten Installation.", "missing": "Wenn dein Modell fehlt, heißt das nicht, dass es nicht funktioniert. Vielleicht hat noch niemand eine erfolgreiche Installation damit geteilt.", "model_one": "Modell mit erfolgreichen Installationen", "model_many": "Modelle mit erfolgreichen Installationen", "successes": "erfolgreiche Installationen", "latest": "Letzte erfolgreiche Installation", "how_summary": "So funktioniert diese Liste", "how_text": "Diese Liste basiert auf echten erfolgreichen Terento-Installationen, die Nutzer geteilt haben. Sie zeigt nur genaue Garmin-Modelle und -Varianten mit mindestens einer erfolgreichen Installation einer Drittanbieter-Karte. Sie ist keine vollständige Liste aller Garmin-Uhren und Edge-Geräte, mit denen Terento funktionieren kann.", "certification": "Die Installationsergebnisse wurden von Nutzern mit Terento geteilt; sie sind keine Garmin-Zertifizierung.", "providers": "Die aktuelle Version umfasst alle Kartenanbieter im Katalog. Diese Produktinformation ist von den hier gezeigten Geräteergebnissen getrennt.", "search": "Modelle suchen", "filter_successful": "Nach erfolgreichen Installationen filtern", "all_successful": "Alle erfolgreichen Installationen", "one_two": "1–2 erfolgreiche Installationen", "three_four": "3–4 erfolgreiche Installationen", "five_plus": "5+ erfolgreiche Installationen", "filter_family": "Nach Familie filtern", "all_families": "Alle Familien", "sort": "Modelle sortieren", "most_successful": "Meiste erfolgreiche Installationen", "name": "A–Z", "clear": "Filter zurücksetzen", "model_one_result": "Modell", "model_many_result": "Modelle", "of": "von", "no_match": "Keine Modelle passen zu diesen Filtern.", "error": "Die Kompatibilitätsergebnisse sind vorübergehend nicht verfügbar. Bitte versuche es später erneut.", "card_latest": "Letzte erfolgreiche Installation", "card_smartwatch": "Smartwatch", "noscript": "Die neuesten veröffentlichten Installationsergebnisse werden angezeigt. Aktiviere JavaScript für Live-Aktualisierungen und Filter.", "refresh_stale": "Aktualisierung fehlgeschlagen. Die neuesten veröffentlichten Installationsergebnisse werden angezeigt; Zahlen können veraltet sein.", "refresh_unavailable": "Veröffentlichte Installationsergebnisse konnten nicht geladen werden.", "last_loaded": "Zuletzt geladen", "retry": "Erneut versuchen", "community_eyebrow": "Ergebnisse aus der Community", "community_heading": "Dein Garmin ist nicht dabei?", "community_body": "Wenn deine Garmin-Uhr oder dein Edge Fahrradcomputer Karten unterstützt, kannst du Terento trotzdem ausprobieren. Jede geteilte erfolgreiche Installation bringt dein Modell auf diese Liste.", "guide_link": "Zum ersten Mal? Lies die Mac-Anleitung", "download": "Herunterladen", "date_locale": "de-DE",
    },
    "fr": {
        "title": "Compatibilité des montres et compteurs Edge Garmin", "meta_title": "Montres Garmin et Edge : installations réussies — Terento", "meta_description": "Terento est conçu pour les montres Garmin et les compteurs vélo Edge récents avec cartes. Voici les modèles et variantes exacts avec des installations réussies.", "hero": "Terento fonctionne avec les montres Garmin et les compteurs vélo Garmin Edge récents compatibles cartes. Voici les modèles exacts sur lesquels quelqu’un a déjà installé une carte avec Terento. La liste s’allonge à chaque installation partagée.", "missing": "L’absence de votre modèle ne veut pas dire qu’il ne fonctionne pas. Personne n’a peut-être encore partagé d’installation réussie avec ce modèle.", "model_one": "modèle avec des installations réussies", "model_many": "modèles avec des installations réussies", "successes": "installations réussies", "latest": "Dernière installation réussie", "how_summary": "Comment fonctionne cette liste", "how_text": "Cette liste repose sur de vraies installations Terento réussies partagées par les utilisateurs. Elle affiche uniquement les modèles et variantes Garmin exacts ayant au moins une installation réussie de carte tierce. Ce n’est pas une liste exhaustive des montres et compteurs Edge Garmin avec lesquels Terento peut fonctionner.", "certification": "Les résultats d’installation sont partagés avec Terento par les utilisateurs ; ils ne constituent pas une certification Garmin.", "providers": "La version actuelle comprend tous les fournisseurs de cartes du catalogue. Cette information produit est distincte des résultats d’appareils présentés ici.", "search": "Rechercher un modèle", "filter_successful": "Filtrer par installations réussies", "all_successful": "Toutes les installations réussies", "one_two": "1–2 installations réussies", "three_four": "3–4 installations réussies", "five_plus": "5+ installations réussies", "filter_family": "Filtrer par famille", "all_families": "Toutes les familles", "sort": "Trier les modèles", "most_successful": "Plus d’installations réussies", "name": "A–Z", "clear": "Effacer les filtres", "model_one_result": "modèle", "model_many_result": "modèles", "of": "sur", "no_match": "Aucun modèle ne correspond à ces filtres.", "error": "Les résultats de compatibilité sont temporairement indisponibles. Réessayez plus tard.", "card_latest": "Dernière installation réussie", "card_smartwatch": "Montre connectée", "noscript": "Les derniers résultats d’installation publiés sont affichés. Activez JavaScript pour les mises à jour en direct et les filtres.", "refresh_stale": "Actualisation impossible. Les derniers résultats d’installation publiés sont affichés ; les chiffres peuvent être obsolètes.", "refresh_unavailable": "Impossible de charger les résultats d’installation publiés.", "last_loaded": "Dernier chargement", "retry": "Réessayer", "community_eyebrow": "Résultats de la communauté", "community_heading": "Votre Garmin n’apparaît pas ?", "community_body": "Si votre montre Garmin ou votre compteur Edge prend en charge les cartes, vous pouvez quand même essayer Terento. Chaque installation réussie partagée ajoute votre modèle à cette liste.", "guide_link": "Première fois ? Lisez le guide Mac", "download": "Télécharger", "date_locale": "fr-FR",
    },
    "pl": {
        "title": "Zgodność zegarków Garmin i liczników Edge", "meta_title": "Zegarki Garmin i liczniki Edge: udane instalacje — Terento", "meta_description": "Terento jest przeznaczone dla zegarków Garmin i nowszych liczników rowerowych Edge obsługujących mapy. Zobacz modele i warianty z udanymi instalacjami map.", "hero": "Terento działa z zegarkami Garmin i nowszymi licznikami rowerowymi Garmin Edge obsługującymi mapy. Poniżej są dokładne modele, na których ktoś już zainstalował mapę przez Terento. Lista rośnie z każdą udostępnioną instalacją.", "missing": "Brak Twojego modelu nie oznacza, że nie zadziała. Być może nikt jeszcze nie udostępnił z niego udanej instalacji.", "model_one": "model z udanymi instalacjami", "model_many": "modele z udanymi instalacjami", "successes": "udane instalacje", "latest": "Ostatnia udana instalacja", "how_summary": "Jak działa ta lista", "how_text": "Lista powstaje na podstawie rzeczywistych, udanych instalacji Terento udostępnianych przez użytkowników. Pokazuje tylko dokładne modele i warianty Garmin z co najmniej jedną udaną instalacją mapy innej firmy. Nie jest to pełna lista wszystkich zegarków Garmin i liczników Edge, z którymi Terento może działać.", "certification": "Wyniki instalacji są udostępniane Terento przez użytkowników; nie są certyfikacją Garmin.", "providers": "Aktualna wersja obejmuje wszystkich dostawców map z katalogu. Ta informacja o produkcie jest oddzielona od pokazanych tutaj wyników dla urządzeń.", "search": "Szukaj modeli", "filter_successful": "Filtruj według udanych instalacji", "all_successful": "Wszystkie udane instalacje", "one_two": "1–2 udane instalacje", "three_four": "3–4 udane instalacje", "five_plus": "5+ udanych instalacji", "filter_family": "Filtruj według rodziny", "all_families": "Wszystkie rodziny", "sort": "Sortuj modele", "most_successful": "Najwięcej udanych instalacji", "name": "A–Z", "clear": "Wyczyść filtry", "model_one_result": "model", "model_many_result": "modeli", "of": "z", "no_match": "Żaden model nie pasuje do tych filtrów.", "error": "Wyniki kompatybilności są chwilowo niedostępne. Spróbuj ponownie później.", "card_latest": "Ostatnia udana instalacja", "card_smartwatch": "Zegarek", "noscript": "Wyświetlamy najnowsze opublikowane wyniki instalacji. Włącz JavaScript, aby korzystać z aktualizacji na żywo i filtrowania.", "refresh_stale": "Nie udało się odświeżyć danych. Wyświetlamy najnowsze opublikowane wyniki instalacji; liczby mogą być nieaktualne.", "refresh_unavailable": "Nie udało się pobrać opublikowanych wyników instalacji.", "last_loaded": "Ostatnio pobrano", "retry": "Spróbuj ponownie", "community_eyebrow": "Wyniki społeczności", "community_heading": "Nie widzisz swojego Garmina?", "community_body": "Jeśli Twój zegarek Garmin lub licznik Edge obsługuje mapy, i tak możesz wypróbować Terento. Każda udostępniona udana instalacja dodaje Twój model do tej listy.", "guide_link": "Pierwszy raz? Przeczytaj instrukcję na Maca", "download": "Pobierz", "date_locale": "pl-PL",
    },
    "cs": {
        "title": "Kompatibilita hodinek a cyklopočítačů Garmin Edge", "meta_title": "Hodinky Garmin a Edge: úspěšné instalace map — Terento", "meta_description": "Terento je navrženo pro hodinky Garmin a novější cyklopočítače Edge s podporou map. Podívejte se na modely a varianty s úspěšnými instalacemi map.", "hero": "Terento funguje s hodinkami Garmin a novějšími cyklopočítači Garmin Edge s podporou map. Níže jsou přesné modely, do kterých už někdo nainstaloval mapu přes Terento. Seznam roste s každou sdílenou instalací.", "missing": "Pokud zde svůj model nevidíte, neznamená to, že nebude fungovat. Možná z něj zatím nikdo nesdílel úspěšnou instalaci.", "model_one": "model s úspěšnými instalacemi", "model_many": "modely s úspěšnými instalacemi", "successes": "úspěšných instalací", "latest": "Poslední úspěšná instalace", "how_summary": "Jak tento seznam funguje", "how_text": "Tento seznam vychází ze skutečných úspěšných instalací Terento sdílených uživateli. Zobrazuje pouze konkrétní modely a varianty Garmin s alespoň jednou úspěšnou instalací mapy třetí strany. Nejde o úplný seznam všech hodinek a cyklopočítačů Garmin Edge, se kterými může Terento fungovat.", "certification": "Výsledky instalací sdílejí s Terento uživatelé; nejde o certifikaci Garmin.", "providers": "Aktuální verze zahrnuje všechny poskytovatele map v katalogu. Tato informace o produktu je oddělená od výsledků zařízení uvedených zde.", "search": "Hledat modely", "filter_successful": "Filtrovat podle úspěšných instalací", "all_successful": "Všechny úspěšné instalace", "one_two": "1–2 úspěšné instalace", "three_four": "3–4 úspěšné instalace", "five_plus": "5+ úspěšných instalací", "filter_family": "Filtrovat podle řady", "all_families": "Všechny řady", "sort": "Řadit modely", "most_successful": "Nejvíce úspěšných instalací", "name": "A–Z", "clear": "Vymazat filtry", "model_one_result": "model", "model_many_result": "modelů", "of": "z", "no_match": "Žádný model neodpovídá těmto filtrům.", "error": "Výsledky kompatibility jsou dočasně nedostupné. Zkuste to později znovu.", "card_latest": "Poslední úspěšná instalace", "card_smartwatch": "Hodinky", "noscript": "Zobrazují se nejnovější zveřejněné výsledky instalací. Pro živé aktualizace a filtrování zapněte JavaScript.", "refresh_stale": "Aktualizace se nezdařila. Zobrazují se nejnovější zveřejněné výsledky instalací; počty mohou být zastaralé.", "refresh_unavailable": "Zveřejněné výsledky instalací se nepodařilo načíst.", "last_loaded": "Naposledy načteno", "retry": "Zkusit znovu", "community_eyebrow": "Výsledky komunity", "community_heading": "Nevidíte zde svůj Garmin?", "community_body": "Pokud vaše hodinky Garmin nebo cyklopočítač Edge podporují mapy, můžete Terento i tak vyzkoušet. Každá sdílená úspěšná instalace přidá váš model do tohoto seznamu.", "guide_link": "Poprvé? Přečtěte si průvodce pro Mac", "download": "Stáhnout", "date_locale": "cs-CZ",
    },
    "it": {
        "title": "Compatibilità smartwatch Garmin ed Edge", "meta_title": "Smartwatch Garmin ed Edge: installazioni riuscite — Terento", "meta_description": "Terento è progettato per smartwatch Garmin e ciclocomputer Edge recenti con supporto mappe. Scopri modelli e varianti esatti con installazioni riuscite.", "hero": "Terento funziona con gli orologi Garmin e i ciclocomputer Garmin Edge più recenti con supporto mappe. Qui sotto trovi i modelli esatti su cui qualcuno ha già installato una mappa con Terento. L’elenco cresce con ogni installazione condivisa.", "missing": "Se il tuo modello non c’è, non significa che non funzioni. Forse nessuno ha ancora condiviso un’installazione riuscita con quel modello.", "model_one": "modello con installazioni riuscite", "model_many": "modelli con installazioni riuscite", "successes": "installazioni riuscite", "latest": "Ultima installazione riuscita", "how_summary": "Come funziona questo elenco", "how_text": "Questo elenco si basa su installazioni Terento reali e riuscite condivise dagli utenti. Mostra solo modelli e varianti Garmin esatti con almeno un’installazione riuscita di una mappa di terze parti. Non è un elenco completo di tutti gli smartwatch e ciclocomputer Edge Garmin con cui Terento può funzionare.", "certification": "I risultati delle installazioni sono condivisi con Terento dagli utenti; non costituiscono una certificazione Garmin.", "providers": "La versione attuale include tutti i provider di mappe del catalogo. Questa informazione sul prodotto è distinta dai risultati dei dispositivi mostrati qui.", "search": "Cerca modelli", "filter_successful": "Filtra per installazioni riuscite", "all_successful": "Tutte le installazioni riuscite", "one_two": "1–2 installazioni riuscite", "three_four": "3–4 installazioni riuscite", "five_plus": "5+ installazioni riuscite", "filter_family": "Filtra per famiglia", "all_families": "Tutte le famiglie", "sort": "Ordina modelli", "most_successful": "Più installazioni riuscite", "name": "A–Z", "clear": "Cancella filtri", "model_one_result": "modello", "model_many_result": "modelli", "of": "di", "no_match": "Nessun modello corrisponde a questi filtri.", "error": "I risultati di compatibilità non sono temporaneamente disponibili. Riprova più tardi.", "card_latest": "Ultima installazione riuscita", "card_smartwatch": "Smartwatch", "noscript": "Sono mostrati gli ultimi risultati di installazione pubblicati. Abilita JavaScript per gli aggiornamenti in tempo reale e i filtri.", "refresh_stale": "Aggiornamento non riuscito. Sono mostrati gli ultimi risultati di installazione pubblicati; i conteggi potrebbero non essere aggiornati.", "refresh_unavailable": "Impossibile caricare i risultati di installazione pubblicati.", "last_loaded": "Ultimo caricamento", "retry": "Riprova", "community_eyebrow": "Risultati della community", "community_heading": "Non vedi il tuo Garmin?", "community_body": "Se il tuo orologio Garmin o il tuo ciclocomputer Edge supporta le mappe, puoi comunque provare Terento. Ogni installazione riuscita che condividi aggiunge il tuo modello all’elenco.", "guide_link": "Prima volta? Leggi la guida per Mac", "download": "Scarica", "date_locale": "it-IT",
    },
}


def page_path(locale: str) -> Path:
    return ROOT / ("site/compatibility/index.html" if locale == "en" else f"site/{locale}/compatibility/index.html")


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


SIZE_RE = re.compile(r"\b\d{2,3}(?:\s*[x×]\s*\d{2,3})?\s*mm\b", re.IGNORECASE)
FEATURE_RE = re.compile(r"\b(?:AMOLED|MicroLED|MIP|Solar|inReach)\b", re.IGNORECASE)


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("®", "").replace("™", "")).strip()


def exact_variant(model: dict[str, object]) -> str:
    raw = clean(model.get("variant"))
    source = f"{raw} {clean(model.get('model'))}"
    size = model.get("caseSizeMm")
    sizes = SIZE_RE.findall(source)
    parts: list[str] = []
    if isinstance(size, int) and size > 0:
        parts.append(f"{size} mm")
    elif sizes:
        parts.append(re.sub(r"\s*mm$", " mm", sizes[0], flags=re.IGNORECASE).replace("×", " × "))
    display = model.get("screenTechnology") or model.get("displayType") or ""
    facts = f"{source} {display}"
    screens = [name for name in ("AMOLED", "MicroLED", "MIP") if re.search(rf"\b{name}\b", facts, re.IGNORECASE)]
    for name in ("AMOLED", "MicroLED", "MIP", "Solar", "inReach"):
        if name in screens and len(screens) > 1:
            continue
        present = bool(re.search(rf"\b{name}\b", facts, re.IGNORECASE))
        if name == "Solar" and model.get("solar") is True:
            present = True
        if name == "inReach" and model.get("inReach") is True:
            present = True
        if present:
            parts.append(name)
    extras = SIZE_RE.sub("", FEATURE_RE.sub("", raw))
    for extra in (part.strip(" ,·•|:–—-/") for part in re.split(r"[,·•|/]", extras)):
        if extra and extra not in parts:
            parts.append(extra)
    return ", ".join(parts) or "Smartwatch"


def public_model_name(value: object) -> str:
    label = clean(value)
    label = re.sub(r"^Garmin\s+", "", label, flags=re.IGNORECASE)
    label = re.split(r"\s*[·|:]\s*", label, maxsplit=1)[0].strip()
    label = SIZE_RE.sub("", label)
    label = FEATURE_RE.sub("", label)
    label = re.sub(r"\bHistorical\s*$", "", label, flags=re.IGNORECASE)
    label = re.sub(r"\b(?:fenix|fēnix)\b", "fēnix", label, flags=re.IGNORECASE)
    label = re.sub(r"\bpro\b", "Pro", label, flags=re.IGNORECASE)
    label = re.sub(r"(fēnix\s+\d+)([sx])\b", lambda match: match.group(1) + match.group(2).upper(), label, flags=re.IGNORECASE)
    label = re.sub(r"[·•|:,]+", " ", label)
    return re.sub(r"\s+", " ", label).strip(" ,·•|:–—-") or clean(value)


def date_text(value: object, locale: str) -> str:
    if not value:
        return ""
    try:
        date = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return ""
    months = {"en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), "de": ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"), "fr": ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"), "pl": ("stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września", "października", "listopada", "grudnia"), "cs": ("ledna", "února", "března", "dubna", "května", "června", "července", "srpna", "září", "října", "listopadu", "prosince"), "it": ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre")}[locale]
    day, year, month = date.day, date.year, months[date.month - 1]
    if locale == "en":
        return f"{month} {day}, {year}"
    if locale == "de":
        return f"{day}. {month} {year}"
    if locale == "fr":
        return f"{day} {month} {year}"
    if locale == "cs":
        return f"{day}. {month} {year}"
    return f"{day} {month} {year}"


# Card counts below 100 are exact; from 100 they round down to the hundred with
# a plus (owner rule 2026-10-11). Grouping mirrors Intl.NumberFormat per locale:
# (separator, minimum grouping digits).
NUMBER_GROUPING = {"en": (",", 1), "de": (".", 1), "fr": ("\u202f", 1), "pl": ("\u00a0", 2), "cs": ("\u00a0", 1), "it": (".", 2)}


def format_number(value: int, locale: str) -> str:
    separator, minimum_grouping = NUMBER_GROUPING[locale]
    digits = str(value)
    if len(digits) < 3 + minimum_grouping:
        return digits
    groups = []
    while len(digits) > 3:
        digits, group = digits[:-3], digits[-3:]
        groups.insert(0, group)
    return separator.join([digits, *groups])


def card_count(count: int) -> tuple[int, bool]:
    """Return the displayed card count and whether it is a rounded lower bound."""
    return (count, False) if count < 100 else (count // 100 * 100, True)


def card_count_text(count: int, locale: str) -> str:
    shown, rounded = card_count(count)
    return format_number(shown, locale) + ("+" if rounded else "")


def install_label(count: int, locale: str) -> str:
    text, one = card_count_text(count, locale), card_count(count)[0] == 1
    if locale == "en":
        return f"{text} successful install{'' if one else 's'}"
    if locale == "de":
        return f"{text} erfolgreiche Installation{'' if one else 'en'}"
    if locale == "fr":
        return f"{text} installation{'' if one else 's'} réussie{'' if one else 's'}"
    if locale == "pl":
        return f"{text} {'udana instalacja' if one else 'udanych instalacji'}"
    if locale == "cs":
        return f"{text} {'úspěšná instalace' if one else 'úspěšných instalací'}"
    return f"{text} {'installazione riuscita' if one else 'installazioni riuscite'}"


def installation_split(model: dict[str, object]) -> tuple[int, int]:
    """Return (app, web) successful installations; older snapshots count everything as app."""
    successful = int(model["successfulInstallations"])
    app, web = model.get("appSuccessfulInstallations"), model.get("webSuccessfulInstallations")
    if app is None and web is None:
        return successful, 0
    if not isinstance(app, int) or not isinstance(web, int) or app < 0 or web < 0 or app + web != successful:
        raise ValueError(f"compatibility snapshot has an inconsistent app/web split for {model.get('model')!r}")
    return app, web


# Lucide 0.460.0 `laptop` and `globe` (ISC, see THIRD_PARTY_NOTICES.md): original paths,
# 24 px outline at the brand 1.75 px stroke. Keep in sync with
# SOURCE_ICONS in site/compatibility/compatibility.js.
SOURCE_ICONS = {
    "app": '<svg class="watch-install-source-icon" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><!-- @license lucide-static v0.460.0 - ISC --><path d="M20 16V7a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v9m16 0H4m16 0 1.28 2.55a1 1 0 0 1-.9 1.45H3.62a1 1 0 0 1-.9-1.45L4 16"/></svg>',
    "web": '<svg class="watch-install-source-icon" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><!-- @license lucide-static v0.460.0 - ISC --><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>',
}
SOURCE_LABELS = {
    "en": {"app": "App", "web": "Web", "app_aria": "{} with the app", "web_aria": "{} with the web installer"},
    "de": {"app": "App", "web": "Web", "app_aria": "{} mit der App", "web_aria": "{} mit dem Web-Installer"},
    "fr": {"app": "App", "web": "Web", "app_aria": "{} avec l’application", "web_aria": "{} avec l’installateur web"},
    "pl": {"app": "App", "web": "Web", "app_aria": "{} przez aplikację", "web_aria": "{} przez instalator webowy"},
    "cs": {"app": "App", "web": "Web", "app_aria": "{} přes aplikaci", "web_aria": "{} přes webový instalátor"},
    "it": {"app": "App", "web": "Web", "app_aria": "{} con l’app", "web_aria": "{} con l’installer web"},
}


def source_parts(model: dict[str, object], locale: str) -> list[tuple[str, str]]:
    """Return (source, displayed count) pairs for the non-zero app/web sources."""
    app, web = installation_split(model)
    return [(source, card_count_text(count, locale)) for source, count in (("app", app), ("web", web)) if count > 0]


def sources_markup(model: dict[str, object], locale: str) -> str:
    labels = SOURCE_LABELS[locale]
    parts = " ".join(f'<span class="watch-install-source">{SOURCE_ICONS[source]}{esc(labels[source])} {esc(text)}</span>' for source, text in source_parts(model, locale))
    return f'<p class="watch-install-sources">{parts}</p>' if parts else ""


def sources_accessible(model: dict[str, object], locale: str) -> str:
    labels = SOURCE_LABELS[locale]
    return ", ".join(labels[f"{source}_aria"].format(text) for source, text in source_parts(model, locale))


def load_snapshot() -> dict:
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    if not isinstance(snapshot.get("models"), list) or not snapshot["models"]:
        raise ValueError("compatibility snapshot must contain public models")
    if any(int(row.get("successfulInstallations", 0)) < 1 for row in snapshot["models"]):
        raise ValueError("compatibility snapshot contains a model without a successful installation")
    return snapshot


def card_markup(model: dict[str, object], locale: str) -> str:
    copy = COPY[locale]
    display_model, variant = public_model_name(model["model"]), exact_variant(model)
    count, latest = int(model["successfulInstallations"]), date_text(model.get("lastSuccessfulInstallation"), locale)
    latest_markup = f'<p class="watch-card-meta">{esc(copy["card_latest"])} {esc(latest)}</p>' if latest else ""
    image = model.get("imageUrl") or FALLBACK_IMAGE_URL
    accessible = ", ".join(filter(None, (display_model, variant, install_label(count, locale), sources_accessible(model, locale), f'{copy["card_latest"]} {latest}' if latest else "")))
    return f'''<article class="watch-card" aria-label="{esc(accessible)}"><div class="watch-card-image"><img data-remote-src="{esc(image)}" src="{esc(image)}" alt="" loading="lazy"></div><div class="watch-card-body"><div class="watch-card-heading"><p class="watch-family">{esc(model.get("familyName") or "Garmin")}</p><div class="watch-card-model-row"><h3>{esc(display_model)} <span class="watch-variant">{esc(variant)}</span></h3></div></div><p class="watch-install-count">{esc(install_label(count, locale))}</p>{sources_markup(model, locale)}{latest_markup}</div></article>'''


def summary_markup(snapshot: dict, locale: str) -> str:
    copy, models = COPY[locale], snapshot["models"]
    total = sum(int(row["successfulInstallations"]) for row in models)
    latest = max((row.get("lastSuccessfulInstallation") for row in models if row.get("lastSuccessfulInstallation")), default=None)
    latest_text = date_text(latest, locale)
    label = copy["model_one"] if len(models) == 1 else copy["model_many"]
    updated = f'<span class="compatibility-summary-item compatibility-summary-updated" data-summary-updated>{esc(copy["latest"])} <time data-summary="updated" datetime="{esc(latest or "")}">{esc(latest_text)}</time></span>' if latest_text else ""
    return f'''<div class="compatibility-summary" id="compatibility-summary" aria-live="polite" aria-busy="false"><p class="compatibility-summary-line" data-summary-content><span class="compatibility-summary-item"><strong data-summary="models">{len(models)}</strong> <span data-summary-model-label>{esc(label)}</span><span class="compatibility-summary-separator" aria-hidden="true">&nbsp;&nbsp;</span></span><span class="compatibility-summary-item"><strong data-summary="successes">{total}</strong> {esc(copy["successes"])}<span class="compatibility-summary-separator" aria-hidden="true">&nbsp;&nbsp;</span></span>{updated}</p><p class="compatibility-freshness" role="status" hidden><span id="compatibility-freshness"></span> <button type="button" id="compatibility-retry" hidden>{esc(copy["retry"])}</button></p></div>'''


def how_markup(locale: str) -> str:
    copy = COPY[locale]
    return f'''<details class="compatibility-how"><summary>{esc(copy["how_summary"])}</summary><div class="compatibility-how-body"><p>{esc(copy["how_text"])}</p><p class="compatibility-evidence-note" data-compatibility-evidence-note>{esc(copy["certification"])}</p><p class="compatibility-provider-note">{esc(copy["providers"])}</p></div></details>'''


def filters_markup(locale: str) -> str:
    copy = COPY[locale]
    return f'''<form class="compatibility-filters" id="compatibility-filters" role="search"><label class="compatibility-filter-control compatibility-search"><span class="sr-only">{esc(copy["search"])}</span><input id="watch-search" type="search" placeholder="{esc(copy["search"])}" autocomplete="off"></label><label class="compatibility-filter-control compatibility-filter-select"><span class="sr-only">{esc(copy["filter_successful"])}</span><select id="successful-install-filter"><option value="ALL">{esc(copy["all_successful"])}</option><option value="1_2">{esc(copy["one_two"])}</option><option value="3_4">{esc(copy["three_four"])}</option><option value="5_PLUS">{esc(copy["five_plus"])}</option></select></label><label class="compatibility-filter-control compatibility-filter-select"><span class="sr-only">{esc(copy["filter_family"])}</span><select id="family-filter"><option value="ALL">{esc(copy["all_families"])}</option></select></label><label class="compatibility-filter-control compatibility-filter-select"><span class="sr-only">{esc(copy["sort"])}</span><select id="sort-filter"><option value="successful">{esc(copy["most_successful"])}</option><option value="name">{esc(copy["name"])}</option></select></label><button type="button" class="compatibility-clear" id="compatibility-clear" disabled><svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><!-- @license lucide-static v0.460.0 - ISC --><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>{esc(copy["clear"])}</button></form>'''


def results_markup(snapshot: dict, locale: str) -> str:
    copy, models = COPY[locale], snapshot["models"]
    cards = "\n".join(card_markup(model, locale) for model in models)
    label = copy["model_one_result"] if len(models) == 1 else copy["model_many_result"]
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f'''<p class="compatibility-results-count" id="results-count" aria-live="polite">{len(models)} {esc(label)}</p><div class="watch-grid" id="watch-grid" aria-live="polite" aria-busy="false">{cards}</div><script type="application/json" id="compatibility-snapshot">{snapshot_json}</script><noscript class="compatibility-noscript"><p>{esc(copy["noscript"])}</p></noscript><p class="compatibility-empty" id="compatibility-empty" hidden>{esc(copy["no_match"])}</p>'''


# Same words as add-guide-links.py COPY["download_web_installer"] (Download page).
WEB_INSTALLER_LABEL = {
    "en": "No Apple Silicon Mac? Use the web installer",
    "de": "Kein Mac mit Apple Silicon? Nutze den Web-Installer",
    "fr": "Pas de Mac Apple Silicon ? Utilisez l’installateur web",
    "pl": "Nie masz Maca z Apple Silicon? Użyj instalatora webowego",
    "cs": "Nemáte Mac s Apple Silicon? Použijte webový instalátor",
    "it": "Niente Mac con Apple Silicon? Usa l’installer web",
}


def web_installer_link(locale: str) -> str:
    """Without an Apple Silicon Mac: the web installer, in the Download page's words (add-guide-links.py)."""
    label = WEB_INSTALLER_LABEL[locale]
    href = f"/{'' if locale == 'en' else f'{locale}/'}install/"
    return f'<a class="text-link compatibility-web-installer-link" href="{href}" data-umami-event="web-installer-link-click" data-umami-event-location="compatibility-community-testing">{esc(label)}</a>'


def community_markup(locale: str) -> str:
    copy, prefix = COPY[locale], "" if locale == "en" else f"/{locale}"
    guide, download = f"{prefix}/guides/install-garmin-maps-mac/", f"{prefix}/download/"
    return f'''<div class="compatibility-community-cta"><div class="compatibility-community-copy"><h2>{esc(copy["community_heading"])}</h2><p>{esc(copy["community_body"])}</p><a class="text-link compatibility-guide-link" href="{guide}" data-umami-event="guide-link-click" data-umami-event-location="compatibility-community-testing">{esc(copy["guide_link"])}</a>{web_installer_link(locale)}</div><a class="download-action download-action-primary compatibility-community-link" href="{download}" data-umami-event="download-cta-click" data-umami-event-location="compatibility-community-testing">{esc(copy["download"])}</a></div>'''


def render_page(source: str, locale: str, snapshot: dict) -> str:
    copy = COPY[locale]
    source = re.sub(r'\s*<p class="eyebrow"><span class="status-dot"[^>]*></span>[^<]*</p>', "", source, count=1)
    source = re.sub(r'(<h1 id="compatibility-title">)[^<]*(</h1>)', rf'\g<1>{esc(copy["title"])}\g<2>', source, count=1)
    source = re.sub(r'(<p class="hero-lede">)[\s\S]*?(</p>)', rf'\g<1>{esc(copy["hero"])}\g<2>', source, count=1)
    missing_markup = f'<p class="hero-lede compatibility-missing-note">{esc(copy["missing"])}</p>'
    source = re.sub(r'\s*<p class="hero-lede compatibility-missing-note">[\s\S]*?</p>', "", source)
    source = source.replace(f'<p class="hero-lede">{esc(copy["hero"])}</p>', f'<p class="hero-lede">{esc(copy["hero"])}</p>{missing_markup}', 1)
    source, count = re.subn(r'<div class="compatibility-summary" id="compatibility-summary"[\s\S]*?</div>\s*(?=<details class="compatibility-how")', summary_markup(snapshot, locale) + "\n\n          ", source, count=1)
    if count != 1:
        raise ValueError(f"{page_path(locale)}: compatibility summary insertion point not found")
    source, count = re.subn(r'<details class="compatibility-how">[\s\S]*?</details>', how_markup(locale), source, count=1)
    if count != 1:
        raise ValueError(f"{page_path(locale)}: compatibility explanation not found")
    source, count = re.subn(r'<form class="compatibility-filters"[\s\S]*?</form>(?:\s*<button[^>]*id="compatibility-clear"[^>]*>[\s\S]*?</button>)?', filters_markup(locale), source, count=1)
    if count != 1:
        raise ValueError(f"{page_path(locale)}: compatibility filters not found")
    start, end = source.find('<p class="compatibility-results-count" id="results-count"'), source.find('<p class="compatibility-error"')
    if start < 0 or end < 0:
        raise ValueError(f"{page_path(locale)}: compatibility results insertion point not found")
    source = source[:start] + results_markup(snapshot, locale) + "\n          " + source[end:]
    source, count = re.subn(r'<div class="compatibility-community-cta">[\s\S]*?</div>\s*</div>\s*</section>', community_markup(locale) + "</div></section>", source, count=1)
    if count != 1:
        raise ValueError(f"{page_path(locale)}: compatibility community CTA not found")
    source = re.sub(r'/compatibility/compatibility-data\.js\?v=[^" ]+', f'/compatibility/compatibility-data.js?v={ASSET_VERSION}', source)
    source = re.sub(r'/compatibility/compatibility-locales\.js\?v=[^" ]+', f'/compatibility/compatibility-locales.js?v={LOCALES_ASSET_VERSION}', source)
    source = re.sub(r'/compatibility/compatibility\.js\?v=[^" ]+', f'/compatibility/compatibility.js?v={ASSET_VERSION}', source)
    source = re.sub(r'(<p class="compatibility-error"[^>]*>)[^<]*(</p>)', rf'\g<1>{esc(copy["error"])}\g<2>', source, count=1)
    # One web-page + breadcrumb JSON-LD block (no device list: the snapshot is not a support list).
    source = re.sub(r'\n[ \t]*<script type="application/ld\+json">[\s\S]*?</script>', "", source)
    block = SCHEMA["json_ld_block"](locale, "compatibility/", "CollectionPage")
    source, count = re.subn(r'\n(\s*)</head>', lambda match: "\n" + block + "\n" + match.group(1) + "</head>", source, count=1)
    if count != 1:
        raise ValueError(f"{page_path(locale)}: </head> not found")
    return source


def main() -> None:
    snapshot = load_snapshot()
    for locale in LOCALES:
        path = page_path(locale)
        path.write_text(render_page(path.read_text(encoding="utf-8"), locale, snapshot), encoding="utf-8")
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
