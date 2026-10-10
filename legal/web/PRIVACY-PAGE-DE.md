# Datenschutz

Dieser Hinweis gilt für die Terento-Website, die macOS-App und den Web-Installer. Ein Konto ist nicht nötig. Karten und Gerätedaten bleiben auf deinem Mac oder in deinem Browser; die unten beschriebenen begrenzten Diagnosen und Statistiken werden getrennt übermittelt.

## Kontakt

Verantwortlicher: Privatperson. Lies [Über Terento](/de/about/) oder kontaktiere [privacy@terento.app](mailto:privacy@terento.app) bei Fragen zu deinen Daten.

## App-Diagnose

Zwei Diagnoseströme sind standardmäßig aktiviert, um Installation und Kompatibilität zu verbessern. Während der Installation gibt es keine Freigabeauswahl. Deaktiviere jeden Strom unter **Terento → Diagnostics**, ohne die App einzuschränken. Dies beendet künftige Übermittlungen und leert die jeweilige ungesendete Warteschlange. Hochgeladene Berichte können nicht in der App gelöscht werden; Datenschutzanfragen sind über den Kontakt oben möglich.

- **Kompatibilität:** Uhrenmodell und Firmware, App- und macOS-Version, gewählte Anbieter/Karten, Installationsergebnis und begrenzte technische Fehlerinformationen.
- **Kartennutzung:** Anbieter, Karte/Region, Download- oder Installationsergebnis, Zeit, App-Build und zufällige Vorgangs-/Ereignis-IDs. Eigene `.img`-Importe sind ausgeschlossen.

Berichte enthalten keine Garmin Unit IDs, Seriennummernwerte, Kontodaten, lokalen Pfade, Kartendateien oder Rohprotokolle. Einzelberichte sind privat; nur geprüfte zusammengefasste Kompatibilitätsergebnisse werden veröffentlicht. Grundlage sind berechtigte Interessen an Zuverlässigkeit und Geräteabdeckung nach Art. 6 Abs. 1 lit. f DSGVO.

## Web-Installer

Mit dem Web-Installer installierst du Karten aus Google Chrome auf deine Uhr, ohne die App. Chrome liest auf deinem Computer, was es von der Uhr braucht, etwa Modell, freien Speicher und Karten.

Wenn du eine Karte wählst, lädt der Terento-Server sie vom ursprünglichen Anbieter und gibt sie an deinen Browser weiter. Die Kopie entsteht nur für deine Anfrage, wird nicht geteilt und gelöscht, sobald dein Browser sie hat, oder nach zwei Stunden, wenn sie nicht abgeholt wird. Der Anbieter sieht den Terento-Server, nicht dich.

Die Seite sendet Terento kurze anonyme Meldungen zu jedem Schritt: ob dieser Browser nutzbar ist, ob die Uhr verbunden wurde und wie jede Installation, Aktualisierung oder Entfernung einer Karte ausging. Sie enthalten:

- Uhrenmodell und Softwareversion
- Betriebssystem und Browser mit ihrer Hauptversion
- Kartenanbieter, Karte, Größenbereich und ob es eine neue Installation oder ein Update war
- den fehlgeschlagenen Schritt, einen festen Grundcode und die Dauer von Schreiben und Prüfen
- einen zufälligen Code, der bei jedem Öffnen der Seite neu entsteht, damit die Schritte eines Besuchs zusammengehören

Sie enthalten nie die Seriennummer oder Unit ID deiner Uhr, deine IP-Adresse, Dateinamen, die Liste der Karten auf deiner Uhr oder Fehlertexte. Deine IP-Adresse wird nur kurz im Arbeitsspeicher gehalten, um zu begrenzen, wie viele Anfragen ein Computer stellen kann, und nicht gespeichert. Die Meldungen zeigen uns, welche Uhren, Systeme und Browser funktionieren, und helfen, Fehler zu beheben. Grundlage sind berechtigte Interessen nach Art. 6 Abs. 1 lit. f DSGVO. Auf der Seite gibt es keinen Schalter; für einen Widerspruch kontaktiere uns. Einzelne Meldungen sind privat und werden 24 Monate aufbewahrt.

