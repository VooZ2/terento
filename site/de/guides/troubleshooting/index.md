---
title: "Fehlerbehebung für Garmin-Karten auf dem Mac — Terento"
canonical: https://terento.app/de/guides/troubleshooting/
---

Fehlerbehebung

# Häufige Terento-Probleme lösen

Suche das Problem, das Terento anzeigt, und folge den kurzen Schritten. Wenn nichts hilft, sende einen Bericht, damit wir es uns ansehen können.

Verbindung

## Uhr verbinden

### Terento wartet auf deine Uhr

Terento findet die Uhr nach dem Verbinden automatisch. Das kann bis zu 2 Minuten dauern.

1. Verbinde die Uhr direkt mit deinem Mac über ein USB-Kabel mit Datenübertragung. Reine Ladekabel und manche Hubs funktionieren nicht.
2. Entsperre die Uhr.
3. Warte bis zu 2 Minuten, während Terento die Verbindung prüft.
4. Erscheint die Uhr weiterhin nicht, trenne sie, warte ein paar Sekunden und verbinde sie erneut.

### Ein anderes Programm verwendet die Uhr

Die Verbindung zur Uhr kann immer nur ein Programm nutzen.

1. Beende Garmin Express und andere Programme, die die Uhr öffnen können, zum Beispiel Dateiübertragungs-Apps.
2. Wenn die Uhr im Finder erscheint, wirf sie dort aus.
3. Verbinde die Uhr erneut und wähle dann in Terento „Refresh“.

### Mehr als ein Garmin ist verbunden

Terento arbeitet immer nur mit einem Garmin-Gerät.

1. Trenne alle Garmin-Geräte außer der Uhr, die du verwenden möchtest.
2. Lass diese Uhr verbunden und warte, bis Terento sie findet.

### Die Uhr ist nicht für die Dateiübertragung bereit

Manche Garmin-Uhren haben eine Einstellung für den USB-Modus, die festlegt, wie sie sich mit einem Computer verbinden.

1. Suche auf der Uhr nach dem USB-Modus, meist unter Einstellungen › System. Nicht jedes Modell hat diese Einstellung.
2. Wenn es die Einstellung gibt, wähle MTP.
3. Trenne die Uhr und verbinde sie erneut.

### Die Uhr wurde erkannt, ist aber nicht bereit

Terento hat die Uhr erkannt, aber die Verbindung war nicht innerhalb von 2 Minuten bereit. Gelegentlich hängende Verbindungen sind eine bekannte Einschränkung der aktuellen Beta.

1. Trenne die Uhr und verbinde sie erneut.
2. Schließe andere Programme, die die Uhr verwenden könnten.
3. Versuche einen anderen USB-Anschluss oder ein anderes Kabel.
4. Wenn es weiter passiert, starte die Uhr neu und verbinde sie erneut.

### Die Uhr reagiert nicht mehr

Die Verbindung wurde unterbrochen oder die Uhr antwortet Terento nicht mehr.

1. Trenne die Uhr, warte ein paar Sekunden und verbinde sie erneut.
2. Wenn Terento gerade eine Karte installiert, aktualisiert oder entfernt hat, öffne nach dem Verbinden „Manage maps“ und prüfe das Ergebnis, bevor du es erneut versuchst.
3. Starte die Uhr neu, wenn es wiederholt passiert.

Prüfungen

## Uhren- und Kartenprüfungen

### Dieses Uhrenmodell ist nicht für die Karteninstallation freigegeben

Terento installiert Karten nur auf Garmin-Uhren mit Kartenunterstützung, die in Terento freigegeben sind. Du kannst die Uhr trotzdem verbinden und die Karten durchsuchen.

