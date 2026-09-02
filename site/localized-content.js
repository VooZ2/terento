(() => {
  const translations = {
    de: {
      home: {
        description: "Kostenlose Open-Source-macOS-App zum Installieren und Verwalten von Drittanbieter-Karten auf Garmin-Smartwatches. Apple Silicon erforderlich; die Kompatibilität wird für jedes Modell bestätigt.",
        title: "Terento — Drittanbieter-Karten für Garmin auf dem Mac",
        hero: "Eine native macOS-App zum Installieren und Verwalten von Drittanbieter-Karten auf Garmin-Smartwatches.",
        problem: "Die Installation von Drittanbieter-Karten sollte keine Dateimanager, Geräteordner oder veralteten Übertragungstools erfordern.",
        installStep: "Wähle eine Karte und sieh vorher, wie viel Speicher benötigt wird.",
        install: "Wähle eine Karte und sieh vor der Installation, wie viel Speicher benötigt wird.",
        manageEyebrow: "Installierte Karten",
        manage: "Sieh, was installiert ist, aktualisiere Karten, wenn eine neuere Version verfügbar ist, und entferne unterstützte Drittanbieter-Karten sicher. Garmin- und Systemkarten bleiben geschützt.",
        scopeProvider: "Kartenanbieter",
        scopeProviderDescription: "Die Unterstützung wächst mit jeder Beta.",
        installAlt: "Terento zeigt Drittanbieter-Kartenanbieter und Regionen auf macOS",
        manageAlt: "Terento zeigt installierte Drittanbieter-Karten nach Anbieter gruppiert",
        scope: "Terento ist für Garmin-Smartwatches mit Kartenunterstützung konzipiert. Die öffentliche Kompatibilität für die Installation von Drittanbieter-Karten wird für jedes genaue Modell und jede Variante anhand echter, von Nutzern geteilter Ergebnisse bestätigt.",
        faq: [
          ["Welche Garmin-Uhren funktionieren mit Terento?", "Terento ist für Garmin-Smartwatches mit Kartenunterstützung konzipiert. Die öffentliche Kompatibilität für die Installation von Drittanbieter-Karten wird für jedes genaue Modell und jede Variante anhand echter, von Nutzern geteilter Ergebnisse bestätigt. Auf der <a href=\"/de/compatibility/\">Kompatibilitätsseite</a> findest du die aktuellen Nachweise."],
          ["Kann ich Drittanbieter-Karten von einem Mac ohne BaseCamp auf einer Garmin-Uhr installieren?", "Ja. Terento bietet einen geführten nativen macOS-Ablauf zum Installieren unterstützter Drittanbieter-Karten ohne BaseCamp oder einen allgemeinen MTP-Dateimanager. Du kannst auch eine unterstützte Drittanbieter-.img-Karte von deinem Mac importieren. Apple Silicon ist erforderlich. <a href=\"/de/guides/install-garmin-maps-mac/\">Lies die vollständige Mac-Installationsanleitung.</a>"],
          ["Warum erscheint meine Garmin-Uhr nicht sofort im Finder oder in Terento?", "Viele neuere Garmin-Uhren verwenden MTP und erscheinen möglicherweise nicht als normales Finder-Laufwerk. Die Erkennung durch Terento kann nach dem Verbinden 1–2 Minuten dauern. Lass die Uhr verbunden und schließe Garmin Express, OpenMTP oder eine andere App, die sie bereits verwenden könnte."],
          ["Ersetzt Terento Garmin Express?", "Nein. Terento konzentriert sich auf die Installation und Verwaltung unterstützter Drittanbieter-Karten. Garmin Express bleibt für offizielle Garmin-Geräteupdates und Dienste relevant."],
          ["Ist Terento sicher für vorhandene Garmin-Karten?", "Ja. Garmin- und Systemkarten bleiben geschützt. Terento aktualisiert oder entfernt unterstützte Drittanbieter-Karten nur durch ausdrücklich bestätigte und geprüfte Aktionen."],
          ["Welche Drittanbieter-Kartenanbieter unterstützt Terento?", "Terento beta.9 unterstützt Drittanbieter-Karten von Freizeitkarte und OpenTopoMap. Die Liste der Anbieter soll mit künftigen Beta-Versionen wachsen. Die Karten werden direkt vom jeweiligen Originalanbieter auf deinen Mac geladen und anschließend auf deine Uhr übertragen; Terento hostet oder verpackt die Kartendateien nicht neu."],
          ["Was soll ich tun, wenn die Installation fehlschlägt?", "Öffne ein GitHub-Issue oder sende das Diagnoseprotokoll per E-Mail an <a href=\"mailto:hello@terento.app?subject=Terento%20installation%20issue\">hello@terento.app</a>. Der Bericht hilft bei der Untersuchung des Fehlers, ohne dass du Geräteordner manuell prüfen musst.", { support: true }],
          ["Lädt Terento Gerätedaten hoch?", "Das Teilen von Kompatibilitätsdaten ist optional. Wenn aktiviert, werden nur datensparsame Installationsnachweise geteilt; Garmin-Unit-IDs, Seriennummern und lokale Pfade nicht."],
          ["Warum ist Apple Silicon erforderlich?", "Die aktuelle native macOS-Beta ist für Apple-Silicon-Macs mit macOS 13 oder neuer gebaut."],
          ["Kann ich installierte Karten aktualisieren oder entfernen?", "Du kannst von Terento verwaltete Karten aktualisieren, wenn eine neuere Version des Anbieters verfügbar ist, und unterstützte Drittanbieter-Karten sicher in der App entfernen. Garmin- und Systemkarten bleiben geschützt."],
        ],
      },
      fr: {
        description: "Application macOS gratuite et open source pour installer et gérer des cartes tierces sur les montres Garmin. Apple Silicon requis ; la compatibilité est confirmée modèle par modèle.",
        title: "Terento — Cartes tierces pour Garmin sur Mac",
        hero: "Une application macOS native pour installer et gérer des cartes tierces sur les montres Garmin.",
        problem: "Installer des cartes tierces ne devrait pas nécessiter de gestionnaire de fichiers, de dossiers d’appareil ni d’outils de transfert obsolètes.",
        installStep: "Choisissez une carte et consultez l’espace nécessaire avant l’installation.",
        install: "Choisissez une carte et consultez l’espace nécessaire avant l’installation.",
        manageEyebrow: "Cartes installées",
        manage: "Consultez les cartes installées, mettez-les à jour lorsqu’une version plus récente est disponible et supprimez en toute sécurité les cartes tierces prises en charge. Les cartes Garmin et système restent protégées.",
        scopeProvider: "Fournisseurs de cartes",
        scopeProviderDescription: "La prise en charge s’élargit à chaque bêta.",
        installAlt: "Terento affiche les fournisseurs et les régions de cartes tierces sur macOS",
        manageAlt: "Terento affiche les cartes tierces installées, regroupées par fournisseur",
        scope: "Terento est conçu pour les montres Garmin compatibles avec les cartes. La compatibilité publique pour l’installation de cartes tierces est confirmée pour chaque modèle et chaque variante grâce à des résultats réels partagés par les utilisateurs.",
        faq: [
          ["Quelles montres Garmin fonctionnent avec Terento ?", "Terento est conçu pour les montres connectées Garmin compatibles avec les cartes. La compatibilité publique pour l’installation de cartes tierces est confirmée pour chaque modèle et chaque variante grâce aux résultats réels partagés par les utilisateurs. Consultez la <a href=\"/fr/compatibility/\">page Compatibilité</a> pour voir les preuves actuelles."],
          ["Puis-je installer des cartes tierces sur une montre Garmin depuis un Mac sans BaseCamp ?", "Oui. Terento propose un parcours macOS natif guidé pour installer des cartes tierces prises en charge, sans BaseCamp ni gestionnaire MTP généraliste. Vous pouvez aussi importer une carte .img tierce prise en charge depuis votre Mac. Apple Silicon est requis. <a href=\"/fr/guides/install-garmin-maps-mac/\">Lisez le guide d’installation sur Mac.</a>"],
          ["Pourquoi ma montre Garmin n’apparaît-elle pas immédiatement dans le Finder ou Terento ?", "De nombreuses montres Garmin récentes utilisent le MTP et peuvent ne pas apparaître comme un disque Finder classique. La détection par Terento peut prendre 1 à 2 minutes après la connexion. Gardez la montre connectée et fermez Garmin Express, OpenMTP ou toute autre application susceptible de l’utiliser."],
          ["Terento remplace-t-il Garmin Express ?", "Non. Terento se concentre sur l’installation et la gestion de cartes tierces prises en charge. Garmin Express reste utile pour les mises à jour officielles des appareils Garmin et leurs services."],
          ["Terento est-il sûr pour mes cartes Garmin existantes ?", "Oui. Les cartes Garmin et système restent protégées. Terento ne met à jour ou ne supprime les cartes tierces prises en charge qu’au moyen d’actions explicites et validées."],
          ["Quels fournisseurs de cartes tierces Terento prend-il en charge ?", "La bêta 9 de Terento prend en charge les cartes tierces de Freizeitkarte et d’OpenTopoMap. La liste des fournisseurs est conçue pour s’élargir avec les prochaines versions bêta. Les cartes sont téléchargées directement depuis le fournisseur d’origine vers votre Mac, puis transférées sur votre montre ; Terento n’héberge pas et ne reconditionne pas les fichiers cartographiques."],
          ["Que dois-je faire si l’installation échoue ?", "Ouvrez une issue GitHub ou envoyez le journal de diagnostic par e-mail à <a href=\"mailto:hello@terento.app?subject=Terento%20installation%20issue\">hello@terento.app</a>. Le rapport aide à analyser l’échec sans vous demander d’inspecter manuellement les dossiers de l’appareil.", { support: true }],
          ["Terento envoie-t-il des données sur l’appareil ?", "Le partage de compatibilité est facultatif. Lorsqu’il est activé, seules des preuves d’installation minimisées sont partagées ; ni identifiants Garmin, ni numéros de série, ni chemins locaux."],
          ["Pourquoi Apple Silicon est-il requis ?", "L’actuelle bêta macOS native est conçue pour les Mac Apple Silicon sous macOS 13 ou version ultérieure."],
          ["Puis-je mettre à jour ou supprimer des cartes installées ?", "Vous pouvez mettre à jour les cartes gérées par Terento lorsqu’une version plus récente du fournisseur est disponible et supprimer en toute sécurité les cartes tierces prises en charge dans l’application. Les cartes Garmin et système restent protégées."],
        ],
      },
      pl: {
        description: "Bezpłatna, otwartoźródłowa aplikacja macOS do instalowania i zarządzania mapami innych firm na zegarkach Garmin. Wymaga Apple Silicon; kompatybilność jest potwierdzana dla każdego modelu.",
        title: "Terento — Mapy innych firm dla Garmina na Macu",
        hero: "Natywna aplikacja macOS do instalowania i zarządzania mapami innych firm na zegarkach Garmin.",
        problem: "Instalowanie map innych firm nie powinno wymagać menedżerów plików, folderów urządzenia ani przestarzałych narzędzi do przesyłania.",
        installStep: "Wybierz mapę i sprawdź wcześniej potrzebne miejsce.",
        install: "Wybierz mapę i sprawdź przed instalacją, ile miejsca zajmie.",
        manageEyebrow: "Zainstalowane mapy",
        manage: "Sprawdź, co jest zainstalowane, aktualizuj mapy, gdy dostępne są nowsze wydania, i bezpiecznie usuwaj obsługiwane mapy innych firm. Mapy Garmin i systemowe pozostają chronione.",
        scopeProvider: "Dostawcy map",
        scopeProviderDescription: "Wsparcie rośnie z każdą betą.",
        installAlt: "Terento pokazuje dostawców i regiony map innych firm na macOS",
        manageAlt: "Terento pokazuje zainstalowane mapy innych firm pogrupowane według dostawcy",
        scope: "Terento jest przeznaczone dla zegarków Garmin obsługujących mapy. Publiczna kompatybilność instalacji map innych firm jest potwierdzana dla konkretnego modelu i wariantu na podstawie rzeczywistych wyników udostępnionych przez użytkowników.",
        faq: [
          ["Jakie zegarki Garmin działają z Terento?", "Terento jest przeznaczone dla zegarków Garmin obsługujących mapy. Publiczna kompatybilność instalacji map innych firm jest potwierdzana dla konkretnego modelu i wariantu na podstawie rzeczywistych wyników udostępnionych przez użytkowników. Aktualne dowody znajdziesz na <a href=\"/pl/compatibility/\">stronie kompatybilności</a>."],
          ["Czy mogę instalować mapy innych firm na zegarku Garmin z Maca bez BaseCamp?", "Tak. Terento oferuje prowadzony, natywny dla macOS sposób instalowania obsługiwanych map innych firm bez BaseCamp i bez uniwersalnego menedżera plików MTP. Możesz też zaimportować obsługiwaną mapę .img innej firmy z Maca. Wymagany jest Apple Silicon. <a href=\"/pl/guides/install-garmin-maps-mac/\">Przeczytaj instrukcję instalacji na Macu.</a>"],
          ["Dlaczego mój zegarek Garmin nie pojawia się od razu w Finderze ani w Terento?", "Wiele nowszych zegarków Garmin korzysta z MTP i może nie pojawiać się jako zwykły dysk w Finderze. Wykrywanie przez Terento może potrwać 1–2 minuty po podłączeniu. Pozostaw zegarek podłączony i zamknij Garmin Express, OpenMTP lub inną aplikację, która może już z niego korzystać."],
          ["Czy Terento zastępuje Garmin Express?", "Nie. Terento koncentruje się na instalowaniu i zarządzaniu obsługiwanymi mapami innych firm. Garmin Express nadal służy do oficjalnych aktualizacji urządzeń Garmin i powiązanych usług."],
          ["Czy Terento jest bezpieczne dla istniejących map Garmin?", "Tak. Mapy Garmin i systemowe pozostają chronione. Terento aktualizuje lub usuwa obsługiwane mapy innych firm wyłącznie w wyniku wyraźnych, sprawdzonych działań."],
          ["Których dostawców map innych firm obsługuje Terento?", "Terento beta 9 obsługuje mapy innych firm od Freizeitkarte i OpenTopoMap. Lista dostawców ma rozszerzać się w kolejnych wersjach beta. Mapy są pobierane bezpośrednio od pierwotnego dostawcy na Maca, a następnie przesyłane na zegarek; Terento nie hostuje ani nie przepakowuje plików map."],
          ["Co zrobić, jeśli instalacja się nie powiedzie?", "Otwórz zgłoszenie na GitHubie lub wyślij log diagnostyczny e-mailem na adres <a href=\"mailto:hello@terento.app?subject=Terento%20installation%20issue\">hello@terento.app</a>. Raport pomaga zbadać problem bez ręcznego przeglądania folderów urządzenia.", { support: true }],
          ["Czy Terento wysyła dane o urządzeniu?", "Udostępnianie danych o kompatybilności jest opcjonalne. Po włączeniu wysyłane są tylko zminimalizowane dowody instalacji; bez identyfikatorów Garmin, numerów seryjnych i lokalnych ścieżek."],
          ["Dlaczego wymagany jest Apple Silicon?", "Obecna natywna beta macOS jest zbudowana dla Maców z Apple Silicon i macOS 13 lub nowszym."],
          ["Czy mogę aktualizować lub usuwać zainstalowane mapy?", "Możesz aktualizować mapy zarządzane przez Terento, gdy dostępne jest nowsze wydanie dostawcy, oraz bezpiecznie usuwać obsługiwane mapy innych firm w aplikacji. Mapy Garmin i systemowe pozostają chronione."],
        ],
      },
      cs: {
        description: "Bezplatná open-source aplikace pro macOS k instalaci a správě map třetích stran na hodinkách Garmin. Vyžaduje Apple Silicon; kompatibilita se potvrzuje pro každý model.",
        title: "Terento — Mapy třetích stran pro Garmin na Macu",
        hero: "Nativní aplikace pro macOS k instalaci a správě map třetích stran na hodinkách Garmin.",
        problem: "Instalace map třetích stran by neměla vyžadovat správce souborů, složky zařízení ani zastaralé nástroje pro přenos.",
        installStep: "Vyberte mapu a předem si prohlédněte nároky na úložiště.",
        install: "Vyberte mapu a před instalací si prohlédněte nároky na úložiště.",
        manageEyebrow: "Nainstalované mapy",
        manage: "Prohlédněte si nainstalované mapy, aktualizujte je, když je k dispozici novější vydání, a bezpečně odstraňujte podporované mapy třetích stran. Garmin a systémové mapy zůstávají chráněné.",
        scopeProvider: "Poskytovatelé map",
        scopeProviderDescription: "Podpora se rozšiřuje s každou betou.",
        installAlt: "Terento zobrazuje poskytovatele a oblasti map třetích stran v macOS",
        manageAlt: "Terento zobrazuje nainstalované mapy třetích stran seskupené podle poskytovatele",
        scope: "Terento je určeno pro hodinky Garmin s podporou map. Veřejná kompatibilita instalace map třetích stran se potvrzuje pro každý přesný model a variantu na základě skutečných výsledků sdílených uživateli.",
        faq: [
          ["Které hodinky Garmin fungují s Terento?", "Terento je určeno pro hodinky Garmin s podporou map. Veřejná kompatibilita instalace map třetích stran se potvrzuje pro přesný model a variantu pomocí skutečných výsledků sdílených uživateli. Aktuální důkazy najdete na stránce <a href=\"/cs/compatibility/\">Kompatibilita</a>."],
          ["Mohu instalovat mapy třetích stran do hodinek Garmin z Macu bez BaseCamp?", "Ano. Terento nabízí řízený nativní postup pro macOS k instalaci podporovaných map třetích stran bez BaseCampu a bez univerzálního správce souborů MTP. Můžete také přímo z Macu importovat podporovanou mapu .img třetí strany. Je vyžadován Apple Silicon. <a href=\"/cs/guides/install-garmin-maps-mac/\">Přečtěte si instalační příručku pro Mac.</a>"],
          ["Proč se moje hodinky Garmin nezobrazí hned ve Finderu ani v Terento?", "Mnoho novějších hodinek Garmin používá MTP a nemusí se zobrazit jako běžný disk ve Finderu. Rozpoznání v Terento může po připojení trvat 1–2 minuty. Nechte hodinky připojené a zavřete Garmin Express, OpenMTP nebo jinou aplikaci, která je může právě používat."],
          ["Nahrazuje Terento Garmin Express?", "Ne. Terento se zaměřuje na instalaci a správu podporovaných map třetích stran. Garmin Express zůstává důležitý pro oficiální aktualizace zařízení Garmin a související služby."],
          ["Je Terento bezpečné pro stávající mapy Garmin?", "Ano. Garmin a systémové mapy zůstávají chráněné. Terento aktualizuje nebo odstraňuje podporované mapy třetích stran pouze pomocí výslovných a ověřených akcí."],
          ["Které poskytovatele map třetích stran Terento podporuje?", "Terento beta 9 podporuje mapy třetích stran od poskytovatelů Freizeitkarte a OpenTopoMap. Seznam poskytovatelů se má rozšiřovat s dalšími beta verzemi. Mapy se stahují přímo od původního poskytovatele do vašeho Macu a poté se přenášejí do hodinek; Terento mapové soubory nehostuje ani nepřebaluje."],
          ["Co mám dělat, když instalace selže?", "Otevřete issue na GitHubu nebo pošlete diagnostický log e-mailem na adresu <a href=\"mailto:hello@terento.app?subject=Terento%20installation%20issue\">hello@terento.app</a>. Zpráva pomůže problém prošetřit bez ruční kontroly složek zařízení.", { support: true }],
          ["Odesílá Terento data o zařízení?", "Sdílení údajů o kompatibilitě je volitelné. Po zapnutí se sdílejí pouze minimalizované důkazy instalace; bez Garmin Unit ID, sériových čísel a místních cest."],
          ["Proč je vyžadován Apple Silicon?", "Aktuální nativní beta pro macOS je vytvořena pro Macy s Apple Silicon a macOS 13 nebo novějším."],
          ["Mohu aktualizovat nebo odstranit nainstalované mapy?", "Mapy spravované Terentem můžete aktualizovat, když je k dispozici novější vydání od poskytovatele, a v aplikaci bezpečně odstranit podporované mapy třetích stran. Garmin a systémové mapy zůstávají chráněné."],
        ],
      },
      it: {
        description: "Applicazione macOS gratuita e open source per installare e gestire mappe di terze parti sugli smartwatch Garmin. Apple Silicon richiesto; la compatibilità è confermata modello per modello.",
        title: "Terento — Mappe di terze parti per Garmin su Mac",
        hero: "Un’app macOS nativa per installare e gestire mappe di terze parti sugli smartwatch Garmin.",
        problem: "Installare mappe di terze parti non dovrebbe richiedere file manager, cartelle del dispositivo o strumenti di trasferimento obsoleti.",
        installStep: "Scegli una mappa e visualizza lo spazio necessario prima dell’installazione.",
        install: "Scegli una mappa e visualizza lo spazio necessario prima dell’installazione.",
        manageEyebrow: "Mappe installate",
        manage: "Visualizza le mappe installate, aggiornatele quando è disponibile una versione più recente e rimuovi in sicurezza le mappe di terze parti supportate. Le mappe Garmin e di sistema restano protette.",
        scopeProvider: "Provider di mappe",
        scopeProviderDescription: "Il supporto cresce con ogni beta.",
        installAlt: "Terento mostra provider e regioni di mappe di terze parti su macOS",
        manageAlt: "Terento mostra le mappe di terze parti installate raggruppate per provider",
        scope: "Terento è progettato per gli smartwatch Garmin con supporto alle mappe. La compatibilità pubblica per l’installazione di mappe di terze parti viene confermata per ogni modello e variante sulla base di risultati reali condivisi dagli utenti.",
        faq: [
          ["Quali smartwatch Garmin funzionano con Terento?", "Terento è progettato per gli smartwatch Garmin con supporto alle mappe. La compatibilità pubblica per l’installazione di mappe di terze parti viene confermata per ogni modello e variante sulla base di risultati reali condivisi dagli utenti. Consulta la pagina <a href=\"/it/compatibility/\">Compatibilità</a> per le prove aggiornate."],
          ["Posso installare mappe di terze parti su uno smartwatch Garmin da un Mac senza BaseCamp?", "Sì. Terento offre un flusso nativo guidato per macOS per installare mappe di terze parti supportate, senza BaseCamp né un file manager MTP generico. Puoi anche importare dal Mac una mappa .img di terze parti supportata. È richiesto Apple Silicon. <a href=\"/it/guides/install-garmin-maps-mac/\">Leggi la guida all’installazione su Mac.</a>"],
          ["Perché il mio smartwatch Garmin non appare subito nel Finder o in Terento?", "Molti smartwatch Garmin recenti usano MTP e potrebbero non apparire come una normale unità del Finder. Il rilevamento di Terento può richiedere 1–2 minuti dopo il collegamento. Lascia l’orologio collegato e chiudi Garmin Express, OpenMTP o un’altra app che potrebbe già utilizzarlo."],
          ["Terento sostituisce Garmin Express?", "No. Terento si concentra sull’installazione e la gestione di mappe di terze parti supportate. Garmin Express resta utile per gli aggiornamenti ufficiali dei dispositivi Garmin e per i relativi servizi."],
          ["Terento è sicuro per le mappe Garmin esistenti?", "Sì. Le mappe Garmin e di sistema restano protette. Terento aggiorna o rimuove le mappe di terze parti supportate solo tramite azioni esplicite e convalidate."],
          ["Quali provider di mappe di terze parti supporta Terento?", "Terento beta 9 supporta mappe di terze parti da Freizeitkarte e OpenTopoMap. L’elenco dei provider è pensato per crescere con le future versioni beta. Le mappe vengono scaricate direttamente dal provider originale sul Mac e poi trasferite sullo smartwatch; Terento non ospita né riconfeziona i file delle mappe."],
          ["Cosa devo fare se l’installazione non riesce?", "Apri una issue su GitHub oppure invia il log diagnostico via e-mail a <a href=\"mailto:hello@terento.app?subject=Terento%20installation%20issue\">hello@terento.app</a>. Il report aiuta a esaminare il problema senza dover controllare manualmente le cartelle del dispositivo.", { support: true }],
          ["Terento carica dati sul dispositivo?", "La condivisione della compatibilità è facoltativa. Se attivata, vengono condivise solo prove di installazione minimizzate; non vengono inviati ID Garmin, numeri di serie o percorsi locali."],
          ["Perché è richiesto Apple Silicon?", "L’attuale beta macOS nativa è realizzata per Mac Apple Silicon con macOS 13 o versioni successive."],
          ["Posso aggiornare o rimuovere le mappe installate?", "Puoi aggiornare le mappe gestite da Terento quando è disponibile una versione più recente del provider e rimuovere in sicurezza dall’app le mappe di terze parti supportate. Le mappe Garmin e di sistema restano protette."],
        ],
      },
    },
    download: {
      de: { title: "Terento für Mac herunterladen — Drittanbieter-Karten für Garmin", description: "Lade die kostenlose, notarielle Terento-Beta für Apple-Silicon-Macs herunter, um Drittanbieter-Karten auf kompatiblen Garmin-Smartwatches zu installieren und zu verwalten.", intro: "Eine notarierte native macOS-Beta zum Installieren und Verwalten von Drittanbieter-Karten auf Garmin-Smartwatches.", requirement: "Apple-Silicon-Mac erforderlich.", requirements: ["macOS 13 oder neuer", "Apple-Silicon-Mac", "Garmin-Smartwatch mit Kartenunterstützung"], status: "Dies ist eine Pre-Release-Beta. Die Kompatibilität wird für jedes Modell bestätigt.", included: ["Native macOS-App", "Sichere Karteninstallation, Aktualisierung und Entfernung", "Katalog für Drittanbieter-Karten", "Import unterstützter Drittanbieter-.img-Karten vom Mac", "Lokale Installationsdaten"] },
      fr: { title: "Télécharger Terento pour Mac — Cartes tierces pour Garmin", description: "Téléchargez la bêta Terento gratuite et notariée pour Mac Apple Silicon afin d’installer et de gérer des cartes tierces sur les montres Garmin compatibles.", intro: "Une bêta macOS native et notariée pour installer et gérer des cartes tierces sur les montres Garmin.", requirement: "Mac Apple Silicon requis.", requirements: ["macOS 13 ou version ultérieure", "Mac Apple Silicon", "Montre Garmin compatible avec les cartes"], status: "Il s’agit d’une bêta pré-release. La compatibilité est confirmée modèle par modèle.", included: ["Application macOS native", "Installation, mise à jour et suppression sûres des cartes", "Catalogue de fournisseurs de cartes tierces", "Import de cartes .img tierces prises en charge depuis le Mac", "Enregistrements locaux des installations"] },
      pl: { title: "Pobierz Terento na Maca — Mapy innych firm dla Garmina", description: "Pobierz bezpłatną, notaryzowaną betę Terento na Maci z Apple Silicon, aby instalować i zarządzać mapami innych firm na zgodnych zegarkach Garmin.", intro: "Notaryzowana natywna beta macOS do instalowania i zarządzania mapami innych firm na zegarkach Garmin.", requirement: "Wymaga Maca z Apple Silicon.", requirements: ["macOS 13 lub nowszy", "Mac z Apple Silicon", "Zegarek Garmin obsługujący mapy"], status: "To wersja beta przed wydaniem. Kompatybilność jest potwierdzana dla każdego modelu.", included: ["Natywna aplikacja macOS", "Bezpieczna instalacja, aktualizacje i usuwanie map", "Katalog dostawców map innych firm", "Import obsługiwanych map .img innych firm z Maca", "Lokalne dane instalacji"] },
      cs: { title: "Stáhnout Terento pro Mac — Mapy třetích stran pro Garmin", description: "Stáhněte si bezplatnou, notářsky ověřenou betu Terento pro Macy s Apple Silicon k instalaci a správě map třetích stran na kompatibilních hodinkách Garmin.", intro: "Notářsky ověřená nativní beta pro macOS k instalaci a správě map třetích stran na hodinkách Garmin.", requirement: "Vyžaduje Mac s Apple Silicon.", requirements: ["macOS 13 nebo novější", "Mac s Apple Silicon", "Hodinky Garmin s podporou map"], status: "Jde o předběžnou betu. Kompatibilita se potvrzuje pro každý model.", included: ["Nativní aplikace pro macOS", "Bezpečná instalace, aktualizace a odstraňování map", "Katalog poskytovatelů map třetích stran", "Import podporovaných map .img třetích stran z Macu", "Místní záznamy instalace"] },
      it: { title: "Scarica Terento per Mac — Mappe di terze parti per Garmin", description: "Scarica la beta gratuita e notarizzata di Terento per Mac Apple Silicon per installare e gestire mappe di terze parti sugli smartwatch Garmin compatibili.", intro: "Una beta nativa per macOS, notarizzata, per installare e gestire mappe di terze parti sugli smartwatch Garmin.", requirement: "È richiesto un Mac Apple Silicon.", requirements: ["macOS 13 o versioni successive", "Mac Apple Silicon", "Smartwatch Garmin con supporto mappe"], status: "Questa è una beta pre-release. La compatibilità viene confermata modello per modello.", included: ["App macOS nativa", "Installazione, aggiornamento e rimozione sicuri delle mappe", "Catalogo dei provider di mappe di terze parti", "Importazione dal Mac di mappe .img di terze parti supportate", "Registri locali delle installazioni"] },
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
    text("#manage-maps-title + p", copy.manage);
    text("#manage-maps-title", document.querySelector("#manage-maps-title")?.textContent || "");
    const manageEyebrow = document.querySelector("#manage-maps-title")?.previousElementSibling;
    if (manageEyebrow) manageEyebrow.textContent = copy.manageEyebrow;
    text(".scope-copy", copy.scope);
    const scopeItems = document.querySelectorAll(".scope-item");
    if (scopeItems[2]) {
      scopeItems[2].querySelector("strong")?.replaceChildren(copy.scopeProvider);
      scopeItems[2].querySelector("span")?.replaceChildren(copy.scopeProviderDescription);
    }
    const installImage = document.querySelector("#install-maps-title")?.closest("section")?.querySelector("img");
    if (installImage) installImage.alt = copy.installAlt;
    const manageImage = document.querySelector("#manage-maps-title")?.closest("section")?.querySelector("img");
    if (manageImage) manageImage.alt = copy.manageAlt;
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
    const sections = [...document.querySelectorAll(".download-item")];
    if (sections[0]) sections[0].querySelector("ul")?.replaceChildren(...copy.requirements.map((item) => { const li = document.createElement("li"); li.textContent = item; return li; }));
    if (sections[1]) textFrom(sections[1], copy.status);
    if (sections[2]) {
      const includedList = sections[2].querySelector("ul");
      if (includedList) {
        includedList.replaceChildren(...copy.included.map((item) => { const li = document.createElement("li"); li.textContent = item; return li; }));
      } else {
        sections[2].querySelector("p")?.replaceChildren(...copy.included.map((item, index) => { const span = document.createElement("span"); span.textContent = `${index ? " · " : ""}${item}`; return span; }));
      }
    }
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
