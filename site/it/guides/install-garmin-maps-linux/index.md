---
title: "Mappe per orologio Garmin su Linux da Chrome — Terento"
canonical: https://terento.app/it/guides/install-garmin-maps-linux/
---

# Installare mappe Garmin su Linux

Su Linux l’installer web di Terento mette mappe gratuite sugli orologi Garmin che supportano le mappe, direttamente dal browser. Prima Linux ha bisogno di una regola di autorizzazione, così il browser può usare l’orologio via USB.

[Apri l’installer web](https://terento.app/it/install/)

Hai un Mac? Leggi la guida per un [orologio Garmin](https://terento.app/it/guides/install-garmin-maps-mac/) o un [Garmin Edge](https://terento.app/it/guides/install-garmin-maps-edge-mac/).

## Cosa ti serve

- Chrome, Microsoft Edge, Opera o Brave su un computer Linux. Firefox non può collegarsi ai dispositivi USB.
- Un cavo USB per dati, non solo di ricarica.
- Un orologio Garmin che supporta le mappe, sbloccato.

## Installa una mappa dal browser

1. Dai al browser l’accesso USB

Apri il Terminale e incolla questo comando. Aggiunge una regola udev per i dispositivi Garmin e chiede una volta la password di amministratore. Poi scollega l’orologio e ricollegalo.

```
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="091e", MODE="0660", GROUP="plugdev", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/70-garmin.rules >/dev/null && sudo udevadm control --reload-rules && sudo udevadm trigger
```

2. Apri l’installer web e collega

[Apri l’installer web](https://terento.app/it/install/), scegli “Collega il tuo orologio” e poi la voce con “Garmin” nel nome. L’elenco può restare vuoto per un minuto o due mentre l’orologio si prepara.

3. Scegli le mappe e installa

Scegli un paese o una regione e poi “Installa mappe”. Lascia la scheda aperta e l’orologio collegato fino al completamento.

## Se non funziona

### Il browser non riesce ad aprire l’orologio

Il gestore file potrebbe usare l’orologio. Espellilo da lì senza scollegarlo, poi ricarica la pagina. Se hai aggiunto la regola con l’orologio collegato, scollegalo e ricollegalo.

### L’elenco del browser resta vuoto

Lascia l’elenco aperto fino a due minuti. Se non appare una voce con “Garmin” nel nome, prova un altro cavo USB per dati e controlla che l’orologio sia sbloccato.

### Il browser non ha accesso USB

Un browser installato come pacchetto Snap potrebbe non avere accesso USB. Usa il browser dal suo pacchetto ufficiale .deb o .rpm.
