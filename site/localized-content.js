(() => {
  const translations = {
    de: {
      home: {
        description: "Kostenlose Open-Source-macOS-App zum Installieren und Verwalten von Drittanbieter-Karten auf Garmin-Smartwatches. Apple Silicon erforderlich; die Kompatibilität wird für jedes Modell bestätigt.",
        title: "Terento — Drittanbieter-Karten für Garmin auf dem Mac",
        hero: "Eine native macOS-App zum Installieren und Verwalten von Drittanbieter-Karten auf Garmin-Smartwatches.",
        problem: "Die Installation von Drittanbieter-Karten sollte keine Dateimanager, Geräteordner oder veralteten Übertragungstools erfordern.",
        installStep: "Wähle Regionen und sieh vorher, wie viel Speicher benötigt wird.",
        install: "Wähle die gewünschten Regionen aus und sieh vor der Installation, wie viel Speicher benötigt wird.",
        manageEyebrow: "Installierte Karten",
        scope: "Terento ist für Garmin-Smartwatches mit Kartenunterstützung konzipiert. Die öffentliche Kompatibilität für die Installation von Drittanbieter-Karten wird für jedes genaue Modell und jede Variante anhand echter, von Nutzern geteilter Ergebnisse bestätigt.",
        faq: [
          ["Welche Garmin-Uhren funktionieren mit Terento?", "Terento ist für Garmin-Smartwatches mit Kartenunterstützung konzipiert. Die öffentliche Kompatibilität für die Installation von Drittanbieter-Karten wird für jedes genaue Modell und jede Variante anhand echter, von Nutzern geteilter Ergebnisse bestätigt. Auf der <a href=\"/de/compatibility/\">Kompatibilitätsseite</a> findest du die aktuellen Nachweise."],
          ["Kann ich Drittanbieter-Karten von einem Mac ohne BaseCamp auf einer Garmin-Uhr installieren?", "Ja. Terento bietet einen geführten nativen macOS-Ablauf zum Installieren unterstützter Drittanbieter-Karten ohne BaseCamp oder einen allgemeinen MTP-Dateimanager. Die aktuelle Beta verwendet Freizeitkarte und erfordert einen Apple-Silicon-Mac. <a href=\"/de/guides/install-garmin-maps-mac/\">Lies die Mac-Installationsanleitung.</a>"],
          ["Warum erscheint meine Garmin-Uhr nicht sofort im Finder oder in Terento?", "Viele neuere Garmin-Uhren verwenden MTP und erscheinen möglicherweise nicht als normales Finder-Laufwerk. Die Erkennung durch Terento kann nach dem Verbinden 1–2 Minuten dauern. Lass die Uhr verbunden und schließe Garmin Express, OpenMTP oder eine andere App, die sie bereits verwenden könnte."],
          ["Ersetzt Terento Garmin Express?", "Nein. Terento konzentriert sich auf die Installation und Verwaltung unterstützter Drittanbieter-Karten. Garmin Express bleibt für offizielle Garmin-Geräteupdates und Dienste relevant."],
          ["Ist Terento sicher für vorhandene Garmin-Karten?", "Ja. Vorhandene Garmin-Karten bleiben unverändert. Terento verwaltet nur Karten, die es installiert und lokal aufgezeichnet hat."],
          ["Woher kommen die Karten?", "Die aktuelle Beta verwendet Freizeitkarte als Kartenquelle. Terento lädt Karten vom Originalanbieter auf deinen Mac und überträgt sie anschließend auf deine Uhr."],
          ["Was soll ich tun, wenn die Installation fehlschlägt?", "Öffne ein GitHub-Issue oder sende das Diagnoseprotokoll per E-Mail an <a href=\"mailto:hello@terento.app?subject=Terento%20installation%20issue\">hello@terento.app</a>. Der Bericht hilft bei der Untersuchung des Fehlers, ohne dass du Geräteordner manuell prüfen musst.", { support: true }],
          ["Lädt Terento Gerätedaten hoch?", "Das Teilen von Kompatibilitätsdaten ist optional. Wenn aktiviert, werden nur datensparsame Installationsnachweise geteilt; Garmin-Unit-IDs, Seriennummern und lokale Pfade nicht."],
          ["Warum ist Apple Silicon erforderlich?", "Die aktuelle native macOS-Beta ist für Apple-Silicon-Macs mit macOS 13 oder neuer gebaut."],
          ["Kann ich installierte Karten sichern oder entfernen?", "Du kannst von Terento verwaltete Karten in der App sichern oder entfernen. Andere Karten bleiben schreibgeschützt."],
        ],
      },
      fr: {
        description: "Application macOS gratuite et open source pour installer et gérer des cartes tierces sur les montres Garmin. Apple Silicon requis ; la compatibilité est confirmée modèle par modèle.",
        title: "Terento — Cartes tierces pour Garmin sur Mac",
        hero: "Une application macOS native pour installer et gérer des cartes tierces sur les montres Garmin.",
        problem: "Installer des cartes tierces ne devrait pas nécessiter de gestionnaire de fichiers, de dossiers d’appareil ni d’outils de transfert obsolètes.",
        installStep: "Choisissez les régions et consultez l’espace nécessaire avant l’installation.",
        install: "Choisissez les régions souhaitées et consultez l’espace nécessaire avant l’installation.",
        manageEyebrow: "Cartes installées",
        scope: "Terento est conçu pour les montres Garmin compatibles avec les cartes. La compatibilité publique pour l’installation de cartes tierces est confirmée pour chaque modèle et chaque variante grâce à des résultats réels partagés par les utilisateurs.",
        faq: [
          ["Quelles montres Garmin fonctionnent avec Terento ?", "Terento est conçu pour les montres connectées Garmin compatibles avec les cartes. La compatibilité publique pour l’installation de cartes tierces est confirmée pour chaque modèle et chaque variante grâce aux résultats réels partagés par les utilisateurs. Consultez la <a href=\"/fr/compatibility/\">page Compatibilité</a> pour voir les preuves actuelles."],
          ["Puis-je installer des cartes tierces sur une montre Garmin depuis un Mac sans BaseCamp ?", "Oui. Terento propose un parcours macOS natif guidé pour installer des cartes tierces prises en charge, sans BaseCamp ni gestionnaire MTP généraliste. La bêta actuelle utilise Freizeitkarte et nécessite un Mac Apple Silicon. <a href=\"/fr/guides/install-garmin-maps-mac/\">Lisez le guide d’installation sur Mac.</a>"],
          ["Pourquoi ma montre Garmin n’apparaît-elle pas immédiatement dans le Finder ou Terento ?", "De nombreuses montres Garmin récentes utilisent le MTP et peuvent ne pas apparaître comme un disque Finder classique. La détection par Terento peut prendre 1 à 2 minutes après la connexion. Gardez la montre connectée et fermez Garmin Express, OpenMTP ou toute autre application susceptible de l’utiliser."],
          ["Terento remplace-t-il Garmin Express ?", "Non. Terento se concentre sur l’installation et la gestion de cartes tierces prises en charge. Garmin Express reste utile pour les mises à jour officielles des appareils Garmin et leurs services."],
          ["Terento est-il sûr pour mes cartes Garmin existantes ?", "Oui. Les cartes Garmin existantes restent inchangées. Terento ne gère que les cartes qu’il a installées et enregistrées localement."],
          ["D’où viennent les cartes ?", "La bêta actuelle utilise Freizeitkarte comme source de cartes. Terento télécharge les cartes depuis le fournisseur d’origine vers votre Mac, puis les transfère sur votre montre."],
          ["Que dois-je faire si l’installation échoue ?", "Ouvrez une issue GitHub ou envoyez le journal de diagnostic par e-mail à <a href=\"mailto:hello@terento.app?subject=Terento%20installation%20issue\">hello@terento.app</a>. Le rapport aide à analyser l’échec sans vous demander d’inspecter manuellement les dossiers de l’appareil.", { support: true }],
          ["Terento envoie-t-il des données sur l’appareil ?", "Le partage de compatibilité est facultatif. Lorsqu’il est activé, seules des preuves d’installation minimisées sont partagées ; ni identifiants Garmin, ni numéros de série, ni chemins locaux."],
          ["Pourquoi Apple Silicon est-il requis ?", "L’actuelle bêta macOS native est conçue pour les Mac Apple Silicon sous macOS 13 ou version ultérieure."],
          ["Puis-je sauvegarder ou supprimer des cartes installées ?", "Vous pouvez sauvegarder ou supprimer dans l’application les cartes gérées par Terento. Les autres cartes restent en lecture seule."],
        ],
      },
      pl: {
        description: "Bezpłatna, otwartoźródłowa aplikacja macOS do instalowania i zarządzania mapami innych firm na zegarkach Garmin. Wymaga Apple Silicon; kompatybilność jest potwierdzana dla każdego modelu.",
        title: "Terento — Mapy innych firm dla Garmina na Macu",
        hero: "Natywna aplikacja macOS do instalowania i zarządzania mapami innych firm na zegarkach Garmin.",
        problem: "Instalowanie map innych firm nie powinno wymagać menedżerów plików, folderów urządzenia ani przestarzałych narzędzi do przesyłania.",
        installStep: "Wybierz regiony i sprawdź wcześniej zajęte miejsce.",
        install: "Wybierz regiony i sprawdź ilość miejsca potrzebnego przed instalacją.",
        manageEyebrow: "Zainstalowane mapy",
        scope: "Terento jest przeznaczone dla zegarków Garmin obsługujących mapy. Publiczna kompatybilność instalacji map innych firm jest potwierdzana dla konkretnego modelu i wariantu na podstawie rzeczywistych wyników udostępnionych przez użytkowników.",
        faq: [
          ["Jakie zegarki Garmin działają z Terento?", "Terento jest przeznaczone dla zegarków Garmin obsługujących mapy. Publiczna kompatybilność instalacji map innych firm jest potwierdzana dla konkretnego modelu i wariantu na podstawie rzeczywistych wyników udostępnionych przez użytkowników. Aktualne dowody znajdziesz na <a href=\"/pl/compatibility/\">stronie kompatybilności</a>."],
          ["Czy mogę instalować mapy innych firm na zegarku Garmin z Maca bez BaseCamp?", "Tak. Terento oferuje prowadzony, natywny dla macOS sposób instalowania obsługiwanych map innych firm bez BaseCamp i bez uniwersalnego menedżera plików MTP. Obecna beta korzysta z Freizeitkarte i wymaga Maca z Apple Silicon. <a href=\"/pl/guides/install-garmin-maps-mac/\">Przeczytaj instrukcję instalacji na Macu.</a>"],
          ["Dlaczego mój zegarek Garmin nie pojawia się od razu w Finderze ani w Terento?", "Wiele nowszych zegarków Garmin korzysta z MTP i może nie pojawiać się jako zwykły dysk w Finderze. Wykrywanie przez Terento może potrwać 1–2 minuty po podłączeniu. Pozostaw zegarek podłączony i zamknij Garmin Express, OpenMTP lub inną aplikację, która może już z niego korzystać."],
          ["Czy Terento zastępuje Garmin Express?", "Nie. Terento koncentruje się na instalowaniu i zarządzaniu obsługiwanymi mapami innych firm. Garmin Express nadal służy do oficjalnych aktualizacji urządzeń Garmin i powiązanych usług."],
          ["Czy Terento jest bezpieczne dla istniejących map Garmin?", "Tak. Istniejące mapy Garmin pozostają niezmienione. Terento zarządza tylko mapami, które zainstalowało i zapisało lokalnie."],
          ["Skąd pochodzą mapy?", "Obecna beta korzysta z Freizeitkarte jako źródła map. Terento pobiera mapy od pierwotnego dostawcy na Maca, a następnie przesyła je na zegarek."],
          ["Co zrobić, jeśli instalacja się nie powiedzie?", "Otwórz zgłoszenie na GitHubie lub wyślij log diagnostyczny e-mailem na adres <a href=\"mailto:hello@terento.app?subject=Terento%20installation%20issue\">hello@terento.app</a>. Raport pomaga zbadać problem bez ręcznego przeglądania folderów urządzenia.", { support: true }],
          ["Czy Terento wysyła dane o urządzeniu?", "Udostępnianie danych o kompatybilności jest opcjonalne. Po włączeniu wysyłane są tylko zminimalizowane dowody instalacji; bez identyfikatorów Garmin, numerów seryjnych i lokalnych ścieżek."],
          ["Dlaczego wymagany jest Apple Silicon?", "Obecna natywna beta macOS jest zbudowana dla Maców z Apple Silicon i macOS 13 lub nowszym."],
          ["Czy mogę wykonać kopię lub usunąć zainstalowane mapy?", "W aplikacji możesz wykonać kopię lub usunąć mapy zarządzane przez Terento. Pozostałe mapy pozostają tylko do odczytu."],
        ],
      },
      cs: {
        description: "Bezplatná open-source aplikace pro macOS k instalaci a správě map třetích stran na hodinkách Garmin. Vyžaduje Apple Silicon; kompatibilita se potvrzuje pro každý model.",
        title: "Terento — Mapy třetích stran pro Garmin na Macu",
        hero: "Nativní aplikace pro macOS k instalaci a správě map třetích stran na hodinkách Garmin.",
        problem: "Instalace map třetích stran by neměla vyžadovat správce souborů, složky zařízení ani zastaralé nástroje pro přenos.",
        installStep: "Vyberte oblasti a předem si prohlédněte nároky na úložiště.",
        install: "Vyberte požadované oblasti a před instalací si prohlédněte nároky na úložiště.",
        manageEyebrow: "Nainstalované mapy",
        scope: "Terento je určeno pro hodinky Garmin s podporou map. Veřejná kompatibilita instalace map třetích stran se potvrzuje pro každý přesný model a variantu na základě skutečných výsledků sdílených uživateli.",
        faq: [
          ["Které hodinky Garmin fungují s Terento?", "Terento je určeno pro hodinky Garmin s podporou map. Veřejná kompatibilita instalace map třetích stran se potvrzuje pro přesný model a variantu pomocí skutečných výsledků sdílených uživateli. Aktuální důkazy najdete na stránce <a href=\"/cs/compatibility/\">Kompatibilita</a>."],
          ["Mohu instalovat mapy třetích stran do hodinek Garmin z Macu bez BaseCamp?", "Ano. Terento nabízí řízený nativní postup pro macOS k instalaci podporovaných map třetích stran bez BaseCampu a bez univerzálního správce souborů MTP. Aktuální beta používá Freizeitkarte a vyžaduje Mac s Apple Silicon. <a href=\"/cs/guides/install-garmin-maps-mac/\">Přečtěte si instalační příručku pro Mac.</a>"],
          ["Proč se moje hodinky Garmin nezobrazí hned ve Finderu ani v Terento?", "Mnoho novějších hodinek Garmin používá MTP a nemusí se zobrazit jako běžný disk ve Finderu. Rozpoznání v Terento může po připojení trvat 1–2 minuty. Nechte hodinky připojené a zavřete Garmin Express, OpenMTP nebo jinou aplikaci, která je může právě používat."],
          ["Nahrazuje Terento Garmin Express?", "Ne. Terento se zaměřuje na instalaci a správu podporovaných map třetích stran. Garmin Express zůstává důležitý pro oficiální aktualizace zařízení Garmin a související služby."],
          ["Je Terento bezpečné pro stávající mapy Garmin?", "Ano. Stávající mapy Garmin zůstávají beze změny. Terento spravuje pouze mapy, které nainstalovalo a lokálně zaznamenalo."],
          ["Odkud mapy pocházejí?", "Aktuální beta používá Freizeitkarte jako zdroj map. Terento stáhne mapy od původního poskytovatele do Macu a poté je přenese do hodinek."],
          ["Co mám dělat, když instalace selže?", "Otevřete issue na GitHubu nebo pošlete diagnostický log e-mailem na adresu <a href=\"mailto:hello@terento.app?subject=Terento%20installation%20issue\">hello@terento.app</a>. Zpráva pomůže problém prošetřit bez ruční kontroly složek zařízení.", { support: true }],
          ["Odesílá Terento data o zařízení?", "Sdílení údajů o kompatibilitě je volitelné. Po zapnutí se sdílejí pouze minimalizované důkazy instalace; bez Garmin Unit ID, sériových čísel a místních cest."],
          ["Proč je vyžadován Apple Silicon?", "Aktuální nativní beta pro macOS je vytvořena pro Macy s Apple Silicon a macOS 13 nebo novějším."],
          ["Mohu zálohovat nebo odstranit nainstalované mapy?", "V aplikaci můžete zálohovat nebo odstranit mapy spravované Terentem. Ostatní mapy zůstávají jen pro čtení."],
        ],
      },
      it: {
        description: "Applicazione macOS gratuita e open source per installare e gestire mappe di terze parti sugli smartwatch Garmin. Apple Silicon richiesto; la compatibilità è confermata modello per modello.",
        title: "Terento — Mappe di terze parti per Garmin su Mac",
        hero: "Un’app macOS nativa per installare e gestire mappe di terze parti sugli smartwatch Garmin.",
        problem: "Installare mappe di terze parti non dovrebbe richiedere file manager, cartelle del dispositivo o strumenti di trasferimento obsoleti.",
        installStep: "Scegli le regioni e visualizza lo spazio necessario prima dell’installazione.",
        install: "Scegli le regioni desiderate e visualizza lo spazio necessario prima dell’installazione.",
        manageEyebrow: "Mappe installate",
        scope: "Terento è progettato per gli smartwatch Garmin con supporto alle mappe. La compatibilità pubblica per l’installazione di mappe di terze parti viene confermata per ogni modello e variante sulla base di risultati reali condivisi dagli utenti.",
        faq: [
          ["Quali smartwatch Garmin funzionano con Terento?", "Terento è progettato per gli smartwatch Garmin con supporto alle mappe. La compatibilità pubblica per l’installazione di mappe di terze parti viene confermata per ogni modello e variante sulla base di risultati reali condivisi dagli utenti. Consulta la pagina <a href=\"/it/compatibility/\">Compatibilità</a> per le prove aggiornate."],
          ["Posso installare mappe di terze parti su uno smartwatch Garmin da un Mac senza BaseCamp?", "Sì. Terento offre un flusso nativo guidato per macOS per installare mappe di terze parti supportate, senza BaseCamp né un file manager MTP generico. La beta attuale usa Freizeitkarte e richiede un Mac Apple Silicon. <a href=\"/it/guides/install-garmin-maps-mac/\">Leggi la guida all’installazione su Mac.</a>"],
          ["Perché il mio smartwatch Garmin non appare subito nel Finder o in Terento?", "Molti smartwatch Garmin recenti usano MTP e potrebbero non apparire come una normale unità del Finder. Il rilevamento di Terento può richiedere 1–2 minuti dopo il collegamento. Lascia l’orologio collegato e chiudi Garmin Express, OpenMTP o un’altra app che potrebbe già utilizzarlo."],
          ["Terento sostituisce Garmin Express?", "No. Terento si concentra sull’installazione e la gestione di mappe di terze parti supportate. Garmin Express resta utile per gli aggiornamenti ufficiali dei dispositivi Garmin e per i relativi servizi."],
          ["Terento è sicuro per le mappe Garmin esistenti?", "Sì. Le mappe Garmin esistenti restano invariate. Terento gestisce solo le mappe che ha installato e registrato localmente."],
          ["Da dove provengono le mappe?", "La beta attuale usa Freizeitkarte come fonte delle mappe. Terento scarica le mappe dal provider originale sul Mac, poi le trasferisce sullo smartwatch."],
          ["Cosa devo fare se l’installazione non riesce?", "Apri una issue su GitHub oppure invia il log diagnostico via e-mail a <a href=\"mailto:hello@terento.app?subject=Terento%20installation%20issue\">hello@terento.app</a>. Il report aiuta a esaminare il problema senza dover controllare manualmente le cartelle del dispositivo.", { support: true }],
          ["Terento carica dati sul dispositivo?", "La condivisione della compatibilità è facoltativa. Se attivata, vengono condivise solo prove di installazione minimizzate; non vengono inviati ID Garmin, numeri di serie o percorsi locali."],
          ["Perché è richiesto Apple Silicon?", "L’attuale beta macOS nativa è realizzata per Mac Apple Silicon con macOS 13 o versioni successive."],
          ["Posso eseguire il backup o rimuovere le mappe installate?", "Nell’app puoi eseguire il backup o rimuovere le mappe gestite da Terento. Le altre mappe restano di sola lettura."],
        ],
      },
    },
    download: {
      de: { title: "Terento für Mac herunterladen — Drittanbieter-Karten für Garmin", description: "Lade die kostenlose, notarielle Terento-Beta für Apple-Silicon-Macs herunter, um Drittanbieter-Karten auf kompatiblen Garmin-Smartwatches zu installieren und zu verwalten.", intro: "Eine notarierte native macOS-Beta zum Installieren und Verwalten von Drittanbieter-Karten auf Garmin-Smartwatches.", requirement: "Apple-Silicon-Mac erforderlich.", requirements: ["macOS 13 oder neuer", "Apple-Silicon-Mac", "Garmin-Smartwatch mit Kartenunterstützung", "Freizeitkarte ist die Kartenquelle in der aktuellen Beta."], status: "Dies ist eine Pre-Release-Beta. Die Kompatibilität wird für jedes Modell bestätigt.", included: ["Native macOS-App", "Sichere Karteninstallation und -entfernung", "Freizeitkarte-Katalog", "Lokale Installationsdaten"] },
      fr: { title: "Télécharger Terento pour Mac — Cartes tierces pour Garmin", description: "Téléchargez la bêta Terento gratuite et notariée pour Mac Apple Silicon afin d’installer et de gérer des cartes tierces sur les montres Garmin compatibles.", intro: "Une bêta macOS native et notariée pour installer et gérer des cartes tierces sur les montres Garmin.", requirement: "Mac Apple Silicon requis.", requirements: ["macOS 13 ou version ultérieure", "Mac Apple Silicon", "Montre Garmin compatible avec les cartes", "Freizeitkarte est la source de cartes de la bêta actuelle."], status: "Il s’agit d’une bêta pré-release. La compatibilité est confirmée modèle par modèle.", included: ["Application macOS native", "Installation et suppression sûres des cartes", "Catalogue Freizeitkarte", "Enregistrements locaux des installations"] },
      pl: { title: "Pobierz Terento na Maca — Mapy innych firm dla Garmina", description: "Pobierz bezpłatną, notaryzowaną betę Terento na Maci z Apple Silicon, aby instalować i zarządzać mapami innych firm na zgodnych zegarkach Garmin.", intro: "Notaryzowana natywna beta macOS do instalowania i zarządzania mapami innych firm na zegarkach Garmin.", requirement: "Wymaga Maca z Apple Silicon.", requirements: ["macOS 13 lub nowszy", "Mac z Apple Silicon", "Zegarek Garmin obsługujący mapy", "Freizeitkarte jest źródłem map w obecnej becie."], status: "To wersja beta przed wydaniem. Kompatybilność jest potwierdzana dla każdego modelu.", included: ["Natywna aplikacja macOS", "Bezpieczna instalacja i usuwanie map", "Katalog Freizeitkarte", "Lokalne dane instalacji"] },
      cs: { title: "Stáhnout Terento pro Mac — Mapy třetích stran pro Garmin", description: "Stáhněte si bezplatnou, notářsky ověřenou betu Terento pro Macy s Apple Silicon k instalaci a správě map třetích stran na kompatibilních hodinkách Garmin.", intro: "Notářsky ověřená nativní beta pro macOS k instalaci a správě map třetích stran na hodinkách Garmin.", requirement: "Vyžaduje Mac s Apple Silicon.", requirements: ["macOS 13 nebo novější", "Mac s Apple Silicon", "Hodinky Garmin s podporou map", "Freizeitkarte je zdrojem map v aktuální betě."], status: "Jde o předběžnou betu. Kompatibilita se potvrzuje pro každý model.", included: ["Nativní aplikace pro macOS", "Bezpečná instalace a odstraňování map", "Katalog Freizeitkarte", "Místní záznamy instalace"] },
      it: { title: "Scarica Terento per Mac — Mappe di terze parti per Garmin", description: "Scarica la beta gratuita e notarizzata di Terento per Mac Apple Silicon per installare e gestire mappe di terze parti sugli smartwatch Garmin compatibili.", intro: "Una beta nativa per macOS, notarizzata, per installare e gestire mappe di terze parti sugli smartwatch Garmin.", requirement: "È richiesto un Mac Apple Silicon.", requirements: ["macOS 13 o versioni successive", "Mac Apple Silicon", "Smartwatch Garmin con supporto mappe", "Freizeitkarte è la fonte delle mappe nella beta attuale."], status: "Questa è una beta pre-release. La compatibilità viene confermata modello per modello.", included: ["App macOS nativa", "Installazione e rimozione sicure delle mappe", "Catalogo Freizeitkarte", "Registri locali delle installazioni"] },
    },
  };

  const faqSupportLabels = {
    de: ["Issue öffnen", "Log per E-Mail senden"],
    fr: ["Ouvrir une issue", "Envoyer le journal"],
    pl: ["Otwórz zgłoszenie", "Wyślij log e-mailem"],
    cs: ["Otevřít issue", "Poslat log e-mailem"],
    it: ["Apri una issue", "Invia il log"],
  };

  const language = (document.documentElement.lang || "en").split("-")[0];
  const meta = (name, value, property = false) => document.querySelector(`${property ? "meta[property" : "meta[name"}="${name}"]`)?.setAttribute("content", value);
  const updateMeta = (copy) => {
    document.title = copy.title;
    meta("description", copy.description);
    meta("og:title", copy.title, true);
    meta("og:description", copy.description, true);
    meta("twitter:title", copy.title);
    meta("twitter:description", copy.description);
  };

  function updateHome(copy) {
    updateMeta(copy);
    const text = (selector, value) => { const element = document.querySelector(selector); if (element) element.textContent = value; };
    text(".hero-lede", copy.hero);
    text(".problem-statement p:first-child", copy.problem);
    text(".steps .step:nth-child(2) > p:last-child", copy.installStep);
    text("#install-maps-title + p", copy.install);
    text("#manage-maps-title", document.querySelector("#manage-maps-title")?.textContent || "");
    const manageEyebrow = document.querySelector("#manage-maps-title")?.previousElementSibling;
    if (manageEyebrow) manageEyebrow.textContent = copy.manageEyebrow;
    text(".scope-copy", copy.scope);
    document.querySelector(".scope-link")?.setAttribute("href", `/${language}/compatibility/`);
    const faqList = document.querySelector("#faq .faq-list");
    const faqActions = (options = {}) => {
      if (!options.support) return "";
      const [issueLabel, emailLabel] = faqSupportLabels[language] || ["Open an issue", "Email the log"];
      return `<div class="faq-support-actions"><a class="text-link" href="https://github.com/VooZ2/terento/issues" target="_blank" rel="noopener noreferrer" data-umami-event="support-link-click" data-umami-event-location="home-faq-install-failed" data-umami-event-channel="github-issue">${issueLabel} <span aria-hidden="true">→</span></a><a class="text-link" href="mailto:hello@terento.app?subject=Terento%20installation%20issue" data-umami-event="support-link-click" data-umami-event-location="home-faq-install-failed" data-umami-event-channel="email">${emailLabel} <span aria-hidden="true">→</span></a></div>`;
    };
    if (faqList) faqList.innerHTML = copy.faq.map(([question, answer, options]) => `<details><summary>${question}</summary><p>${answer}</p>${faqActions(options)}</details>`).join("");
    const ld = [...document.querySelectorAll('script[type="application/ld+json"]')][0];
    if (ld) {
      try {
        const data = JSON.parse(ld.textContent);
        const graph = data["@graph"] || [];
        graph.find((item) => item["@type"] === "SoftwareApplication").description = copy.description;
        graph.find((item) => item["@type"] === "WebSite").description = copy.description;
        const faq = graph.find((item) => item["@type"] === "FAQPage");
        faq.mainEntity = copy.faq.map(([question, answer]) => ({ "@type": "Question", name: question, acceptedAnswer: { "@type": "Answer", text: answer.replace(/<[^>]+>/g, "") } }));
        ld.textContent = JSON.stringify(data, null, 2);
      } catch { /* static JSON-LD remains available if a browser blocks mutation */ }
    }
  }

  function updateDownload(copy) {
    updateMeta(copy);
    const text = (selector, value) => { const element = document.querySelector(selector); if (element) element.textContent = value; };
    text(".download-intro", copy.intro);
    let requirement = document.querySelector(".download-requirement");
    if (!requirement) {
      requirement = document.createElement("p");
      requirement.className = "download-requirement";
      document.querySelector(".download-intro")?.after(requirement);
    }
    text(".download-requirement", copy.requirement);
    document.querySelector(".download-compatibility-link")?.setAttribute("href", `/${language}/compatibility/`);
    const sections = [...document.querySelectorAll(".download-item")];
    if (sections[0]) sections[0].querySelector("ul")?.replaceChildren(...copy.requirements.map((item) => { const li = document.createElement("li"); li.textContent = item; return li; }));
    if (sections[1]) textFrom(sections[1], copy.status);
    if (sections[2]) sections[2].querySelector("p")?.replaceChildren(...copy.included.map((item, index) => { const span = document.createElement(index ? "span" : "span"); span.textContent = `${index ? " · " : ""}${item}`; return span; }));
    const ld = [...document.querySelectorAll('script[type="application/ld+json"]')][0];
    if (ld) { try { const data = JSON.parse(ld.textContent); data.description = copy.description; data["@type"] === "SoftwareApplication" && (data.description = copy.description); ld.textContent = JSON.stringify(data, null, 2); } catch { /* keep static JSON-LD */ } }
  }

  function textFrom(section, value) {
    const paragraph = section.querySelector("p");
    if (paragraph) paragraph.textContent = value;
  }

  const isDownload = /\/download\/?$/.test(window.location.pathname);
  if (!isDownload && translations[language]?.home) updateHome(translations[language].home);
  if (isDownload && translations.download[language]) updateDownload(translations.download[language]);
})();
