---
title: "Garmin-Karten unter Linux aus Chrome installieren — Terento"
canonical: https://terento.app/de/guides/install-garmin-maps-linux/
---

Linux-Anleitung

# Garmin-Karten unter Linux installieren

Unter Linux installiert der Terento-Web-Installer kostenlose Karten auf Garmin-Uhren mit Kartenunterstützung, direkt aus dem Browser. Linux braucht zuerst eine Berechtigungsregel, damit der Browser die Uhr über USB nutzen kann.

## Das brauchst du

- Chrome, Edge, Opera oder Brave auf einem Linux-Computer. Firefox kann keine USB-Geräte verbinden.
- Ein USB-Datenkabel, kein reines Ladekabel.
- Eine entsperrte Garmin-Uhr mit Kartenunterstützung.

Drei Schritte

## Eine Karte aus dem Browser installieren

1. Dem Browser USB-Zugriff geben

Öffne das Terminal und füge diesen Befehl ein. Er legt eine udev-Regel für Garmin-Geräte an und fragt einmal nach deinem Administratorpasswort. Trenne die Uhr danach und schließe sie wieder an.

```
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="091e", MODE="0660", GROUP="plugdev", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/70-garmin.rules >/dev/null && sudo udevadm control --reload-rules && sudo udevadm trigger
```

2. Web-Installer öffnen und verbinden

Öffne den Web-Installer, wähle „Verbinde deine Uhr“ und dann den Eintrag mit „Garmin“ im Namen. Die Liste kann ein bis zwei Minuten leer bleiben, während sich die Uhr vorbereitet.

3. Karten wählen und installieren

Wähle ein Land oder eine Region und dann „Karten installieren“. Lass den Tab geöffnet und die Uhr verbunden, bis der Vorgang abgeschlossen ist.

Fehlerbehebung

## Wenn es nicht klappt

### Der Browser kann die Uhr nicht öffnen

Möglicherweise verwendet dein Dateimanager die Uhr. Wirf sie dort aus, ohne sie zu trennen, und lade die Seite neu. Wenn du die Regel bei verbundener Uhr angelegt hast, trenne die Uhr und schließe sie wieder an.

### Die Liste des Browsers bleibt leer

Lass die Liste bis zu zwei Minuten offen. Wenn kein Eintrag mit „Garmin“ im Namen erscheint, probiere ein anderes USB-Datenkabel und prüfe, ob die Uhr entsperrt ist.

### Der Browser hat keinen USB-Zugriff

Ein als Snap-Paket installierter Browser bekommt möglicherweise keinen USB-Zugriff. Verwende den Browser aus seinem offiziellen .deb- oder .rpm-Paket.

Bereit?

## Öffne den Web-Installer und verbinde deine Uhr.

[Web-Installer öffnen](https://terento.app/de/install/)