1. Prüfe, ob dein Uhrenmodell Karten unterstützt.
2. Terento prüft bei jedem Verbinden seine aktuelle Liste. Wird dein Modell später freigegeben, verbinde die Uhr erneut.
3. Nenne uns dein genaues Modell, damit wir es prüfen können. Siehe [Bericht senden](https://terento.app/de/guides/troubleshooting/#send-report).

### Terento konnte diese Uhr nicht prüfen

Terento braucht eine Internetverbindung, um zu prüfen, ob auf dieser Uhr Karten installiert werden können.

1. Prüfe, ob dein Mac mit dem Internet verbunden ist.
2. Verbinde die Uhr erneut, um die Prüfung zu wiederholen.
3. Wenn es weiterhin fehlschlägt, warte ein paar Minuten und versuche es erneut.

### Die Kartenverfügbarkeit konnte nicht geprüft werden

Terento konnte die aktuelle Kartenliste nicht laden, oder diese Terento-Version ist dafür zu alt. Karten, die bereits auf deiner Uhr sind, sind nicht betroffen.

1. Prüfe deine Internetverbindung und versuche es in ein paar Minuten erneut.
2. Wenn Terento eine neuere Version meldet, installiere das Update.
3. Solange Terento eine ältere gespeicherte Kartenliste zeigt, bleiben Installation und Aktualisierung von Katalogkarten nicht verfügbar, bis die aktuelle Liste geprüft werden kann.

Downloads und Speicher

## Downloads und freier Speicher

### Der Kartendownload ist fehlgeschlagen

Terento lädt jede Karte direkt vom Kartenanbieter. Anbieter sind manchmal langsam oder vorübergehend nicht erreichbar.

1. Prüfe deine Internetverbindung.
2. Lies den Hinweis neben der Karte. Wenn der Anbieter nicht erreichbar ist oder Downloads pausiert sind, versuche es später erneut.
3. Starte die Installation erneut.

### Nicht genügend freier Speicher auf dem Mac

Terento braucht vorübergehend Speicher auf deinem Mac, um eine Karte herunterzuladen und vorzubereiten.

1. Schaffe Platz auf deinem Mac, zum Beispiel indem du nicht mehr benötigte Dateien entfernst.
2. Versuche es erneut. Große Regionen brauchen mehr Speicher.

### Nicht genügend freier Speicher auf der Uhr

Terento prüft vor der Installation den freien Speicher der Uhr und startet nicht, wenn die Karten nicht passen.

1. Wähle eine kleinere Region oder weniger Karten.
2. Entferne in „Manage maps“ eine Karte, die du nicht mehr brauchst.
3. Ein Update braucht zusätzlichen Speicher, während die neue Karte geprüft wird. Schaffe Platz, wenn ein Update nicht starten kann.

Installieren und aktualisieren

## Installation, Updates und Entfernen

### Die Installation ist nach dem Schreiben fehlgeschlagen

Wenn eine Installation nach Beginn des Kopierens abbricht, kann ein Teil der Karte auf der Uhr bleiben. Terento entfernt ihn nicht automatisch.

1. Verbinde die Uhr erneut und warte, bis Terento bereit ist.
2. Öffne „Manage maps“ und prüfe die Liste.
3. Wenn die Karte aus der fehlgeschlagenen Installation aufgeführt ist, entferne sie und installiere sie dann erneut.
4. Wenn es wieder fehlschlägt, [sende einen Bericht](https://terento.app/de/guides/troubleshooting/#send-report).

### Updates oder Entfernen dauern lange

Beim Aktualisieren oder Entfernen einer Karte kann die Anzeige eine Weile bei einem hohen Prozentwert stehen bleiben, bevor der Vorgang endet. Das ist in der aktuellen Beta zu erwarten.

1. Lass die Uhr verbunden und deinen Mac wach, bis Terento den Abschluss meldet.
2. Trenne die Uhr nicht, solange Terento arbeitet.
3. Wenn Terento einen Fehler meldet, verbinde die Uhr erneut und prüfe „Manage maps“, bevor du es erneut versuchst.

Weiterhin Probleme?

## Hilfe bekommen

### Bericht senden

Wenn eine Installation, ein Update oder eine Entfernung fehlschlägt, speichert Terento einen Bericht auf deinem Mac, der uns bei der Untersuchung hilft.

1. Wähle im Fehlerbildschirm „Report issue“. Später kannst du „Report latest failure“ in „Diagnostics“ verwenden.
2. Terento öffnet GitHub mit dem ausgefüllten Bericht. Wenn das Formular leer ist, klicke in das Berichtsfeld, drücke ⌘A und dann ⌘V.
3. Prüfe den Bericht vor dem Veröffentlichen: GitHub-Issues sind öffentlich.
4. Kein GitHub-Konto? Schreibe an [hello@terento.app](mailto:hello@terento.app?subject=Terento%20installation%20issue) und nenne dein Uhrenmodell, die Kartenregion und was passiert ist.

Neu bei Terento?

## Starte mit der Anleitung in drei Schritten.

[Mac-Installationsanleitung lesen](https://terento.app/de/guides/install-garmin-maps-mac/)
