---
title: "Il Mac non rileva l’orologio Garmin? Risoluzione problemi — Terento"
canonical: https://terento.app/it/guides/troubleshooting/
---

Risoluzione dei problemi

# Risolvi i problemi di orologio Garmin e mappe su Mac

Trova il tuo problema, da un orologio Garmin che il Mac non rileva a un download della mappa non riuscito, e segui i brevi passaggi. Se niente funziona, invia un rapporto così possiamo dare un’occhiata.

Connessione

## Problemi di connessione dell’orologio Garmin

### Orologio Garmin non rilevato dal Mac

Collega l’orologio direttamente al Mac con un cavo USB che trasferisca i dati, sbloccalo e attendi fino a 2 minuti: Terento lo rileva automaticamente.

1. Usa un cavo dati. I cavi solo di ricarica e alcuni hub USB non funzionano.
2. Attendi fino a 2 minuti mentre Terento controlla la connessione.
3. Se l’orologio non appare ancora, scollegalo, attendi qualche secondo e ricollegalo.
4. Se è aperta un’altra app, vedi [Garmin Express o un’altra app sta usando l’orologio](https://terento.app/it/guides/troubleshooting/#garmin-busy).

### Garmin Express o un’altra app sta usando l’orologio

Chiudi Garmin Express e le app di trasferimento file come Android File Transfer, OpenMTP o MacDroid: solo un’app alla volta può usare la connessione con l’orologio.

1. Chiudi Garmin Express, Android File Transfer, OpenMTP, MacDroid e le altre app MTP. Se Terento indica un’app, chiudi prima quella.
2. Chiudi anche Acquisizione Immagine, Foto e Anteprima se sono aperte.
3. Se l’orologio appare nel Finder, espellilo da lì.
4. Scollega l’orologio, ricollegalo e poi scegli “Refresh” in Terento.

### Più dispositivi Garmin collegati

Scollega tutti i dispositivi Garmin tranne l’orologio che vuoi usare: Terento funziona con un solo Garmin alla volta.

1. Scollega gli altri orologi, ciclocomputer e dispositivi portatili Garmin.
2. Lascia collegato l’orologio scelto e attendi che Terento lo trovi.

### Orologio Garmin non riconosciuto: modalità USB (MTP)

Se Terento indica che l’orologio non è pronto per il trasferimento file, imposta la Modalità USB dell’orologio su MTP, se il tuo modello ha questa impostazione.

1. Sull’orologio apri Modalità USB, di solito in Impostazioni › Sistema. Non tutti i modelli la hanno.
2. Scegli MTP.
3. Scollega l’orologio e ricollegalo.

### Orologio Garmin rilevato ma non pronto

Se Terento trova l’orologio ma la connessione non è pronta entro 2 minuti, scollega l’orologio e ricollegalo. I blocchi occasionali della connessione sono un limite noto della versione attuale.

1. Chiudi le altre app che potrebbero usare l’orologio. Vedi [Garmin Express o un’altra app sta usando l’orologio](https://terento.app/it/guides/troubleshooting/#garmin-busy).
2. Prova un’altra porta USB o un altro cavo.
3. Se continua a succedere, riavvia l’orologio e ricollegalo.

### L’orologio Garmin non risponde più

Scollega l’orologio, attendi qualche secondo e ricollegalo: la connessione si è interrotta o l’orologio ha smesso di rispondere a Terento.

1. Se Terento stava installando, aggiornando o rimuovendo una mappa, dopo il ricollegamento apri “Manage maps” e controlla il risultato prima di riprovare.
2. Riavvia l’orologio se succede di nuovo.

Controlli

## Controlli di orologio e mappe

### Installazione mappe non disponibile per questo modello Garmin

Terento installa mappe solo sugli smartwatch Garmin con supporto alle mappe abilitati in Terento. Puoi comunque collegare l’orologio e sfogliare le mappe.

1. Verifica che il tuo modello di orologio supporti le mappe.
2. Terento controlla il suo elenco aggiornato a ogni collegamento. Se il tuo modello viene abilitato in seguito, ricollega l’orologio.
3. Indicaci il modello esatto così possiamo valutarlo. Vedi [Come segnalare un problema con Terento](https://terento.app/it/guides/troubleshooting/#send-report).

### Terento non è riuscito a controllare l’orologio Garmin

Verifica che il Mac sia connesso a Internet e ricollega l’orologio: Terento ha bisogno di Internet per verificare se su questo orologio si possono installare mappe.

1. Apri un sito web per verificare che il Mac sia online.
2. Scollega l’orologio e ricollegalo per ripetere il controllo.
3. Se non riesce ancora, attendi qualche minuto e riprova.

### L’elenco delle mappe Garmin non si carica o Terento va aggiornato

Se Terento non riesce a caricare l’elenco attuale delle mappe, controlla la connessione Internet e riprova tra qualche minuto. Le mappe già presenti sull’orologio non sono interessate.

1. Se questa versione di Terento è troppo vecchia per l’elenco attuale e Terento segnala una versione più recente, installa l’aggiornamento.
2. Finché Terento mostra un elenco salvato meno recente, l’installazione e l’aggiornamento delle mappe del catalogo restano non disponibili fino a quando non è possibile verificare l’elenco attuale.

Download e spazio

## Download delle mappe e spazio libero

### Download della mappa Garmin non riuscito

Controlla la connessione Internet e riprova più tardi: Terento scarica ogni mappa direttamente dal suo provider, e i provider a volte sono lenti o temporaneamente non disponibili.

1. Leggi il motivo indicato accanto alla mappa. Se il provider non è raggiungibile o i download sono sospesi, riprova più tardi.
2. Avvia di nuovo l’installazione.

### Spazio insufficiente sul Mac per scaricare la mappa

Libera spazio sul Mac e riprova: Terento ha bisogno di spazio temporaneo per scaricare e preparare una mappa.

1. Elimina i file che non ti servono più e svuota il Cestino.
2. Riprova. Le regioni grandi richiedono più spazio.

### Spazio insufficiente per le mappe Garmin sull’orologio

Scegli una regione più piccola o rimuovi una mappa che non ti serve più: Terento controlla lo spazio libero sull’orologio prima di installare e non inizia se le mappe non ci stanno.

1. Scegli una regione più piccola o meno mappe.
2. Apri “Manage maps” e rimuovi una mappa che non ti serve più.
3. Un aggiornamento richiede spazio extra mentre la nuova mappa viene verificata. Libera spazio se un aggiornamento non può iniziare.

Installazione e aggiornamenti

## Installare, aggiornare e rimuovere mappe

### Installazione della mappa non riuscita: mappa rimasta sull’orologio

Rimuovi la mappa rimasta in “Manage maps” e poi installala di nuovo. Se un’installazione si interrompe dopo l’inizio della copia, parte della mappa può restare sull’orologio e Terento non la rimuove automaticamente.

1. Ricollega l’orologio e attendi che Terento sia pronto.
2. Apri “Manage maps” e controlla l’elenco.
3. Se la mappa dell’installazione non riuscita è nell’elenco, rimuovila e poi installala di nuovo.
4. Se non riesce di nuovo, [invia un rapporto](https://terento.app/it/guides/troubleshooting/#send-report).

### Aggiornamento o rimozione della mappa molto lenti

Nella versione attuale è previsto: durante l’aggiornamento o la rimozione di una mappa l’avanzamento può restare per un po’ su una percentuale alta prima di terminare. Lascia l’orologio collegato e il Mac attivo.

1. Non scollegare l’orologio mentre Terento è al lavoro.
2. Attendi che Terento segnali che ha finito.
3. Se Terento segnala un errore, ricollega l’orologio e controlla “Manage maps” prima di riprovare.

Ancora problemi?

## Ottenere assistenza

### Come segnalare un problema con Terento

Nella schermata di errore scegli “Report issue”: Terento apre GitHub con il rapporto salvato sul Mac già compilato.

1. In seguito puoi usare “Report latest failure” in “Diagnostics”.
2. Se il modulo GitHub è vuoto, fai clic nel campo del rapporto, premi ⌘A e poi ⌘V.
3. Controlla il rapporto prima di pubblicarlo: le issue su GitHub sono pubbliche.
4. Non hai un account GitHub? Scrivi a [hello@terento.app](mailto:hello@terento.app?subject=Terento%20installation%20issue) indicando il modello dell’orologio, la regione della mappa e cosa è successo.

Nuovo su Terento?

## Inizia dalla guida all’installazione in tre passaggi.

[Leggi la guida all’installazione su Mac](https://terento.app/it/guides/install-garmin-maps-mac/)
