---
title: "Mappe gratuite sull’orologio Garmin da Mac — Terento"
canonical: https://terento.app/it/guides/install-garmin-maps-mac/
---

# Installa mappe gratuite sul tuo orologio Garmin da Mac

Terento installa mappe OpenStreetMap gratuite, o un tuo file di mappa, su un orologio Garmin con supporto alle mappe. Non copi nessun file a mano e le tue mappe Garmin restano come sono.

[Scarica](https://terento.app/it/download/)

Usi Linux? [Installa le mappe dal browser](https://terento.app/it/guides/install-garmin-maps-linux/).

## Cosa ti serve

- Mac Apple Silicon con macOS 13 o versioni successive
- Smartwatch Garmin con supporto alle mappe
- Cavo USB per il trasferimento dati

Dopo il collegamento, Terento controlla l’orologio e ti dice se può installare le mappe. La pagina [Compatibilità](https://terento.app/it/compatibility/) elenca i modelli con installazioni riuscite; un modello assente non è per forza non supportato.

## Installa una mappa

1. Scarica e apri Terento

[Scarica Terento](https://terento.app/it/download/), trascinalo dall’immagine disco in Applicazioni e aprilo da lì. Alla prima apertura macOS chiede se aprire un’app scaricata da Internet: scegli Apri.

2. Collega l’orologio

Chiudi Garmin Express, se è aperto. Sblocca l’orologio e collegalo al Mac con un cavo USB dati, non con un cavo di sola ricarica. Se macOS chiede se consentire il collegamento dell’accessorio, scegli Consenti. Terento trova l’orologio entro 1–2 minuti e controlla se può installare le mappe.

[Orologio Garmin non rilevato dal Mac](https://terento.app/it/guides/troubleshooting/#connect-watch)

Terento mostra uno smartwatch Garmin collegato e lo stato del rilevamento
Terento riconosce lo smartwatch Garmin collegato prima dell’installazione.

3. Scegli una mappa

Scegli una mappa dal catalogo oppure aggiungi il tuo file .img compatibile. [Confronta gli stili di mappa](https://terento.app/it/map-styles/) per vedere come ogni mappa mostra strade e sentieri.

1. Scegli dal catalogo

Scegli un provider e una regione dal catalogo.

2. Aggiungi la tua mappa

Aggiungi una mappa .img compatibile dal Mac.

Terento mostra i provider, le regioni delle mappe di terze parti e lo spazio disponibile sul Garmin
Scegli una mappa dal catalogo oppure aggiungi il tuo file compatibile.

4. Installa

Avvia l’installazione e lascia l’orologio collegato finché Terento non indica che la mappa è pronta. Poi scollega l’orologio.

Terento mostra un’installazione della mappa completata su uno smartwatch Garmin
Lascia l’orologio collegato fino al completamento del trasferimento e della verifica.

## Mostra la mappa sull’orologio

Scollega l’orologio, apri le impostazioni delle mappe e attiva la nuova mappa. Se non è nell’elenco, riavvia l’orologio. Se più mappe coprono la stessa zona, disattiva quelle che non vuoi vedere.

Ancora non la vedi? Scrivi a [hello@terento.app](mailto:hello@terento.app?subject=Terento%20installation%20issue) indicando il modello esatto dell’orologio, la regione della mappa e cosa è successo.

## Se qualcosa non funziona

### Terento non rileva l’orologio

Attendi 1–2 minuti dopo il collegamento. Se lo smartwatch non appare, ricollegalo, controlla il cavo dati e chiudi le altre app che potrebbero usarlo. Altro aiuto: [Orologio Garmin non rilevato dal Mac](https://terento.app/it/guides/troubleshooting/#connect-watch), [Garmin Express o un’altra app sta usando l’orologio](https://terento.app/it/guides/troubleshooting/#garmin-busy), [Orologio Garmin non riconosciuto: modalità USB (MTP)](https://terento.app/it/guides/troubleshooting/#usb-mode).

### L’installazione o l’aggiornamento non è disponibile

Le mappe temporaneamente non disponibili restano visibili. Leggi il motivo indicato accanto alla mappa. Se il provider non è raggiungibile o i download sono sospesi, riprova più tardi. Se Terento non riesce a verificare la disponibilità attuale, controlla la connessione Internet e riprova. Le mappe già installate restano disponibili. Altro aiuto: [L’elenco delle mappe Garmin non si carica o Terento va aggiornato](https://terento.app/it/guides/troubleshooting/#catalog-unavailable), [Download della mappa Garmin non riuscito](https://terento.app/it/guides/troubleshooting/#download-failed).

### Installazione non riuscita

Nella schermata di installazione non riuscita, scegli “Report issue”. Terento apre GitHub con il rapporto già compilato. Controllalo prima di pubblicarlo: le issue su GitHub sono pubbliche. Per assistenza via e-mail, indica il modello dell’orologio, la regione della mappa e cosa è successo. Altro aiuto: [Installazione della mappa non riuscita: mappa rimasta sull’orologio](https://terento.app/it/guides/troubleshooting/#leftover-map), [Come segnalare un problema con Terento](https://terento.app/it/guides/troubleshooting/#send-report).

[Vedi tutte le soluzioni](https://terento.app/it/guides/troubleshooting/)

## Disinstallare Terento

Chiudi Terento e spostalo da Applicazioni nel Cestino. Le mappe già sull’orologio restano lì. Terento conserva le informazioni sulle mappe installate in ~/Library/Application Support/Terento: tieni questa cartella se potresti reinstallare Terento, così potrà ancora aggiornare e rimuovere quelle mappe. Per rimuovere tutto, elimina anche questa cartella, ~/Library/Caches/Terento, ~/Library/Logs/Terento e ~/Library/Preferences/app.terento.mac.plist.
