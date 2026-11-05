---
title: "Kostenlose Karten auf die Garmin-Uhr vom Mac — Terento"
canonical: https://terento.app/de/guides/install-garmin-maps-mac/
---

# Kostenlose Karten vom Mac auf deine Garmin-Uhr installieren

Terento installiert kostenlose OpenStreetMap-Karten oder deine eigene Kartendatei auf einer Garmin-Uhr mit Kartenunterstützung. Du kopierst selbst keine Dateien, und deine Garmin-Karten bleiben unverändert.

[Herunterladen](https://terento.app/de/download/)

Du nutzt Linux? [Installiere Karten aus dem Browser](https://terento.app/de/guides/install-garmin-maps-linux/).

## Das brauchst du

- Mac mit Apple Silicon und macOS 13 oder neuer
- Garmin-Smartwatch mit Kartenunterstützung
- USB-Kabel mit Datenübertragung

Nach dem Verbinden prüft Terento die Uhr und sagt dir, ob es Karten installieren kann. Unter [Kompatibilität](https://terento.app/de/compatibility/) stehen die Modelle mit erfolgreichen Installationen; fehlt ein Modell, heißt das nicht unbedingt, dass es nicht unterstützt wird.

## Eine Karte installieren

1. Terento laden und öffnen

[Lade Terento herunter](https://terento.app/de/download/), ziehe es aus dem Disk-Image in den Ordner „Programme“ und öffne es dort. Beim ersten Öffnen fragt macOS, ob du eine aus dem Internet geladene App öffnen möchtest: Wähle „Öffnen“.

2. Uhr verbinden

Beende Garmin Express, falls es geöffnet ist. Entsperre die Uhr und verbinde sie mit einem USB-Datenkabel mit deinem Mac, nicht mit einem reinen Ladekabel. Fragt macOS, ob das Zubehör verbunden werden darf, wähle „Erlauben“. Terento findet die Uhr innerhalb von 1–2 Minuten und prüft, ob es Karten installieren kann.

[Garmin-Uhr wird am Mac nicht erkannt](https://terento.app/de/guides/troubleshooting/#connect-watch)

Terento zeigt eine verbundene Garmin-Uhr und den Gerätestatus
Terento erkennt die verbundene Garmin-Uhr vor der Installation.

3. Karte wählen

Wähle eine Karte aus dem Katalog oder füge deine eigene kompatible .img-Datei hinzu. [Vergleiche die Kartenstile](https://terento.app/de/map-styles/), um zu sehen, wie jede Karte Straßen und Wege darstellt.

1. Aus dem Katalog wählen

Wähle einen Anbieter und eine Region aus dem Katalog.

2. Eigene Karte hinzufügen

Füge eine kompatible .img-Karte von deinem Mac hinzu.

Terento zeigt Drittanbieter-Kartenanbieter, Regionen und verfügbaren Garmin-Speicher
Wähle eine Karte aus dem Katalog oder füge deine eigene kompatible Datei hinzu.

4. Installieren

Starte die Installation und lass die Uhr verbunden, bis Terento meldet, dass die Karte bereit ist. Trenne die Uhr danach.

Terento zeigt eine abgeschlossene Karteninstallation auf einer Garmin-Uhr
Lass die Uhr verbunden, bis Übertragung und Prüfung abgeschlossen sind.

## Die Karte auf der Uhr anzeigen

Trenne die Uhr, öffne ihre Karteneinstellungen und schalte die neue Karte ein. Fehlt sie in der Liste, starte die Uhr neu. Decken mehrere Karten dasselbe Gebiet ab, schalte die aus, die du nicht sehen möchtest.

Immer noch nicht sichtbar? Schreib an [hello@terento.app](mailto:hello@terento.app?subject=Terento%20installation%20issue) mit deinem genauen Uhrenmodell, der Kartenregion und dem, was passiert ist.

## Wenn etwas nicht klappt

### Terento erkennt die Uhr nicht

Warte nach dem Verbinden bis zu 1–2 Minuten. Wenn die Uhr weiterhin nicht erscheint, verbinde sie erneut, prüfe das Datenkabel und schließe andere Programme, die sie verwenden könnten. Weitere Hilfe: [Garmin-Uhr wird am Mac nicht erkannt](https://terento.app/de/guides/troubleshooting/#connect-watch), [Garmin Express oder eine andere App blockiert die Uhr](https://terento.app/de/guides/troubleshooting/#garmin-busy), [Garmin-Uhr nicht erkannt: USB-Modus (MTP)](https://terento.app/de/guides/troubleshooting/#usb-mode).

### Installieren oder Aktualisieren ist nicht verfügbar

Vorübergehend nicht verfügbare Karten bleiben sichtbar. Lies den Hinweis neben der Karte. Wenn der Kartenanbieter nicht erreichbar ist oder Downloads pausiert sind, versuche es später erneut. Kann Terento die aktuelle Verfügbarkeit nicht prüfen, überprüfe deine Internetverbindung und versuche es erneut. Bereits installierte Karten bleiben verfügbar. Weitere Hilfe: [Garmin-Kartenliste lädt nicht oder Terento braucht ein Update](https://terento.app/de/guides/troubleshooting/#catalog-unavailable), [Garmin-Karte: Download fehlgeschlagen](https://terento.app/de/guides/troubleshooting/#download-failed).

### Installation fehlgeschlagen

Wähle nach einer fehlgeschlagenen Installation „Report issue“. Terento öffnet GitHub mit einem bereits ausgefüllten Bericht. Prüfe ihn vor dem Veröffentlichen: GitHub-Issues sind öffentlich. Für Hilfe per E-Mail nenne dein Uhrenmodell, die Kartenregion und den Fehler. Weitere Hilfe: [Karteninstallation fehlgeschlagen: Kartenrest auf der Uhr](https://terento.app/de/guides/troubleshooting/#leftover-map), [Problem mit Terento melden](https://terento.app/de/guides/troubleshooting/#send-report).

[Alle Lösungsschritte ansehen](https://terento.app/de/guides/troubleshooting/)

## Terento deinstallieren

Beende Terento und bewege es aus „Programme“ in den Papierkorb. Karten auf deiner Uhr bleiben dort. Terento speichert die Angaben zu den installierten Karten in ~/Library/Application Support/Terento: Behalte diesen Ordner, wenn du Terento wieder installieren möchtest, damit es diese Karten weiter aktualisieren und entfernen kann. Um alles zu entfernen, lösche auch diesen Ordner, ~/Library/Caches/Terento, ~/Library/Logs/Terento und ~/Library/Preferences/app.terento.mac.plist.