Einige Daten bleiben in deinem Browser, nicht auf unserem Server: welche Karten der Web-Installer auf welcher Uhr installiert hat, damit er sie später sicher aktualisieren oder entfernen kann, eine vorübergehende Kopie einer Karte bis zur Installation und die gewählte Sprache. Um die Uhr wiederzuerkennen, speichert er einen Einwegcode aus Uhrendaten und einem Zufallswert, aus dem sich die Seriennummer nicht zurückgewinnen lässt. Wenn du in Chrome die Websitedaten des Web-Installers löschst, wird all das entfernt. Der Web-Installer lädt keine Website-Statistik.

## Verbindungen von Website und App

Bei Website-, Web-Installer-, API-, Katalog- und Update-Anfragen können Hosting- und Sicherheitsanbieter deine IP-Adresse und Anfrage-Metadaten erhalten. In der App werden Katalogkarten direkt von Freizeitkarte, OpenTopoMap, MapRando oder BBBike geladen; deren Datenschutzregeln gelten für diese Verbindungen. Die Update-Prüfung beim App-Start lädt Veröffentlichungsdaten, nicht die App selbst.

Diese Verbindungen liefern Inhalte, ermöglichen angeforderte Funktionen und schützen vor Missbrauch. Die Sicherheitsverarbeitung beruht auf berechtigten Interessen nach Art. 6 Abs. 1 lit. f DSGVO.

## Hilfe und öffentliche Meldungen

Wenn du uns schreibst, erhalten wir deine E-Mail-Adresse, Nachricht und Anhänge, um zu antworten und das Problem zu untersuchen. Sende keine Kartendateien, Zugangsdaten oder privaten Gerätekennungen. Die Bearbeitung beruht auf berechtigten Interessen an der Beantwortung von Anfragen und der Wartung der App.

