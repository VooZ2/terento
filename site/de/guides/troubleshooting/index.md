---
title: "Garmin-Uhr wird am Mac nicht erkannt? Fehlerbehebung — Terento"
canonical: https://terento.app/de/guides/troubleshooting/
---

Fehlerbehebung

# Probleme mit Garmin-Uhr und Karten am Mac lösen

Finde dein Problem – von einer Garmin-Uhr, die der Mac nicht erkennt, bis zu einem fehlgeschlagenen Karten-Download – und folge den kurzen Schritten. Wenn nichts hilft, sende einen Bericht, damit wir es uns ansehen können.

Verbindung

## Verbindungsprobleme mit der Garmin-Uhr

### Garmin-Uhr wird am Mac nicht erkannt

Verbinde die Uhr direkt mit deinem Mac über ein USB-Kabel mit Datenübertragung, entsperre sie und warte bis zu 2 Minuten: Terento findet sie automatisch.

1. Verwende ein Datenkabel. Reine Ladekabel und manche USB-Hubs funktionieren nicht.
2. Warte bis zu 2 Minuten, während Terento die Verbindung prüft.
3. Erscheint die Uhr weiterhin nicht, trenne sie, warte ein paar Sekunden und verbinde sie erneut.
4. Ist ein anderes Programm geöffnet, siehe [Garmin Express oder eine andere App blockiert die Uhr](https://terento.app/de/guides/troubleshooting/#garmin-busy).

### Garmin Express oder eine andere App blockiert die Uhr

Beende Garmin Express und Dateiübertragungs-Apps wie Android File Transfer, OpenMTP oder MacDroid: Die Verbindung zur Uhr kann immer nur ein Programm nutzen.

1. Beende Garmin Express, Android File Transfer, OpenMTP, MacDroid und andere MTP-Apps. Nennt Terento ein Programm, beende zuerst dieses.
2. Schließe auch Digitale Bilder, Fotos und Vorschau, falls sie geöffnet sind.
3. Wenn die Uhr im Finder erscheint, wirf sie dort aus.
4. Trenne die Uhr, verbinde sie erneut und wähle dann in Terento „Refresh“.

### Mehrere Garmin-Geräte verbunden

Trenne alle Garmin-Geräte außer der Uhr, die du verwenden möchtest: Terento arbeitet immer nur mit einem Garmin.

1. Trenne andere Garmin-Uhren, Fahrradcomputer und Handgeräte.
2. Lass die gewünschte Uhr verbunden und warte, bis Terento sie findet.

### Garmin-Uhr nicht erkannt: USB-Modus (MTP)

Meldet Terento, dass die Uhr nicht für die Dateiübertragung bereit ist, stelle den USB-Modus der Uhr auf MTP, sofern dein Modell diese Einstellung hat.

1. Öffne auf der Uhr den USB-Modus, meist unter Einstellungen › System. Nicht jedes Modell hat diese Einstellung.
2. Wähle MTP.
3. Trenne die Uhr und verbinde sie erneut.

### Garmin-Uhr erkannt, aber nicht bereit

Findet Terento die Uhr, wird die Verbindung aber nicht innerhalb von 2 Minuten bereit, trenne die Uhr und verbinde sie erneut. Gelegentlich hängende Verbindungen sind eine bekannte Einschränkung der aktuellen Beta.

1. Beende andere Programme, die die Uhr verwenden könnten. Siehe [Garmin Express oder eine andere App blockiert die Uhr](https://terento.app/de/guides/troubleshooting/#garmin-busy).
2. Versuche einen anderen USB-Anschluss oder ein anderes Kabel.
3. Wenn es weiter passiert, starte die Uhr neu und verbinde sie erneut.

### Garmin-Uhr reagiert nicht mehr

Trenne die Uhr, warte ein paar Sekunden und verbinde sie erneut: Die Verbindung wurde unterbrochen oder die Uhr antwortet Terento nicht mehr.

1. Wenn Terento gerade eine Karte installiert, aktualisiert oder entfernt hat, öffne nach dem Verbinden „Manage maps“ und prüfe das Ergebnis, bevor du es erneut versuchst.
2. Starte die Uhr neu, wenn es wiederholt passiert.

Prüfungen

## Uhren- und Kartenprüfungen

### Karteninstallation für dieses Garmin-Modell nicht verfügbar

Terento installiert Karten nur auf Garmin-Uhren mit Kartenunterstützung, die in Terento freigegeben sind. Du kannst die Uhr trotzdem verbinden und die Karten durchsuchen.

1. Prüfe, ob dein Uhrenmodell Karten unterstützt.
2. Terento prüft bei jedem Verbinden seine aktuelle Liste. Wird dein Modell später freigegeben, verbinde die Uhr erneut.
3. Nenne uns dein genaues Modell, damit wir es prüfen können. Siehe [Problem mit Terento melden](https://terento.app/de/guides/troubleshooting/#send-report).

### Terento konnte deine Garmin-Uhr nicht prüfen

Prüfe, ob dein Mac online ist, und verbinde die Uhr erneut: Terento braucht eine Internetverbindung, um zu prüfen, ob auf dieser Uhr Karten installiert werden können.

1. Öffne eine Website, um zu prüfen, ob dein Mac online ist.
2. Trenne die Uhr und verbinde sie erneut, um die Prüfung zu wiederholen.
3. Wenn es weiterhin fehlschlägt, warte ein paar Minuten und versuche es erneut.

### Garmin-Kartenliste lädt nicht oder Terento braucht ein Update

Kann Terento die aktuelle Kartenliste nicht laden, prüfe deine Internetverbindung und versuche es in ein paar Minuten erneut. Karten, die bereits auf deiner Uhr sind, sind nicht betroffen.

1. Ist diese Terento-Version für die aktuelle Kartenliste zu alt und meldet Terento eine neuere Version, installiere das Update.
2. Solange Terento eine ältere gespeicherte Kartenliste zeigt, bleiben Installation und Aktualisierung von Katalogkarten nicht verfügbar, bis die aktuelle Liste geprüft werden kann.

Downloads und Speicher

## Karten-Downloads und freier Speicher

### Garmin-Karte: Download fehlgeschlagen

Prüfe deine Internetverbindung und versuche es später erneut: Terento lädt jede Karte direkt vom Kartenanbieter, und Anbieter sind manchmal langsam oder vorübergehend nicht erreichbar.

1. Lies den Hinweis neben der Karte. Wenn der Anbieter nicht erreichbar ist oder Downloads pausiert sind, versuche es später erneut.
2. Starte die Installation erneut.

### Nicht genug Speicher auf dem Mac für den Karten-Download

Schaffe Platz auf deinem Mac und versuche es erneut: Terento braucht vorübergehend Speicher, um eine Karte herunterzuladen und vorzubereiten.

1. Entferne nicht mehr benötigte Dateien und leere den Papierkorb.
2. Versuche es erneut. Große Regionen brauchen mehr Speicher.

### Nicht genug Speicher für Garmin-Karten auf der Uhr

Wähle eine kleinere Region oder entferne eine Karte, die du nicht mehr brauchst: Terento prüft vor der Installation den freien Speicher der Uhr und startet nicht, wenn die Karten nicht passen.

1. Wähle eine kleinere Region oder weniger Karten.
2. Öffne „Manage maps“ und entferne eine Karte, die du nicht mehr brauchst.
3. Ein Update braucht zusätzlichen Speicher, während die neue Karte geprüft wird. Schaffe Platz, wenn ein Update nicht starten kann.

Installieren und aktualisieren

## Karten installieren, aktualisieren und entfernen

### Karteninstallation fehlgeschlagen: Kartenrest auf der Uhr

Entferne den Kartenrest in „Manage maps“ und installiere die Karte dann erneut. Bricht eine Installation nach Beginn des Kopierens ab, kann ein Teil der Karte auf der Uhr bleiben, und Terento entfernt ihn nicht automatisch.

1. Verbinde die Uhr erneut und warte, bis Terento bereit ist.
2. Öffne „Manage maps“ und prüfe die Liste.
3. Wenn die Karte aus der fehlgeschlagenen Installation aufgeführt ist, entferne sie und installiere sie dann erneut.
4. Wenn es wieder fehlschlägt, [sende einen Bericht](https://terento.app/de/guides/troubleshooting/#send-report).

### Karten-Update oder Entfernen dauert lange

Das ist in der aktuellen Beta zu erwarten: Beim Aktualisieren oder Entfernen einer Karte kann die Anzeige eine Weile bei einem hohen Prozentwert stehen bleiben, bevor der Vorgang endet. Lass die Uhr verbunden und deinen Mac wach.

1. Trenne die Uhr nicht, solange Terento arbeitet.
2. Warte, bis Terento den Abschluss meldet.
3. Wenn Terento einen Fehler meldet, verbinde die Uhr erneut und prüfe „Manage maps“, bevor du es erneut versuchst.

Weiterhin Probleme?

## Hilfe bekommen

### Problem mit Terento melden

Wähle im Fehlerbildschirm „Report issue“: Terento öffnet GitHub mit dem Bericht, den es auf deinem Mac gespeichert hat, bereits ausgefüllt.

1. Später kannst du „Report latest failure“ in „Diagnostics“ verwenden.
2. Wenn das GitHub-Formular leer ist, klicke in das Berichtsfeld, drücke ⌘A und dann ⌘V.
3. Prüfe den Bericht vor dem Veröffentlichen: GitHub-Issues sind öffentlich.
4. Kein GitHub-Konto? Schreibe an [hello@terento.app](mailto:hello@terento.app?subject=Terento%20installation%20issue) und nenne dein Uhrenmodell, die Kartenregion und was passiert ist.

Neu bei Terento?

## Starte mit der Anleitung in drei Schritten.

[Mac-Installationsanleitung lesen](https://terento.app/de/guides/install-garmin-maps-mac/)
