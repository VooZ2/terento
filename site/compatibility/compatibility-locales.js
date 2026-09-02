(() => {
  const statusCodes = ["VERIFIED", "SUPPORTED", "TESTED", "TESTING"];

  const definitions = {
    en: {
      language: "en",
      dateLocale: "en-US",
      title: "Garmin compatibility",
      metaTitle: "Garmin Watch Compatibility — Terento",
      metaDescription: "Check Garmin smartwatch compatibility for Terento using real installation results by model and variant.",
      hero: "See real Terento installation results for third-party maps by exact Garmin watch model and variant. Compatibility grows as more successful installations are shared by users.",
      summary: {
        modelOne: "model with evidence",
        modelMany: "models with evidence",
        successes: "successful installs",
        moreModels: "More models ready for testing",
        updated: "Updated",
      },
      howSummary: "How compatibility works",
      howText: "Public compatibility is based on real installation evidence from exact Garmin models and variants. Each successful installation shared by users helps us confirm compatibility with greater confidence.",
      evidenceNote: "These counts come from successful installations shared with Terento. They are not Garmin certification.",
      filters: {
        search: "Search models",
        status: "Filter by status",
        allStatuses: "All statuses",
        family: "Filter by family",
        allFamilies: "All families",
        sort: "Sort models",
        attempts: "Most installations",
        successes: "Most successful",
        name: "A–Z",
        statusOption: "Status",
      },
      results: { modelOne: "model", modelMany: "models", of: "of", noMatch: "No tried models match these filters.", error: "Compatibility results are temporarily unavailable. Please try again later." },
      card: { latest: "Latest installation", smartwatch: "Smartwatch", unavailable: "Compatibility unavailable" },
      statuses: {
        VERIFIED: { label: "Verified", description: "5 or more successful installations have confirmed compatibility." },
        SUPPORTED: { label: "Supported", description: "3–4 successful installations have confirmed compatibility." },
        TESTED: { label: "Tested", description: "1–2 successful installations have been shared by Terento users." },
        TESTING: { label: "Testing", description: "Terento can install third-party maps on this model, but we’re waiting for the first successful installation shared by users to confirm compatibility." },
      },
    },
    de: {
      language: "de",
      dateLocale: "de-DE",
      title: "Garmin-Kompatibilität",
      metaTitle: "Kompatibilität von Garmin-Uhren — Terento",
      metaDescription: "Prüfe die Kompatibilität von Garmin-Smartwatches mit Terento anhand echter Installationen für Modell und Variante.",
      hero: "Sieh dir echte Terento-Installationsergebnisse für Drittanbieter-Karten nach genauem Garmin-Uhrenmodell und Variante an. Die Kompatibilität wächst, wenn Nutzer weitere erfolgreiche Installationen teilen.",
      summary: { modelOne: "Modell mit Nachweis", modelMany: "Modelle mit Nachweis", successes: "erfolgreiche Installationen", moreModels: "Weitere Modelle zum Testen", updated: "Aktualisiert" },
      howSummary: "So funktioniert die Kompatibilität",
      howText: "Die öffentliche Kompatibilität basiert auf echten Installationsnachweisen für genaue Garmin-Modelle und Varianten. Jede von Nutzern geteilte erfolgreiche Installation hilft uns, die Kompatibilität verlässlicher zu bestätigen.",
      evidenceNote: "Diese Zahlen stammen aus erfolgreichen Installationen, die mit Terento geteilt wurden. Sie sind keine Garmin-Zertifizierung.",
      filters: { search: "Modelle suchen", status: "Nach Status filtern", allStatuses: "Alle Status", family: "Nach Familie filtern", allFamilies: "Alle Familien", sort: "Modelle sortieren", attempts: "Meiste Installationen", successes: "Meiste erfolgreiche", name: "A–Z", statusOption: "Status" },
      results: { modelOne: "Modell", modelMany: "Modelle", of: "von", noMatch: "Keine getesteten Modelle passen zu diesen Filtern.", error: "Die Kompatibilitätsergebnisse sind vorübergehend nicht verfügbar. Bitte versuche es später erneut." },
      card: { latest: "Letzte Installation", smartwatch: "Smartwatch", unavailable: "Kompatibilität nicht verfügbar" },
      statuses: { VERIFIED: { label: "Bestätigt", description: "Mindestens 5 erfolgreiche Installationen haben die Kompatibilität bestätigt." }, SUPPORTED: { label: "Unterstützt", description: "3–4 erfolgreiche Installationen haben die Kompatibilität bestätigt." }, TESTED: { label: "Getestet", description: "1–2 erfolgreiche Installationen wurden von Terento-Nutzern geteilt." }, TESTING: { label: "In Prüfung", description: "Terento kann Drittanbieter-Karten auf diesem Modell installieren; wir warten noch auf die erste von Nutzern geteilte erfolgreiche Installation zur Bestätigung." } },
    },
    fr: {
      language: "fr",
      dateLocale: "fr-FR",
      title: "Compatibilité Garmin",
      metaTitle: "Compatibilité des montres Garmin — Terento",
      metaDescription: "Vérifiez la compatibilité des montres Garmin avec Terento grâce aux résultats réels par modèle et variante.",
      hero: "Consultez les résultats réels d’installation de cartes tierces avec Terento pour chaque modèle et variante de montre Garmin. La compatibilité progresse à mesure que les utilisateurs partagent de nouvelles installations réussies.",
      summary: { modelOne: "modèle avec preuve", modelMany: "modèles avec preuve", successes: "installations réussies", moreModels: "D’autres modèles prêts à être testés", updated: "Mis à jour" },
      howSummary: "Comment fonctionne la compatibilité",
      howText: "La compatibilité publique repose sur des preuves réelles d’installation pour des modèles et variantes Garmin précis. Chaque installation réussie partagée par les utilisateurs nous aide à confirmer la compatibilité avec plus de certitude.",
      evidenceNote: "Ces chiffres proviennent d’installations réussies partagées avec Terento. Ils ne constituent pas une certification Garmin.",
      filters: { search: "Rechercher un modèle", status: "Filtrer par statut", allStatuses: "Tous les statuts", family: "Filtrer par famille", allFamilies: "Toutes les familles", sort: "Trier les modèles", attempts: "Plus d’installations", successes: "Plus d’installations réussies", name: "A–Z", statusOption: "Statut" },
      results: { modelOne: "modèle", modelMany: "modèles", of: "sur", noMatch: "Aucun modèle testé ne correspond à ces filtres.", error: "Les résultats de compatibilité sont temporairement indisponibles. Réessayez plus tard." },
      card: { latest: "Dernière installation", smartwatch: "Montre connectée", unavailable: "Compatibilité indisponible" },
      statuses: { VERIFIED: { label: "Vérifiée", description: "Au moins 5 installations réussies ont confirmé la compatibilité." }, SUPPORTED: { label: "Prise en charge", description: "3 à 4 installations réussies ont confirmé la compatibilité." }, TESTED: { label: "Testée", description: "1 à 2 installations réussies ont été partagées par des utilisateurs de Terento." }, TESTING: { label: "En test", description: "Terento peut installer des cartes tierces sur ce modèle, mais nous attendons la première installation réussie partagée par un utilisateur pour confirmer la compatibilité." } },
    },
    pl: {
      language: "pl",
      dateLocale: "pl-PL",
      title: "Kompatybilność z Garminem",
      metaTitle: "Kompatybilność zegarków Garmin — Terento",
      metaDescription: "Sprawdź kompatybilność zegarków Garmin z Terento na podstawie rzeczywistych instalacji dla modelu i wariantu.",
      hero: "Zobacz rzeczywiste wyniki instalacji map innych firm przez Terento dla konkretnego modelu i wariantu zegarka Garmin. Kompatybilność rośnie wraz z kolejnymi udanymi instalacjami udostępnianymi przez użytkowników.",
      summary: { modelOne: "model z potwierdzeniem", modelMany: "modele z potwierdzeniem", successes: "udanych instalacji", moreModels: "Kolejne modele gotowe do testów", updated: "Zaktualizowano" },
      howSummary: "Jak działa potwierdzanie kompatybilności",
      howText: "Publiczna kompatybilność opiera się na rzeczywistych dowodach instalacji dla konkretnych modeli i wariantów Garmin. Każda udana instalacja udostępniona przez użytkownika pomaga nam potwierdzać kompatybilność z większą pewnością.",
      evidenceNote: "Te dane pochodzą z udanych instalacji udostępnionych Terento. Nie są certyfikatem firmy Garmin.",
      filters: { search: "Szukaj modeli", status: "Filtruj według statusu", allStatuses: "Wszystkie statusy", family: "Filtruj według rodziny", allFamilies: "Wszystkie rodziny", sort: "Sortuj modele", attempts: "Najwięcej instalacji", successes: "Najwięcej udanych", name: "A–Z", statusOption: "Status" },
      results: { modelOne: "model", modelMany: "modeli", of: "z", noMatch: "Żaden testowany model nie pasuje do tych filtrów.", error: "Wyniki kompatybilności są chwilowo niedostępne. Spróbuj ponownie później." },
      card: { latest: "Ostatnia instalacja", smartwatch: "Zegarek", unavailable: "Kompatybilność niedostępna" },
      statuses: { VERIFIED: { label: "Potwierdzona", description: "Co najmniej 5 udanych instalacji potwierdziło kompatybilność." }, SUPPORTED: { label: "Obsługiwana", description: "3–4 udane instalacje potwierdziły kompatybilność." }, TESTED: { label: "Przetestowana", description: "Użytkownicy Terento udostępnili 1–2 udane instalacje." }, TESTING: { label: "W trakcie testów", description: "Terento może instalować mapy innych firm na tym modelu, ale czekamy na pierwszą udaną instalację udostępnioną przez użytkownika, aby potwierdzić kompatybilność." } },
    },
    cs: {
      language: "cs",
      dateLocale: "cs-CZ",
      title: "Kompatibilita Garmin",
      metaTitle: "Kompatibilita hodinek Garmin — Terento",
      metaDescription: "Ověřte kompatibilitu hodinek Garmin s Terento podle skutečných instalací pro konkrétní model a variantu.",
      hero: "Prohlédněte si skutečné výsledky instalace map třetích stran pomocí Terento pro konkrétní model a variantu hodinek Garmin. Kompatibilita roste s každou další úspěšnou instalací sdílenou uživateli.",
      summary: { modelOne: "model s ověřením", modelMany: "modely s ověřením", successes: "úspěšných instalací", moreModels: "Další modely připravené k testování", updated: "Aktualizováno" },
      howSummary: "Jak kompatibilita funguje",
      howText: "Veřejná kompatibilita vychází ze skutečných instalačních výsledků pro konkrétní modely a varianty Garmin. Každá úspěšná instalace sdílená uživateli nám pomáhá potvrdit kompatibilitu s větší jistotou.",
      evidenceNote: "Tato čísla pocházejí z úspěšných instalací sdílených s Terento. Nejde o certifikaci Garmin.",
      filters: { search: "Hledat modely", status: "Filtrovat podle stavu", allStatuses: "Všechny stavy", family: "Filtrovat podle řady", allFamilies: "Všechny řady", sort: "Řadit modely", attempts: "Nejvíce instalací", successes: "Nejvíce úspěšných", name: "A–Z", statusOption: "Stav" },
      results: { modelOne: "model", modelMany: "modelů", of: "z", noMatch: "Žádný testovaný model neodpovídá těmto filtrům.", error: "Výsledky kompatibility jsou dočasně nedostupné. Zkuste to později znovu." },
      card: { latest: "Poslední instalace", smartwatch: "Hodinky", unavailable: "Kompatibilita není dostupná" },
      statuses: { VERIFIED: { label: "Ověřeno", description: "Kompatibilitu potvrdilo nejméně 5 úspěšných instalací." }, SUPPORTED: { label: "Podporováno", description: "Kompatibilitu potvrdily 3–4 úspěšné instalace." }, TESTED: { label: "Testováno", description: "Uživatelé Terento sdíleli 1–2 úspěšné instalace." }, TESTING: { label: "Testování", description: "Terento umí na tomto modelu instalovat mapy třetích stran, ale na potvrzení kompatibility čekáme na první úspěšnou instalaci sdílenou uživatelem." } },
    },
    it: {
      language: "it",
      dateLocale: "it-IT",
      title: "Compatibilità Garmin",
      metaTitle: "Compatibilità degli smartwatch Garmin — Terento",
      metaDescription: "Verifica la compatibilità degli smartwatch Garmin con Terento tramite risultati reali per modello e variante.",
      hero: "Scopri i risultati reali di installazione di mappe di terze parti con Terento per ogni modello e variante di smartwatch Garmin. La compatibilità cresce quando gli utenti condividono nuove installazioni riuscite.",
      summary: { modelOne: "modello con evidenze", modelMany: "modelli con evidenze", successes: "installazioni riuscite", moreModels: "Altri modelli pronti per i test", updated: "Aggiornato" },
      howSummary: "Come funziona la compatibilità",
      howText: "La compatibilità pubblica si basa su risultati reali di installazione per modelli e varianti Garmin esatti. Ogni installazione riuscita condivisa dagli utenti ci aiuta a confermare la compatibilità con maggiore sicurezza.",
      evidenceNote: "Questi dati provengono da installazioni riuscite condivise con Terento. Non sono una certificazione Garmin.",
      filters: { search: "Cerca modelli", status: "Filtra per stato", allStatuses: "Tutti gli stati", family: "Filtra per famiglia", allFamilies: "Tutte le famiglie", sort: "Ordina modelli", attempts: "Più installazioni", successes: "Più installazioni riuscite", name: "A–Z", statusOption: "Stato" },
      results: { modelOne: "modello", modelMany: "modelli", of: "di", noMatch: "Nessun modello provato corrisponde a questi filtri.", error: "I risultati di compatibilità non sono temporaneamente disponibili. Riprova più tardi." },
      card: { latest: "Ultima installazione", smartwatch: "Smartwatch", unavailable: "Compatibilità non disponibile" },
      statuses: { VERIFIED: { label: "Verificata", description: "Almeno 5 installazioni riuscite hanno confermato la compatibilità." }, SUPPORTED: { label: "Supportata", description: "3–4 installazioni riuscite hanno confermato la compatibilità." }, TESTED: { label: "Testata", description: "Gli utenti di Terento hanno condiviso 1–2 installazioni riuscite." }, TESTING: { label: "In test", description: "Terento può installare mappe di terze parti su questo modello, ma aspettiamo la prima installazione riuscita condivisa da un utente per confermare la compatibilità." } },
    },
  };

  const successfulInstallLabel = {
    en: (count) => `${count} successful install${count === 1 ? "" : "s"}`,
    de: (count) => `${count} erfolgreiche${count === 1 ? "" : "n"} Installation${count === 1 ? "" : "en"}`,
    fr: (count) => `${count} installation${count === 1 ? "" : "s"} réussie${count === 1 ? "" : "s"}`,
    pl: (count) => `${count} ${count === 1 ? "udana instalacja" : "udanych instalacji"}`,
    cs: (count) => `${count} ${count === 1 ? "úspěšná instalace" : "úspěšných instalací"}`,
    it: (count) => `${count} installazione${count === 1 ? "" : "i"} riuscita${count === 1 ? "" : "e"}`,
  };

  Object.entries(definitions).forEach(([language, definition]) => {
    definition.successfulInstallLabel = successfulInstallLabel[language];
  });

  const getLocale = (value) => definitions[String(value || "en").toLowerCase().split("-")[0]] || definitions.en;
  const selectedLanguage = typeof document === "undefined" ? "en" : document.documentElement.lang;
  const selected = getLocale(selectedLanguage);
  const api = { statusCodes, definitions, getLocale, selected };

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof globalThis !== "undefined") globalThis.TerentoCompatibilityLocale = selected;
})();