Ein GitHub-Issue ist von automatischer Diagnose getrennt: Du prüfst und sendest es selbst; Inhalt und GitHub-Kontoname können öffentlich sein. Es gilt [GitHubs Datenschutzerklärung](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement). Freiwillige Spenden erfolgen über [Buy Me a Coffee](https://www.buymeacoffee.com/privacy-policy), das Zahlungsinformationen nach eigenen Bedingungen verarbeitet.

## Supportberichte

Wenn die App anbietet, einen Supportbericht an Terento zu senden, wird er nur gesendet, wenn du dich dafür entscheidest, nachdem du seinen Inhalt gesehen hast. Er enthält die bereinigten Fehlerangaben, die auch für GitHub-Berichte verwendet werden: App- und macOS-Version, Uhrenmodell und -variante, den fehlgeschlagenen Schritt, Fehlerkategorie und -meldung, Kartenanbieter und Region sowie Zeitangaben, dazu eine optionale Beschreibung. Seriennummern, Unit IDs, Kontodaten, lokale Pfade, Rohprotokolle und Kartendateien sind ausgeschlossen; ein GitHub-Konto ist nicht nötig. Gib in der Beschreibung keine personenbezogenen Daten an.

Supportberichte dienen nur der Diagnose des gemeldeten Problems, fließen nicht in Statistiken ein und werden 12 Monate aufbewahrt. Zugriff hat nur die Projektverwaltung; deine IP-Adresse wird nicht mit dem Bericht gespeichert. Grundlage sind berechtigte Interessen an der Beantwortung deiner Anfrage und der Wartung der App nach Art. 6 Abs. 1 lit. f DSGVO.

## Website-Statistik und Browserspeicher

Umami wird für alle Besucher geladen, um Seitenaufrufe, Linkklicks und Downloads zu messen. Es nutzt keine Tracking-Cookies. Verarbeitet werden können Seiten-/Referrer-URLs, Browser, Betriebssystem, Gerät und ungefähre Standortdaten. UTM-Werte in Links beschreiben Kampagnenquellen. Terento reicht sie über URLs weiter, ohne Kampagnen im Browser zu speichern. Die Statistik dient Website-Verbesserung und Kampagnenmessung auf Grundlage berechtigter Interessen nach Art. 6 Abs. 1 lit. f DSGVO. Es gibt weder ein Analyse-Einwilligungsbanner noch einen Analyseschalter auf der Website; für einen Widerspruch kontaktiere uns. Website-Statistik und App-Diagnoseeinstellungen sind getrennt.

Eine von dir gewählte Sprache wird als `terento-language` im lokalen Speicher gespeichert. Diese angeforderte Einstellung ist von der Analytik getrennt. Cloudflare kann je nach Schutzeinstellungen Sicherheits-Cookies einsetzen.

## Empfänger und Speicherung

Website, Web-Installer, API und Datenbank nutzen Hostinger; Cloudflare liefert und schützt Website-, Web-Installer- und API-Verkehr. Umami läuft unter `stats.enduristas.lt`. Informationen der Anbieter findest du bei [Cloudflare](https://www.cloudflare.com/privacypolicy/) und [Hostinger](https://www.hostinger.com/legal/privacy-policy). Je nach Konfiguration kann eine Verarbeitung außerhalb des EWR stattfinden; kontaktiere uns zu den geltenden Regelungen.

Die Aufbewahrungsrichtlinie für hochgeladene App-Diagnosen und Meldungen des Web-Installers beträgt 24 Monate. Zugriff hat nur die Projektverwaltung. Verschlüsselte Sicherungen der API-Datenbank und der Serverkonfiguration werden bis zu 14 Tage auf separater, vom Projekt kontrollierter Hardware aufbewahrt. Support-Nachrichten werden so lange aufbewahrt, wie sie zur Klärung der Anfrage, damit verbundener Streitigkeiten oder gesetzlicher Pflichten nötig sind. Frage uns nach weiteren dienstspezifischen Fristen oder einem bestimmten Bericht.

## Auswahl und Rechte

Du kannst Auskunft, Berichtigung, Löschung oder Einschränkung verlangen und einer Verarbeitung aufgrund berechtigter Interessen widersprechen. Datenübertragbarkeit gilt, wenn ihre gesetzlichen Voraussetzungen erfüllt sind.

Kontaktiere [privacy@terento.app](mailto:privacy@terento.app). Wir antworten normalerweise innerhalb eines Monats und erklären eine gesetzlich zulässige Verlängerung. Berichte sind nicht mit einem Konto oder einer direkten Gerätekennung verknüpft; wir benötigen eventuell Angaben, um deinen Bericht zu finden. Du kannst dich bei der [litauischen Datenschutzaufsicht VDAI](https://vdai.lrv.lt/) oder einer anderen zuständigen Aufsichtsbehörde beschweren.

## Technische Diagnosefelder

Kompatibilitätsberichte können außerdem eine bereinigte MTP-Modellbezeichnung, USB VID/PID, Transport, Identitätsquellenkategorie (nie den Kennungswert), Kartenausgaben, Zeitstempel, zufällige Ereignis-/Vorgangs-IDs, Fehlerphase, zugelassene App-/native Fehlercodes, Schreib-/Bereinigungsstatus und groben Fortschritt enthalten. Eigene Importe nutzen grobe Quellenbezeichnungen. Keiner der Ströme sendet Manifeste, MTP-Objekt-IDs, Karten-Hashes oder ungefilterte Fehlertexte.

Berichte können zusätzlich die ursprüngliche XML-Modellbeschreibung (bis zu 160 Zeichen) und den Modellproduktcode (bis zu 64 ASCII-Buchstaben, Ziffern oder Bindestrichen) enthalten. Diese beschreiben ein Produktmodell, keine einzelne Uhr. Vollständige XML-Dokumente, Unit IDs und Seriennummern sind ausgeschlossen. Modellcode-Zuordnungen und administrative Korrekturen werden getrennt vom ursprünglichen Bericht gespeichert.

Aktualisiert: 10. Oktober 2026.
