---
title: "Kostenlose Karten auf den Garmin Edge vom Mac — Terento"
canonical: https://terento.app/de/guides/install-garmin-maps-edge-mac/
---

# Kostenlose Karten vom Mac auf deinen Garmin Edge installieren

Neuere Garmin-Edge-Radcomputer erscheinen am Mac nicht als Laufwerk, deshalb kannst du nicht einfach eine Kartendatei darauf kopieren. Terento installiert kostenlose OpenStreetMap-Karten oder deine eigene kompatible Kartendatei auf Garmin-Edge-Radcomputern mit Kartenunterstützung, etwa Edge 540, 840 und 1050.

[Herunterladen](https://terento.app/de/download/)

## Das brauchst du

- Mac mit Apple Silicon und macOS 13 oder neuer
- Neuerer Garmin Edge mit Kartenunterstützung
- USB-Kabel mit Datenübertragung

Nach dem Verbinden prüft Terento den Edge und sagt dir, ob es Karten installieren kann. Unter [Kompatibilität](https://terento.app/de/compatibility/) stehen die Modelle mit erfolgreichen Installationen; fehlt ein Modell, heißt das nicht unbedingt, dass es nicht unterstützt wird.

## Eine Karte auf deinem Edge installieren

1. Terento laden und öffnen

[Lade Terento herunter](https://terento.app/de/download/), ziehe es aus dem Disk-Image in den Ordner „Programme“ und öffne es dort. Beim ersten Öffnen fragt macOS, ob du eine aus dem Internet geladene App öffnen möchtest: Wähle „Öffnen“.

2. Edge verbinden

Beende Garmin Express, falls es geöffnet ist. Verbinde den Edge über ein USB-Datenkabel direkt mit deinem Mac, nicht über einen Hub. Fragt macOS, ob das Zubehör verbunden werden darf, wähle „Erlauben“. Terento findet den Edge innerhalb von 2 Minuten und prüft, ob es Karten installieren kann.

3. Karte wählen

Wähle einen Anbieter und eine Region aus dem Katalog oder füge eine eigene kompatible .img-Kartendatei von deinem Mac hinzu. [Vergleiche die Kartenstile](https://terento.app/de/map-styles/), um zu sehen, wie jede Karte Straßen und Wege darstellt.

Terento zeigt Drittanbieter-Kartenanbieter, Regionen und verfügbaren Garmin-Speicher
Wähle eine Karte aus dem Katalog oder füge deine eigene kompatible Datei hinzu.

4. Installieren

Starte die Installation und lass den Edge verbunden, bis Terento meldet, dass die Installation abgeschlossen ist. Trenne den Edge danach.

Terento zeigt eine abgeschlossene Karteninstallation
Lass den Edge verbunden, bis Terento meldet, dass die Karte bereit ist.

## Die Karte auf dem Edge anzeigen

Trenne den Edge, öffne seine Karteneinstellungen und prüfe, ob die neue Karte aktiviert ist. Fehlt sie in der Liste, starte den Edge neu. Decken mehrere Karten dasselbe Gebiet ab, schalte die aus, die du nicht sehen möchtest.

## Wenn etwas nicht klappt

### Garmin Edge erscheint nicht in Terento

Nutze ein USB-Datenkabel, verbinde den Edge direkt statt über einen Hub, beende Garmin Express und Dateiübertragungs-Apps und warte bis zu 2 Minuten. Weitere Hilfe: [Garmin-Uhr wird am Mac nicht erkannt](https://terento.app/de/guides/troubleshooting/#connect-watch), [Garmin Express oder eine andere App blockiert die Uhr](https://terento.app/de/guides/troubleshooting/#garmin-busy).

### Installieren oder Aktualisieren ist nicht verfügbar

Vorübergehend nicht verfügbare Karten bleiben sichtbar. Lies den Hinweis neben der Karte. Wenn der Kartenanbieter nicht erreichbar ist oder Downloads pausiert sind, versuche es später erneut. Kann Terento die aktuelle Verfügbarkeit nicht prüfen, überprüfe deine Internetverbindung und versuche es erneut. Bereits installierte Karten bleiben verfügbar. Weitere Hilfe: [Garmin-Kartenliste lädt nicht oder Terento braucht ein Update](https://terento.app/de/guides/troubleshooting/#catalog-unavailable), [Garmin-Karte: Download fehlgeschlagen](https://terento.app/de/guides/troubleshooting/#download-failed).

### Installation fehlgeschlagen

Wähle nach einer fehlgeschlagenen Installation „Report issue“. Terento öffnet GitHub mit einem bereits ausgefüllten Bericht. Prüfe ihn vor dem Veröffentlichen: GitHub-Issues sind öffentlich. Für Hilfe per E-Mail nenne dein Edge-Modell, die Kartenregion und den Fehler. Weitere Hilfe: [Karteninstallation fehlgeschlagen: Kartenrest auf der Uhr](https://terento.app/de/guides/troubleshooting/#leftover-map), [Problem mit Terento melden](https://terento.app/de/guides/troubleshooting/#send-report).

[Alle Lösungsschritte ansehen](https://terento.app/de/guides/troubleshooting/)

## Warum dein Garmin Edge am Mac nicht erscheint

Neuere Edge-Modelle wie Edge 540, 840 und 1050 übertragen Dateien per USB wie Android-Smartphones. macOS unterstützt das nicht von Haus aus. Deshalb erscheint der Edge nicht als Laufwerk im Finder, und Anleitungen, nach denen du eine Kartendatei in den Garmin-Ordner kopierst, funktionieren bei diesen Modellen nicht. Terento spricht direkt mit dem Edge, du brauchst also weder Android File Transfer noch OpenMTP.

## Ältere Edge-Modelle

Ältere Modelle wie der Edge 1030 Plus und frühere erscheinen am Mac meist als USB-Laufwerk. Dort kannst du eine kompatible .img-Kartendatei selbst in den Garmin-Ordner auf dem Laufwerk kopieren, ohne Terento. Terento ist nicht für diese Modelle gedacht.
