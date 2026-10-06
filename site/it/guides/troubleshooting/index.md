---
title: "Risoluzione dei problemi delle mappe Garmin su Mac — Terento"
canonical: https://terento.app/it/guides/troubleshooting/
---

Risoluzione dei problemi

# Risolvi i problemi comuni di Terento

Trova il problema mostrato da Terento e segui i brevi passaggi. Se niente funziona, invia un rapporto così possiamo dare un’occhiata.

Connessione

## Collegare l’orologio

### Terento è in attesa dell’orologio

Terento rileva l’orologio automaticamente dopo il collegamento. Possono servire fino a 2 minuti.

1. Collega l’orologio direttamente al Mac con un cavo USB che supporti il trasferimento dati. I cavi solo di ricarica e alcuni hub non funzionano.
2. Sblocca l’orologio.
3. Attendi fino a 2 minuti mentre Terento controlla la connessione.
4. Se l’orologio non appare ancora, scollegalo, attendi qualche secondo e ricollegalo.

### Un’altra app sta usando l’orologio

Solo un’app alla volta può usare la connessione con l’orologio.

1. Chiudi Garmin Express e le altre app che possono aprire l’orologio, ad esempio le app di trasferimento file.
2. Se l’orologio appare nel Finder, espellilo da lì.
3. Ricollega l’orologio, poi scegli “Refresh” in Terento.

### È collegato più di un dispositivo Garmin

Terento funziona con un solo dispositivo Garmin alla volta.

1. Scollega tutti i dispositivi Garmin tranne l’orologio che vuoi usare.
2. Lascia collegato quell’orologio e attendi che Terento lo trovi.

### L’orologio non è pronto per il trasferimento file

Alcuni orologi Garmin hanno un’impostazione Modalità USB che determina come si collegano a un computer.

1. Sull’orologio cerca Modalità USB, di solito in Impostazioni › Sistema. Non tutti i modelli la hanno.
2. Se l’impostazione è presente, scegli MTP.
3. Scollega l’orologio e ricollegalo.

### L’orologio è stato rilevato ma non è pronto

Terento ha rilevato l’orologio, ma la connessione non era pronta entro 2 minuti. I blocchi occasionali della connessione sono un limite noto della beta attuale.

1. Scollega l’orologio e ricollegalo.
2. Chiudi le altre app che potrebbero usare l’orologio.
3. Prova un’altra porta USB o un altro cavo.
4. Se continua a succedere, riavvia l’orologio e ricollegalo.

### L’orologio non risponde più

La connessione si è interrotta o l’orologio ha smesso di rispondere a Terento.

1. Scollega l’orologio, attendi qualche secondo e ricollegalo.
2. Se Terento stava installando, aggiornando o rimuovendo una mappa, dopo il ricollegamento apri “Manage maps” e controlla il risultato prima di riprovare.
3. Riavvia l’orologio se succede di nuovo.

Controlli

## Controlli di orologio e mappe

### Questo modello di orologio non è abilitato all’installazione di mappe

Terento installa mappe solo sugli smartwatch Garmin con supporto alle mappe abilitati in Terento. Puoi comunque collegare l’orologio e sfogliare le mappe.

1. Verifica che il tuo modello di orologio supporti le mappe.
2. Terento controlla il suo elenco aggiornato a ogni collegamento. Se il tuo modello viene abilitato in seguito, ricollega l’orologio.
3. Indicaci il modello esatto così possiamo valutarlo. Vedi [Invia un rapporto](https://terento.app/it/guides/troubleshooting/#send-report).

### Terento non è riuscito a controllare questo orologio

Terento ha bisogno di una connessione Internet per verificare se su questo orologio si possono installare mappe.

1. Verifica che il Mac sia connesso a Internet.
2. Ricollega l’orologio per ripetere il controllo.
3. Se non riesce ancora, attendi qualche minuto e riprova.

### Non è stato possibile verificare la disponibilità delle mappe

Terento non è riuscito a caricare l’elenco attuale delle mappe, oppure questa versione di Terento è troppo vecchia. Le mappe già presenti sull’orologio non sono interessate.

1. Controlla la connessione Internet e riprova tra qualche minuto.
2. Se Terento segnala una versione più recente, installa l’aggiornamento.
3. Finché Terento mostra un elenco salvato meno recente, l’installazione e l’aggiornamento delle mappe del catalogo restano non disponibili fino a quando non è possibile verificare l’elenco attuale.

Download e spazio

## Download e spazio libero

### Il download della mappa non è riuscito

Terento scarica ogni mappa direttamente dal suo provider. I provider a volte sono lenti o temporaneamente non disponibili.

1. Controlla la connessione Internet.
2. Leggi il motivo indicato accanto alla mappa. Se il provider non è raggiungibile o i download sono sospesi, riprova più tardi.
3. Avvia di nuovo l’installazione.

### Spazio libero insufficiente sul Mac

Terento ha bisogno di spazio temporaneo sul Mac per scaricare e preparare una mappa.

1. Libera spazio sul Mac, ad esempio eliminando file che non ti servono più.
2. Riprova. Le regioni grandi richiedono più spazio.

### Spazio libero insufficiente sull’orologio

Terento controlla lo spazio libero sull’orologio prima di installare e non inizia se le mappe non ci stanno.

1. Scegli una regione più piccola o meno mappe.
2. Rimuovi in “Manage maps” una mappa che non ti serve più.
3. Un aggiornamento richiede spazio extra mentre la nuova mappa viene verificata. Libera spazio se un aggiornamento non può iniziare.

Installazione e aggiornamenti

## Installazioni, aggiornamenti e rimozioni

### L’installazione non è riuscita dopo la scrittura della mappa

Se un’installazione si interrompe dopo l’inizio della copia, parte della mappa può restare sull’orologio. Terento non la rimuove automaticamente.

1. Ricollega l’orologio e attendi che Terento sia pronto.
2. Apri “Manage maps” e controlla l’elenco.
3. Se la mappa dell’installazione non riuscita è nell’elenco, rimuovila e poi installala di nuovo.
4. Se non riesce di nuovo, [invia un rapporto](https://terento.app/it/guides/troubleshooting/#send-report).

### Aggiornamenti o rimozioni richiedono molto tempo

Durante l’aggiornamento o la rimozione di una mappa l’avanzamento può restare per un po’ su una percentuale alta prima di terminare. Nella beta attuale è previsto.

1. Lascia l’orologio collegato e il Mac attivo finché Terento non segnala che ha finito.
2. Non scollegare l’orologio mentre Terento è al lavoro.
3. Se Terento segnala un errore, ricollega l’orologio e controlla “Manage maps” prima di riprovare.

Ancora problemi?

## Ottenere assistenza

### Invia un rapporto

Quando un’installazione, un aggiornamento o una rimozione non riesce, Terento salva sul Mac un rapporto che ci aiuta ad analizzare il problema.

1. Nella schermata di errore scegli “Report issue”. In seguito puoi usare “Report latest failure” in “Diagnostics”.
2. Terento apre GitHub con il rapporto già compilato. Se il modulo è vuoto, fai clic nel campo del rapporto, premi ⌘A e poi ⌘V.
3. Controlla il rapporto prima di pubblicarlo: le issue su GitHub sono pubbliche.
4. Non hai un account GitHub? Scrivi a [hello@terento.app](mailto:hello@terento.app?subject=Terento%20installation%20issue) indicando il modello dell’orologio, la regione della mappa e cosa è successo.

Nuovo su Terento?

## Inizia dalla guida all’installazione in tre passaggi.

[Leggi la guida all’installazione su Mac](https://terento.app/it/guides/install-garmin-maps-mac/)
