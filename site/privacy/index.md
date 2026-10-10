---
title: "Privacy — Terento"
canonical: https://terento.app/privacy/
---

# Privacy

This notice covers the Terento website, the macOS app and the web installer. No account is needed. Your maps and device records stay on your Mac or in your browser; the limited diagnostics and statistics described below are shared separately.

## Who to contact

Data controller: private individual. Read [About Terento](https://terento.app/about/) or contact [privacy@terento.app](mailto:privacy@terento.app) about your data.

## App diagnostics

Two diagnostic streams are enabled by default to improve installation reliability and compatibility. There is no sharing choice during installation. Turn either stream off in **Terento → Diagnostics** without limiting the app. This stops future sharing and clears that stream’s unsent queue; uploaded reports cannot be deleted from the app. Privacy-rights requests can be sent to the contact above.

- **Compatibility:** watch model and firmware, app and macOS versions, selected provider/maps, installation result and limited technical error information.
- **Map usage:** provider, map/region, download or installation outcome, time, app build and random operation/event IDs. Custom `.img` imports are excluded from this stream.

Reports exclude Garmin Unit IDs, serial-number values, account details, local paths, map files and raw logs. Individual reports are private; only reviewed aggregate compatibility results are published. The basis is legitimate interests in improving reliability and device coverage, under GDPR Article 6(1)(f).

## Web installer

The web installer lets you install maps on your watch from Google Chrome, without the app. Chrome reads what it needs from the watch, such as its model, free space and maps, on your computer.

When you choose a map, Terento’s server downloads it from the original provider and passes it to your browser. The copy is made for your request only, is not shared and is deleted once your browser has it, or after two hours if it is not collected. The provider sees Terento’s server, not you. For each copy, the server keeps a record of the map (provider, map, region and release), its size, how much of it reached your browser, the times and the result, with nothing about you, your browser or your watch. These records are kept for 24 months.

The page sends Terento short notes that do not identify you, one for each step: whether this browser can be used, whether the watch connected and how each map installation, update or removal ended. They include:

- the watch model and software version
- the operating system and browser, with their main version numbers
- the map provider, the map, its size range and whether it was a new installation or an update
- the step that failed, a fixed reason code, standard error codes from the browser, our server or the watch, and how long writing and checking took
- a random code created each time the page opens, so the steps of one visit can be grouped

They never include your watch’s serial number or Unit ID, your IP address, file names, the list of maps on your watch or error text. Your IP address is held briefly in memory to limit how many requests one computer can make, and is not stored. The notes show us which watches, systems and browsers work and help us fix what fails. The basis is legitimate interests under GDPR Article 6(1)(f). There is no switch on the page; contact us to object. Individual notes are private and kept for 24 months.

Some data stays in your browser, not on our server: which maps the web installer installed and on which watch, so it can update or remove them safely later; a temporary copy of a map until it is installed; and the language you choose. To recognise the watch, it stores a one-way code made from the watch details and a random value, which cannot be turned back into the serial number. Clearing the web installer’s site data in Chrome removes all of this. The web installer does not load website statistics.

## Website and app connections

Website, web installer, API, catalog and app-update requests may expose your IP address and request metadata to hosting and security providers. In the app, catalog maps download directly from Freizeitkarte, OpenTopoMap, MapRando or BBBike, whose privacy practices apply to those connections. The app’s launch update check retrieves release metadata, not an app download.

These connections serve content, provide requested app functions and protect against abuse. Security processing relies on legitimate interests under GDPR Article 6(1)(f).

## Help and public issues

If you email us, we receive your address, message and anything you attach, to answer your request and investigate the problem. Do not send map files, credentials or private device identifiers. Support handling relies on legitimate interests in responding to requests and maintaining the app.

A GitHub issue is separate from automatic diagnostics: you review and submit it, and its content and GitHub account name may be public. [GitHub’s privacy statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement) applies. Optional donations take place on [Buy Me a Coffee](https://www.buymeacoffee.com/privacy-policy), which processes payment-related information under its own terms.

## Support reports

Where the app offers to send a support report to Terento, a report is sent only when you choose to send it, after you have seen its content. It contains the sanitised issue details also used for GitHub reports: app and macOS versions, watch model and variant, the failed step, error category and message, map provider and region, and timings, plus any description you add. It excludes serial numbers, Unit IDs, account details, local paths, raw logs and map files, and no GitHub account is needed. Do not include personal information in the description.

Support reports are used only to diagnose the reported problem, are not used for statistics and are kept for 12 months. Access is restricted to project administration; your IP address is not stored with the report. The basis is legitimate interests in answering your request and maintaining the app, under GDPR Article 6(1)(f).

## Website statistics and browser storage

Umami loads for all visitors to measure page visits, link clicks and download events. It does not use tracking cookies. It may process page/referrer URLs, browser, operating system, device and approximate location information. UTM values in links describe campaign sources. Terento passes those values through URLs without storing campaigns in your browser. Statistics support site improvement and campaign measurement under legitimate interests, GDPR Article 6(1)(f). There is no analytics consent banner or on-site analytics switch; contact us to object. Website statistics are separate from the app’s diagnostic settings.

The site remembers a language you choose as `terento-language` in local storage. This requested preference is separate from analytics. Cloudflare may use security cookies depending on its protection settings.

## Recipients and storage

Website, web installer, API and database hosting use Hostinger; Cloudflare delivers and protects website, web installer and API traffic. Umami runs at `stats.enduristas.lt`. See [Cloudflare](https://www.cloudflare.com/privacypolicy/) and [Hostinger](https://www.hostinger.com/legal/privacy-policy) for their processing information. Provider configurations may involve processing outside the EEA; contact us for details of applicable arrangements.

The retention policy for uploaded app diagnostics and web installer notes is 24 months. Access is restricted to project administration. Encrypted backups of the API database and server configuration are kept on separate equipment controlled by the project for up to 14 days. Support correspondence is kept while needed to resolve the request and related disputes or legal obligations. Contact us about other service-specific storage periods or a particular report.

## Your choices and rights

You may request access, correction, erasure or restriction and object to processing based on legitimate interests. Portability applies where its legal conditions are met.

Contact [privacy@terento.app](mailto:privacy@terento.app). We normally respond within one month; if a lawful extension is needed, we will explain it. Reports are not linked to an account or direct device identifier, so we may need information that helps locate yours. You may complain to the [Lithuanian State Data Protection Inspectorate (VDAI)](https://vdai.lrv.lt/) or another competent supervisory authority.

## Technical diagnostic fields

Compatibility reports may also include a sanitized MTP model label, USB VID/PID, transport, identity-source category (never the identifier value), map releases, timestamps, random event/operation IDs, failure stage, approved app/native error codes, write/cleanup status and coarse transfer progress. Custom imports use coarse custom-source labels. Neither stream sends manifests, MTP object IDs, map hashes or unfiltered error text.

Reports may additionally include the original XML model description (up to 160 characters) and model product code (up to 64 ASCII letters, digits or hyphens). These identify a product model, not an individual watch. Whole XML documents, Unit IDs and serial numbers are excluded. Model-code mappings and any administrator corrections are kept separately from the original report.

Updated: 10 October 2026.

# Datenschutz

Dieser Hinweis gilt für die Terento-Website, die macOS-App und den Web-Installer. Ein Konto ist nicht nötig. Karten und Gerätedaten bleiben auf deinem Mac oder in deinem Browser; die unten beschriebenen begrenzten Diagnosen und Statistiken werden getrennt übermittelt.

## Kontakt

Verantwortlicher: Privatperson. Lies [Über Terento](https://terento.app/de/about/) oder kontaktiere [privacy@terento.app](mailto:privacy@terento.app) bei Fragen zu deinen Daten.

## App-Diagnose

Zwei Diagnoseströme sind standardmäßig aktiviert, um Installation und Kompatibilität zu verbessern. Während der Installation gibt es keine Freigabeauswahl. Deaktiviere jeden Strom unter **Terento → Diagnostics**, ohne die App einzuschränken. Dies beendet künftige Übermittlungen und leert die jeweilige ungesendete Warteschlange. Hochgeladene Berichte können nicht in der App gelöscht werden; Datenschutzanfragen sind über den Kontakt oben möglich.

- **Kompatibilität:** Uhrenmodell und Firmware, App- und macOS-Version, gewählte Anbieter/Karten, Installationsergebnis und begrenzte technische Fehlerinformationen.
- **Kartennutzung:** Anbieter, Karte/Region, Download- oder Installationsergebnis, Zeit, App-Build und zufällige Vorgangs-/Ereignis-IDs. Eigene `.img`-Importe sind ausgeschlossen.

Berichte enthalten keine Garmin Unit IDs, Seriennummernwerte, Kontodaten, lokalen Pfade, Kartendateien oder Rohprotokolle. Einzelberichte sind privat; nur geprüfte zusammengefasste Kompatibilitätsergebnisse werden veröffentlicht. Grundlage sind berechtigte Interessen an Zuverlässigkeit und Geräteabdeckung nach Art. 6 Abs. 1 lit. f DSGVO.

## Web-Installer

Mit dem Web-Installer installierst du Karten aus Google Chrome auf deine Uhr, ohne die App. Chrome liest auf deinem Computer, was es von der Uhr braucht, etwa Modell, freien Speicher und Karten.

Wenn du eine Karte wählst, lädt der Terento-Server sie vom ursprünglichen Anbieter und gibt sie an deinen Browser weiter. Die Kopie entsteht nur für deine Anfrage, wird nicht geteilt und gelöscht, sobald dein Browser sie hat, oder nach zwei Stunden, wenn sie nicht abgeholt wird. Der Anbieter sieht den Terento-Server, nicht dich. Zu jeder Kopie speichert der Server einen Eintrag über die Karte (Anbieter, Karte, Region und Version), ihre Größe, wie viel davon deinen Browser erreicht hat, die Zeiten und das Ergebnis, ohne Angaben zu dir, deinem Browser oder deiner Uhr. Diese Einträge werden 24 Monate aufbewahrt.

Die Seite sendet Terento zu jedem Schritt kurze Meldungen, die dich nicht identifizieren: ob dieser Browser nutzbar ist, ob die Uhr verbunden wurde und wie jede Installation, Aktualisierung oder Entfernung einer Karte ausging. Sie enthalten:

- Uhrenmodell und Softwareversion
- Betriebssystem und Browser mit ihrer Hauptversion
- Kartenanbieter, Karte, Größenbereich und ob es eine neue Installation oder ein Update war
- den fehlgeschlagenen Schritt, einen festen Grundcode, Standard-Fehlercodes von Browser, Server oder Uhr und die Dauer von Schreiben und Prüfen
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

# Confidentialité

Cet avis concerne le site Terento, l’application macOS et l’installateur web. Aucun compte n’est nécessaire. Vos cartes et données d’appareil restent sur votre Mac ou dans votre navigateur ; les diagnostics et statistiques limités décrits ci-dessous sont transmis séparément.

## Contact

Responsable du traitement : particulier. Consultez [À propos de Terento](https://terento.app/fr/about/) ou contactez [privacy@terento.app](mailto:privacy@terento.app) au sujet de vos données.

## Diagnostics de l’application

Deux flux sont activés par défaut pour améliorer la fiabilité et la compatibilité. Il n’y a pas de choix de partage pendant l’installation. Désactivez chaque flux dans **Terento → Diagnostics** sans limiter l’application. Cela arrête les futurs envois et vide la file correspondante non envoyée. Les rapports transmis ne peuvent pas être supprimés depuis l’application ; utilisez le contact ci-dessus pour vos demandes.

- **Compatibilité :** modèle et micrologiciel de la montre, versions de l’application et de macOS, fournisseur/cartes sélectionnés, résultat et informations techniques limitées sur les erreurs.
- **Utilisation des cartes :** fournisseur, carte/région, résultat du téléchargement ou de l’installation, heure, build et identifiants aléatoires d’opération/événement. Les imports `.img` personnels sont exclus.

Les rapports excluent les Garmin Unit IDs, valeurs de numéros de série, comptes, chemins locaux, cartes et journaux bruts. Les rapports individuels sont privés ; seuls des résultats agrégés de compatibilité vérifiés sont publiés. Le fondement est l’intérêt légitime à améliorer la fiabilité et la couverture des appareils, selon l’article 6(1)(f) du RGPD.

## Installateur web

L’installateur web permet d’installer des cartes sur votre montre depuis Google Chrome, sans l’application. Chrome lit sur votre ordinateur ce dont il a besoin, comme le modèle de la montre, l’espace libre et les cartes.

Quand vous choisissez une carte, le serveur de Terento la télécharge depuis le fournisseur d’origine et la transmet à votre navigateur. Cette copie est faite pour votre seule demande, n’est pas partagée et est supprimée dès que votre navigateur l’a reçue, ou après deux heures si elle n’est pas récupérée. Le fournisseur voit le serveur de Terento, pas vous. Pour chaque copie, le serveur conserve un enregistrement de la carte (fournisseur, carte, région et version), de sa taille, de la part reçue par votre navigateur, des horaires et du résultat, sans rien sur vous, votre navigateur ou votre montre. Ces enregistrements sont conservés 24 mois.

La page envoie à Terento, à chaque étape, de courtes notes qui ne vous identifient pas : si ce navigateur peut être utilisé, si la montre s’est connectée et comment chaque installation, mise à jour ou suppression de carte s’est terminée. Elles contiennent :

- le modèle de la montre et sa version logicielle
- le système d’exploitation et le navigateur, avec leur version principale
- le fournisseur, la carte, sa tranche de taille et s’il s’agit d’une nouvelle installation ou d’une mise à jour
- l’étape en échec, un code de motif fixe, des codes d’erreur standard du navigateur, de notre serveur ou de la montre, et la durée d’écriture et de vérification
- un code aléatoire créé à chaque ouverture de la page, pour regrouper les étapes d’une même visite

Elles ne contiennent jamais le numéro de série ou l’Unit ID de votre montre, votre adresse IP, des noms de fichiers, la liste des cartes de votre montre ni de texte d’erreur. Votre adresse IP n’est gardée que brièvement en mémoire pour limiter le nombre de requêtes d’un même ordinateur, et n’est pas enregistrée. Ces notes nous montrent quelles montres et quels systèmes et navigateurs fonctionnent et nous aident à corriger les échecs. La base est l’intérêt légitime selon l’article 6(1)(f) du RGPD. La page n’a pas d’interrupteur ; contactez-nous pour vous opposer. Les notes individuelles sont privées et conservées 24 mois.

Certaines données restent dans votre navigateur, pas sur notre serveur : les cartes installées par l’installateur web et sur quelle montre, pour pouvoir les mettre à jour ou les supprimer en toute sécurité, une copie temporaire d’une carte jusqu’à son installation et la langue choisie. Pour reconnaître la montre, il enregistre un code à sens unique tiré des données de la montre et d’une valeur aléatoire, qui ne permet pas de retrouver le numéro de série. Effacer dans Chrome les données du site de l’installateur web supprime tout cela. L’installateur web ne charge pas les statistiques du site.

## Connexions du site et de l’application

Les requêtes au site, à l’installateur web, à l’API, au catalogue et aux mises à jour peuvent communiquer votre adresse IP et des métadonnées aux hébergeurs et services de sécurité. Dans l’application, les cartes du catalogue sont téléchargées directement depuis Freizeitkarte, OpenTopoMap, MapRando ou BBBike ; leurs règles de confidentialité s’appliquent à ces connexions. La vérification au démarrage récupère des informations de version, pas l’application.

Ces connexions fournissent le contenu et les fonctions demandées et protègent contre les abus. Le traitement de sécurité repose sur l’intérêt légitime selon l’article 6(1)(f) du RGPD.

## Assistance et signalements publics

Si vous nous écrivez, nous recevons votre adresse, message et pièces jointes pour répondre et examiner le problème. N’envoyez pas de cartes, d’identifiants de connexion ou d’identifiants privés d’appareil. L’assistance repose sur l’intérêt légitime à répondre aux demandes et maintenir l’application.

Un ticket GitHub est distinct des diagnostics automatiques : vous le vérifiez et l’envoyez ; son contenu et votre nom de compte peuvent être publics. La [politique de GitHub](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement) s’applique. Les dons facultatifs passent par [Buy Me a Coffee](https://www.buymeacoffee.com/privacy-policy), qui traite les données de paiement selon ses conditions.

## Rapports d’assistance

Lorsque l’application propose d’envoyer un rapport d’assistance à Terento, le rapport n’est envoyé que si vous choisissez de l’envoyer, après en avoir vu le contenu. Il contient les détails nettoyés également utilisés pour les rapports GitHub : versions de l’application et de macOS, modèle et variante de la montre, étape en échec, catégorie et message d’erreur, fournisseur et région de la carte, durées, ainsi que la description que vous ajoutez. Il exclut les numéros de série, Unit IDs, comptes, chemins locaux, journaux bruts et cartes ; aucun compte GitHub n’est nécessaire. N’indiquez pas de données personnelles dans la description.

Les rapports d’assistance servent uniquement à diagnostiquer le problème signalé, ne sont pas utilisés pour les statistiques et sont conservés 12 mois. L’accès est réservé à l’administration du projet ; votre adresse IP n’est pas enregistrée avec le rapport. Le fondement est l’intérêt légitime à répondre à votre demande et maintenir l’application, selon l’article 6(1)(f) du RGPD.

## Statistiques et stockage du navigateur

Umami est chargé pour tous les visiteurs pour mesurer les pages vues, clics et téléchargements. Il n’utilise pas de cookies de suivi. Il peut traiter les URL de page/provenance, navigateur, système, appareil et localisation approximative. Les valeurs UTM des liens décrivent les sources de campagne. Terento les transmet dans les URL sans stocker les campagnes dans votre navigateur. Les statistiques servent à améliorer le site et mesurer les campagnes sur la base de l’intérêt légitime, article 6(1)(f) du RGPD. Il n’y a ni bandeau de consentement analytique ni interrupteur sur le site ; contactez-nous pour vous opposer. Ces statistiques sont distinctes des réglages de diagnostic de l’app.

Une langue choisie est mémorisée sous `terento-language` dans le stockage local. Cette préférence demandée est distincte de l’analytique. Cloudflare peut utiliser des cookies de sécurité selon ses réglages.

## Destinataires et conservation

Le site, l’installateur web, l’API et la base de données utilisent Hostinger ; Cloudflare assure la diffusion et la protection du trafic. Umami fonctionne à `stats.enduristas.lt`. Consultez [Cloudflare](https://www.cloudflare.com/privacypolicy/) et [Hostinger](https://www.hostinger.com/legal/privacy-policy) pour leurs traitements. Les configurations peuvent impliquer des traitements hors EEE ; contactez-nous pour les modalités applicables.

La politique de conservation des diagnostics transmis et des notes de l’installateur web est de 24 mois. L’accès est réservé à l’administration du projet. Des sauvegardes chiffrées de la base de données de l’API et de la configuration du serveur sont conservées jusqu’à 14 jours sur un équipement distinct contrôlé par le projet. Les échanges d’assistance sont conservés tant que nécessaires au traitement de la demande, des litiges associés ou des obligations légales. Contactez-nous au sujet d’autres durées propres aux services ou d’un rapport précis.

## Vos choix et droits

Vous pouvez demander accès, rectification, effacement ou limitation et vous opposer aux traitements fondés sur l’intérêt légitime. La portabilité s’applique lorsque ses conditions légales sont réunies.

Écrivez à [privacy@terento.app](mailto:privacy@terento.app). Nous répondons normalement sous un mois et expliquons toute prolongation légale. Les rapports ne sont pas liés à un compte ou identifiant direct d’appareil ; des précisions peuvent être nécessaires pour retrouver le vôtre. Vous pouvez saisir l’ [autorité lituanienne VDAI](https://vdai.lrv.lt/) ou une autre autorité compétente.

## Champs techniques des diagnostics

La compatibilité peut aussi inclure un libellé MTP nettoyé, USB VID/PID, transport, catégorie de source d’identité (jamais sa valeur), versions des cartes, horodatages, identifiants aléatoires, étape d’échec, codes d’erreur autorisés, état d’écriture/nettoyage et progression approximative. Les imports personnels utilisent des catégories générales. Aucun flux n’envoie de manifestes, identifiants d’objets MTP, empreintes de cartes ou erreurs non filtrées.

Les rapports peuvent aussi contenir la description originale du modèle XML (160 caractères maximum) et son code produit (64 lettres ASCII, chiffres ou traits d’union maximum). Ces données désignent un modèle, pas une montre individuelle. Les documents XML complets, Unit IDs et numéros de série sont exclus. Les correspondances des codes et les corrections administratives sont conservées séparément du rapport original.

Mise à jour : 10 octobre 2026.

# Prywatność

Informacja dotyczy witryny Terento, aplikacji macOS i instalatora webowego. Korzystanie z nich nie wymaga konta. Mapy i dane urządzenia pozostają na Twoim Macu lub w przeglądarce; ograniczona diagnostyka i statystyki opisane poniżej są wysyłane oddzielnie.

## Kontakt

Administrator danych: osoba prywatna. Przeczytaj [O Terento](https://terento.app/pl/about/) lub napisz do [privacy@terento.app](mailto:privacy@terento.app) w sprawie danych.

## Diagnostyka aplikacji

Dwa strumienie są domyślnie włączone, aby poprawiać niezawodność i zgodność. Podczas instalacji nie ma wyboru udostępniania. Każdy strumień można wyłączyć w **Terento → Diagnostics** bez ograniczania aplikacji. Zatrzymuje to przyszłe wysyłanie i usuwa niewysłaną kolejkę tego strumienia. Wysłanych raportów nie można usunąć z aplikacji; żądania dotyczące prywatności kieruj na adres powyżej.

- **Zgodność:** model i oprogramowanie zegarka, wersje aplikacji i macOS, dostawca/mapy, wynik instalacji i ograniczone techniczne informacje o błędach.
- **Użycie map:** dostawca, mapa/region, wynik pobrania lub instalacji, czas, build aplikacji i losowe identyfikatory operacji/zdarzeń. Własne importy `.img` są wyłączone z tego strumienia.

Raporty nie zawierają Garmin Unit IDs, wartości numerów seryjnych, kont, lokalnych ścieżek, map ani surowych logów. Raporty indywidualne są prywatne; publikowane są tylko sprawdzone zbiorcze wyniki zgodności. Podstawą jest uzasadniony interes w poprawie niezawodności i obsługi urządzeń, zgodnie z art. 6 ust. 1 lit. f RODO.

## Instalator webowy

Instalator webowy pozwala instalować mapy na zegarku z Google Chrome, bez aplikacji. Chrome odczytuje z zegarka na Twoim komputerze to, czego potrzebuje, np. model, wolne miejsce i mapy.

Gdy wybierzesz mapę, serwer Terento pobiera ją od pierwotnego dostawcy i przekazuje do Twojej przeglądarki. Kopia powstaje tylko dla Twojego żądania, nie jest udostępniana innym i jest usuwana, gdy przeglądarka ją otrzyma, albo po dwóch godzinach, jeśli nie zostanie odebrana. Dostawca widzi serwer Terento, nie Ciebie. Dla każdej kopii serwer zapisuje informację o mapie (dostawca, mapa, region i wydanie), jej rozmiarze, tym, ile dotarło do przeglądarki, czasach i wyniku, bez danych o Tobie, Twojej przeglądarce czy zegarku. Te zapisy są przechowywane przez 24 miesiące.

Strona wysyła do Terento krótkie informacje o każdym kroku, które nie pozwalają Cię zidentyfikować: czy tej przeglądarki można użyć, czy zegarek się połączył i jak zakończyła się każda instalacja, aktualizacja lub usunięcie mapy. Zawierają one:

- model zegarka i wersję oprogramowania
- system operacyjny i przeglądarkę z ich główną wersją
- dostawcę, mapę, przedział rozmiaru oraz to, czy była to nowa instalacja, czy aktualizacja
- krok, który się nie powiódł, stały kod przyczyny, standardowe kody błędów przeglądarki, naszego serwera lub zegarka oraz czas zapisu i sprawdzania
- losowy kod tworzony przy każdym otwarciu strony, aby połączyć kroki jednej wizyty

Nigdy nie zawierają numeru seryjnego ani Unit ID zegarka, Twojego adresu IP, nazw plików, listy map na zegarku ani tekstu błędów. Adres IP jest przez chwilę trzymany w pamięci, aby ograniczyć liczbę żądań z jednego komputera, i nie jest zapisywany. Informacje te pokazują nam, które zegarki, systemy i przeglądarki działają, i pomagają naprawiać błędy. Podstawą jest uzasadniony interes zgodnie z art. 6 ust. 1 lit. f RODO. Na stronie nie ma przełącznika; skontaktuj się, aby zgłosić sprzeciw. Pojedyncze informacje są prywatne i przechowywane przez 24 miesiące.

Część danych zostaje w Twojej przeglądarce, nie na naszym serwerze: które mapy instalator webowy zainstalował i na którym zegarku, aby później bezpiecznie je aktualizować lub usuwać, tymczasowa kopia mapy do czasu instalacji oraz wybrany język. Aby rozpoznać zegarek, zapisuje jednokierunkowy kod utworzony z danych zegarka i losowej wartości, z którego nie da się odtworzyć numeru seryjnego. Wyczyszczenie w Chrome danych witryny instalatora webowego usuwa to wszystko. Instalator webowy nie ładuje statystyk witryny.

## Połączenia witryny i aplikacji

Żądania do witryny, instalatora webowego, API, katalogu i aktualizacji mogą ujawniać adres IP i metadane dostawcom hostingu i zabezpieczeń. W aplikacji mapy są pobierane bezpośrednio z Freizeitkarte, OpenTopoMap, MapRando lub BBBike; do tych połączeń mają zastosowanie ich zasady prywatności. Kontrola aktualizacji przy uruchomieniu pobiera informacje o wydaniu, nie aplikację.

Połączenia dostarczają treści i żądane funkcje oraz chronią przed nadużyciami. Przetwarzanie dla bezpieczeństwa opiera się na uzasadnionym interesie zgodnie z art. 6 ust. 1 lit. f RODO.

## Pomoc i publiczne zgłoszenia

Gdy piszesz do nas, otrzymujemy adres, wiadomość i załączniki, aby odpowiedzieć i zbadać problem. Nie wysyłaj map, danych logowania ani prywatnych identyfikatorów urządzeń. Obsługa opiera się na uzasadnionym interesie w odpowiadaniu na prośby i utrzymaniu aplikacji.

Zgłoszenie GitHub jest oddzielne od automatycznej diagnostyki: sprawdzasz i wysyłasz je samodzielnie, a treść i nazwa konta mogą być publiczne. Obowiązuje [polityka GitHub](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement). Dobrowolne wsparcie odbywa się przez [Buy Me a Coffee](https://www.buymeacoffee.com/privacy-policy), przetwarzające dane płatnicze na własnych zasadach.

## Raporty pomocy

Gdy aplikacja oferuje wysłanie raportu pomocy do Terento, raport jest wysyłany tylko wtedy, gdy zdecydujesz się go wysłać po zapoznaniu się z jego treścią. Zawiera oczyszczone informacje o problemie używane także w raportach GitHub: wersje aplikacji i macOS, model i wariant zegarka, etap, który się nie powiódł, kategorię i komunikat błędu, dostawcę i region mapy oraz czasy, a także opcjonalny opis. Nie zawiera numerów seryjnych, Unit IDs, danych kont, lokalnych ścieżek, surowych logów ani map; konto GitHub nie jest potrzebne. Nie podawaj w opisie danych osobowych.

Raporty pomocy służą wyłącznie do diagnozy zgłoszonego problemu, nie są używane w statystykach i są przechowywane przez 12 miesięcy. Dostęp ma administracja projektu; adres IP nie jest zapisywany z raportem. Podstawą jest uzasadniony interes w odpowiedzi na zgłoszenie i utrzymaniu aplikacji, zgodnie z art. 6 ust. 1 lit. f RODO.

## Statystyki i pamięć przeglądarki

Umami jest ładowane dla wszystkich odwiedzających, aby mierzyć odsłony, kliknięcia i pobrania. Nie używa śledzących plików cookie. Może przetwarzać adresy stron i odsyłaczy, przeglądarkę, system, urządzenie i przybliżoną lokalizację. Wartości UTM w linkach opisują źródła kampanii. Terento przekazuje je w adresach URL bez zapisywania kampanii w przeglądarce. Statystyki służą ulepszaniu witryny i pomiarowi kampanii na podstawie uzasadnionego interesu, art. 6 ust. 1 lit. f RODO. Nie ma banera zgody ani przełącznika analityki w witrynie; skontaktuj się, aby zgłosić sprzeciw. Statystyki są oddzielne od ustawień diagnostyki aplikacji.

Wybrany język jest zapisywany jako `terento-language` w pamięci lokalnej. Ta żądana preferencja jest oddzielna od analityki. Cloudflare może używać plików cookie bezpieczeństwa zależnie od ustawień ochrony.

## Odbiorcy i przechowywanie

Witryna, instalator webowy, API i baza danych korzystają z Hostinger; Cloudflare dostarcza i chroni ruch. Umami działa pod `stats.enduristas.lt`. Informacje dostawców znajdziesz w [Cloudflare](https://www.cloudflare.com/privacypolicy/) i [Hostinger](https://www.hostinger.com/legal/privacy-policy). Konfiguracje mogą obejmować przetwarzanie poza EOG; zapytaj nas o stosowane rozwiązania.

Polityka przechowywania wysłanej diagnostyki i informacji z instalatora webowego wynosi 24 miesiące. Dostęp ma administracja projektu. Zaszyfrowane kopie zapasowe bazy danych API i konfiguracji serwera są przechowywane do 14 dni na osobnym sprzęcie kontrolowanym przez projekt. Korespondencja pomocy jest przechowywana tak długo, jak wymaga obsługa zgłoszenia, powiązanych sporów lub obowiązków prawnych. Zapytaj o inne okresy właściwe dla usług lub konkretny raport.

## Twoje wybory i prawa

Możesz żądać dostępu, sprostowania, usunięcia lub ograniczenia oraz sprzeciwić się przetwarzaniu opartemu na uzasadnionym interesie. Przenoszenie danych przysługuje po spełnieniu warunków prawnych.

Napisz do [privacy@terento.app](mailto:privacy@terento.app). Zwykle odpowiadamy w ciągu miesiąca i wyjaśniamy zgodne z prawem przedłużenie. Raporty nie są połączone z kontem lub bezpośrednim identyfikatorem urządzenia, więc możemy potrzebować informacji pozwalających odnaleźć Twój raport. Możesz złożyć skargę do [litewskiego organu VDAI](https://vdai.lrv.lt/) lub innego właściwego organu.

## Techniczne pola diagnostyczne

Zgodność może obejmować oczyszczoną nazwę modelu MTP, USB VID/PID, transport, kategorię źródła tożsamości (nigdy wartość identyfikatora), wydania map, czas, losowe identyfikatory, etap awarii, dozwolone kody błędów aplikacji/systemu, stan zapisu/czyszczenia i przybliżony postęp. Importy własne mają ogólne etykiety źródła. Żaden strumień nie wysyła manifestów, ID obiektów MTP, skrótów map ani nieprzefiltrowanych błędów.

Raporty mogą dodatkowo zawierać oryginalny opis modelu z XML (do 160 znaków) i kod produktu modelu (do 64 liter ASCII, cyfr lub łączników). Dane te określają model produktu, a nie pojedynczy zegarek. Pełne dokumenty XML, Unit ID i numery seryjne są wykluczone. Powiązania kodów modeli i poprawki administratora są przechowywane oddzielnie od oryginalnego raportu.

Aktualizacja: 10 października 2026 r.

# Soukromí

Oznámení se vztahuje na web Terento, aplikaci macOS a webový instalátor. Nevyžadují účet. Mapy a záznamy zařízení zůstávají na vašem Macu nebo v prohlížeči; omezená diagnostika a statistiky popsané níže se sdílejí samostatně.

## Kontakt

Správce údajů: soukromá osoba. Přečtěte si [O Terento](https://terento.app/cs/about/) nebo napište na [privacy@terento.app](mailto:privacy@terento.app) ohledně svých údajů.

## Diagnostika aplikace

Dva proudy jsou standardně zapnuté pro zlepšení spolehlivosti a kompatibility. Během instalace není volba sdílení. Každý proud vypnete v **Terento → Diagnostics** bez omezení aplikace. Zastaví se další sdílení a smaže jeho neodeslaná fronta. Odeslané zprávy nelze smazat v aplikaci; žádosti ohledně soukromí zašlete na kontakt výše.

- **Kompatibilita:** model a firmware hodinek, verze aplikace a macOS, poskytovatel/mapy, výsledek instalace a omezené technické údaje o chybách.
- **Použití map:** poskytovatel, mapa/oblast, výsledek stažení či instalace, čas, build a náhodná ID operací/událostí. Vlastní importy `.img` jsou z tohoto proudu vyloučeny.

Zprávy neobsahují Garmin Unit IDs, hodnoty sériových čísel, účty, místní cesty, mapy ani surové protokoly. Jednotlivé zprávy jsou soukromé; zveřejňují se jen ověřené souhrnné výsledky kompatibility. Základem jsou oprávněné zájmy na spolehlivosti a pokrytí zařízení podle čl. 6 odst. 1 písm. f GDPR.

## Webový instalátor

Webový instalátor umožňuje instalovat mapy do hodinek z Google Chrome, bez aplikace. Chrome na vašem počítači přečte z hodinek, co potřebuje, například model, volné místo a mapy.

Když zvolíte mapu, server Terento ji stáhne od původního poskytovatele a předá ji vašemu prohlížeči. Kopie vzniká jen pro váš požadavek, nesdílí se a smaže se, jakmile ji prohlížeč má, nebo po dvou hodinách, pokud si ji nevyzvedne. Poskytovatel vidí server Terento, ne vás. Ke každé kopii server ukládá záznam o mapě (poskytovatel, mapa, oblast a vydání), její velikosti, kolik z ní dorazilo do prohlížeče, časech a výsledku, bez údajů o vás, vašem prohlížeči nebo hodinkách. Tyto záznamy se uchovávají 24 měsíců.

Stránka posílá Terento o každém kroku krátké zprávy, které vás neidentifikují: zda lze tento prohlížeč použít, zda se hodinky připojily a jak skončila každá instalace, aktualizace nebo odebrání mapy. Obsahují:

- model hodinek a verzi softwaru
- operační systém a prohlížeč s jejich hlavní verzí
- poskytovatele, mapu, rozsah velikosti a zda šlo o novou instalaci, nebo aktualizaci
- krok, který selhal, pevný kód důvodu, standardní chybové kódy prohlížeče, našeho serveru nebo hodinek a dobu zápisu a kontroly
- náhodný kód vytvořený při každém otevření stránky, aby bylo možné spojit kroky jedné návštěvy

Nikdy neobsahují sériové číslo ani Unit ID hodinek, vaši IP adresu, názvy souborů, seznam map v hodinkách ani text chyb. IP adresa se jen krátce drží v paměti, aby se omezil počet požadavků z jednoho počítače, a neukládá se. Zprávy nám ukazují, které hodinky, systémy a prohlížeče fungují, a pomáhají opravovat chyby. Základem jsou oprávněné zájmy podle čl. 6 odst. 1 písm. f GDPR. Stránka nemá přepínač; pro námitku nás kontaktujte. Jednotlivé zprávy jsou soukromé a uchovávají se 24 měsíců.

Některá data zůstávají ve vašem prohlížeči, ne na našem serveru: které mapy webový instalátor nainstaloval a do kterých hodinek, aby je později mohl bezpečně aktualizovat nebo odebrat, dočasná kopie mapy do dokončení instalace a zvolený jazyk. K rozpoznání hodinek ukládá jednosměrný kód vytvořený z údajů hodinek a náhodné hodnoty, ze kterého nelze zjistit sériové číslo. Vymazáním dat webu webového instalátoru v Chromu se to vše odstraní. Webový instalátor nenačítá statistiky webu.

## Připojení webu a aplikace

Požadavky na web, webový instalátor, API, katalog a aktualizace mohou poskytovatelům hostingu a zabezpečení zpřístupnit IP adresu a metadata. V aplikaci se mapy stahují přímo od Freizeitkarte, OpenTopoMap, MapRando či BBBike; pro tato připojení platí jejich pravidla soukromí. Kontrola při spuštění načítá informace o vydání, nikoli aplikaci.

Připojení poskytují obsah, požadované funkce a ochranu před zneužitím. Bezpečnostní zpracování se opírá o oprávněné zájmy podle čl. 6 odst. 1 písm. f GDPR.

## Pomoc a veřejná hlášení

Pokud nám napíšete, obdržíme adresu, zprávu a přílohy pro odpověď a prošetření problému. Neposílejte mapy, přihlašovací údaje ani soukromé identifikátory zařízení. Podpora se opírá o oprávněné zájmy na vyřizování požadavků a údržbě aplikace.

GitHub issue je oddělené od automatické diagnostiky: sami jej zkontrolujete a odešlete; obsah a jméno účtu mohou být veřejné. Platí [pravidla GitHubu](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement). Dobrovolné příspěvky probíhají přes [Buy Me a Coffee](https://www.buymeacoffee.com/privacy-policy), které zpracovává platební údaje podle vlastních podmínek.

## Zprávy podpoře

Pokud aplikace nabízí odeslání zprávy podpoře Terento, zpráva se odešle jen tehdy, když se tak rozhodnete po zobrazení jejího obsahu. Obsahuje očištěné údaje o problému, které se používají i pro hlášení na GitHubu: verze aplikace a macOS, model a variantu hodinek, neúspěšný krok, kategorii a zprávu chyby, poskytovatele a oblast mapy a časové údaje, spolu s volitelným popisem. Neobsahuje sériová čísla, Unit IDs, účty, místní cesty, surové protokoly ani mapy; účet na GitHubu není potřeba. Do popisu neuvádějte osobní údaje.

Zprávy podpoře slouží jen k diagnostice nahlášeného problému, nepoužívají se pro statistiky a uchovávají se 12 měsíců. Přístup má správa projektu; vaše IP adresa se se zprávou neukládá. Základem jsou oprávněné zájmy na vyřízení vašeho požadavku a údržbě aplikace podle čl. 6 odst. 1 písm. f GDPR.

## Statistiky a úložiště prohlížeče

Umami se načítá všem návštěvníkům pro měření zobrazení, kliknutí a stažení. Nepoužívá sledovací cookies. Může zpracovávat URL stránky a odkazujícího webu, prohlížeč, systém, zařízení a přibližnou polohu. UTM v odkazech popisují zdroje kampaní. Terento je předává v URL bez ukládání kampaní do prohlížeče. Statistiky slouží zlepšování webu a měření kampaní na základě oprávněných zájmů, čl. 6 odst. 1 písm. f GDPR. Na webu není analytický souhlasový banner ani přepínač; pro námitku nás kontaktujte. Statistiky webu jsou oddělené od nastavení diagnostiky aplikace.

Vybraný jazyk se ukládá jako `terento-language` do místního úložiště. Tato vyžádaná preference je oddělena od analytiky. Cloudflare může podle nastavení ochrany používat bezpečnostní cookies.

## Příjemci a uchovávání

Web, webový instalátor, API a databáze využívají Hostinger; Cloudflare poskytuje a chrání provoz. Umami běží na `stats.enduristas.lt`. Podrobnosti poskytovatelů: [Cloudflare](https://www.cloudflare.com/privacypolicy/) a [Hostinger](https://www.hostinger.com/legal/privacy-policy). Konfigurace mohou zahrnovat zpracování mimo EHP; kontaktujte nás pro platná opatření.

Pravidlo uchovávání odeslané diagnostiky a zpráv webového instalátoru je 24 měsíců. Přístup má správa projektu. Šifrované zálohy databáze API a konfigurace serveru se uchovávají až 14 dní na samostatném zařízení pod kontrolou projektu. Korespondence podpory se uchovává po dobu potřebnou k vyřízení žádosti, souvisejících sporů nebo právních povinností. Zeptejte se na další lhůty konkrétních služeb nebo zprávu.

## Vaše volby a práva

Můžete žádat přístup, opravu, výmaz či omezení a vznést námitku proti zpracování založenému na oprávněných zájmech. Přenositelnost platí při splnění zákonných podmínek.

Kontaktujte [privacy@terento.app](mailto:privacy@terento.app). Běžně odpovíme do měsíce a případné zákonné prodloužení vysvětlíme. Zprávy nejsou spojeny s účtem ani přímým identifikátorem zařízení; k nalezení vaší zprávy můžeme potřebovat další údaje. Stížnost můžete podat u [litevského úřadu VDAI](https://vdai.lrv.lt/) nebo jiného příslušného dozorového úřadu.

## Technická diagnostická pole

Kompatibilita může zahrnovat očištěný název modelu MTP, USB VID/PID, transport, kategorii zdroje identity (nikdy hodnotu identifikátoru), vydání map, čas, náhodná ID, fázi selhání, povolené chybové kódy, stav zápisu/úklidu a hrubý průběh. Vlastní importy používají obecná označení zdroje. Žádný proud neposílá manifesty, ID objektů MTP, hashe map ani nefiltrované chyby.

Zprávy mohou navíc obsahovat původní popis modelu z XML (nejvýše 160 znaků) a produktový kód modelu (nejvýše 64 písmen ASCII, číslic nebo spojovníků). Tyto údaje označují model výrobku, nikoli jednotlivé hodinky. Celé dokumenty XML, Unit ID a sériová čísla jsou vyloučeny. Přiřazení kódů modelů a opravy správce se ukládají odděleně od původní zprávy.

Aktualizováno: 10. října 2026.

# Privacy

Questa informativa riguarda il sito Terento, l’app macOS e l’installer web. Non serve un account. Mappe e dati del dispositivo restano sul Mac o nel browser; la diagnostica e le statistiche limitate descritte sotto vengono condivise separatamente.

## Contatti

Titolare del trattamento: privato. Leggi [Informazioni su Terento](https://terento.app/it/about/) o scrivi a [privacy@terento.app](mailto:privacy@terento.app) per i tuoi dati.

## Diagnostica dell’app

Due flussi sono attivi per impostazione predefinita per migliorare affidabilità e compatibilità. Durante l’installazione non c’è una scelta di condivisione. Disattiva ciascun flusso in **Terento → Diagnostics** senza limitare l’app. Questo interrompe gli invii futuri e cancella la relativa coda non inviata. I rapporti inviati non si eliminano dall’app; usa il contatto sopra per le richieste sui dati.

- **Compatibilità:** modello e firmware dell’orologio, versioni app/macOS, fornitore/mappe scelti, esito e informazioni tecniche limitate sugli errori.
- **Uso delle mappe:** fornitore, mappa/regione, esito del download o installazione, ora, build e ID casuali di operazioni/eventi. Le importazioni `.img` personali sono escluse.

I rapporti escludono Garmin Unit IDs, valori dei numeri di serie, account, percorsi locali, mappe e log grezzi. I rapporti individuali sono privati; vengono pubblicati solo risultati aggregati di compatibilità verificati. La base è il legittimo interesse a migliorare affidabilità e copertura dei dispositivi, ai sensi dell’art. 6(1)(f) GDPR.

## Installer web

L’installer web ti permette di installare mappe sull’orologio da Google Chrome, senza l’app. Chrome legge dall’orologio, sul tuo computer, ciò che gli serve, come modello, spazio libero e mappe.

Quando scegli una mappa, il server di Terento la scarica dal fornitore originale e la passa al tuo browser. La copia è creata solo per la tua richiesta, non viene condivisa ed è eliminata appena il browser l’ha ricevuta, o dopo due ore se non viene ritirata. Il fornitore vede il server di Terento, non te. Per ogni copia il server conserva un registro della mappa (fornitore, mappa, regione e versione), della sua dimensione, di quanto è arrivato al browser, degli orari e dell’esito, senza nulla su di te, sul browser o sull’orologio. Questi registri sono conservati per 24 mesi.

La pagina invia a Terento, per ogni passaggio, brevi note che non ti identificano: se questo browser può essere usato, se l’orologio si è collegato e come si è conclusa ogni installazione, aggiornamento o rimozione di mappa. Contengono:

- modello dell’orologio e versione del software
- sistema operativo e browser, con la loro versione principale
- fornitore, mappa, fascia di dimensione e se si trattava di una nuova installazione o di un aggiornamento
- il passaggio non riuscito, un codice di motivo fisso, codici di errore standard del browser, del nostro server o dell’orologio e la durata di scrittura e verifica
- un codice casuale creato a ogni apertura della pagina, per raggruppare i passaggi di una visita

Non contengono mai numero di serie o Unit ID dell’orologio, il tuo indirizzo IP, nomi di file, l’elenco delle mappe sull’orologio o testi di errore. L’indirizzo IP resta solo brevemente in memoria per limitare quante richieste può fare un computer e non viene salvato. Le note ci mostrano quali orologi, sistemi e browser funzionano e ci aiutano a correggere gli errori. La base è il legittimo interesse ai sensi dell’art. 6(1)(f) GDPR. La pagina non ha un interruttore; contattaci per opporti. Le singole note sono private e conservate per 24 mesi.

Alcuni dati restano nel tuo browser, non sul nostro server: quali mappe l’installer web ha installato e su quale orologio, per poterle aggiornare o rimuovere in sicurezza in seguito, una copia temporanea di una mappa fino all’installazione e la lingua scelta. Per riconoscere l’orologio salva un codice a senso unico ricavato dai dati dell’orologio e da un valore casuale, da cui non si può risalire al numero di serie. Cancellare in Chrome i dati del sito dell’installer web rimuove tutto questo. L’installer web non carica le statistiche del sito.

## Connessioni del sito e dell’app

Le richieste al sito, all’installer web, API, catalogo e aggiornamenti possono comunicare IP e metadati ai fornitori di hosting e sicurezza. Nell’app le mappe si scaricano direttamente da Freizeitkarte, OpenTopoMap, MapRando o BBBike; a queste connessioni si applicano le loro regole privacy. Il controllo all’avvio recupera informazioni sulla versione, non l’app.

Le connessioni forniscono contenuti e funzioni richieste e proteggono dagli abusi. Il trattamento per sicurezza si basa sul legittimo interesse ai sensi dell’art. 6(1)(f) GDPR.

## Assistenza e segnalazioni pubbliche

Se ci scrivi, riceviamo indirizzo, messaggio e allegati per rispondere e analizzare il problema. Non inviare mappe, credenziali o identificativi privati del dispositivo. L’assistenza si basa sul legittimo interesse a rispondere alle richieste e mantenere l’app.

Una issue GitHub è distinta dalla diagnostica automatica: la controlli e invii tu; contenuti e nome account possono essere pubblici. Si applica l’ [informativa GitHub](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement). Le donazioni facoltative avvengono tramite [Buy Me a Coffee](https://www.buymeacoffee.com/privacy-policy), che tratta i dati di pagamento secondo le proprie condizioni.

## Rapporti di assistenza

Quando l’app offre di inviare un rapporto di assistenza a Terento, il rapporto viene inviato solo se scegli di inviarlo, dopo averne visto il contenuto. Contiene i dettagli ripuliti usati anche per le segnalazioni GitHub: versioni dell’app e di macOS, modello e variante dell’orologio, passaggio non riuscito, categoria e messaggio di errore, provider e regione della mappa e tempi, oltre all’eventuale descrizione che aggiungi. Esclude numeri di serie, Unit IDs, account, percorsi locali, log grezzi e mappe; non serve un account GitHub. Non inserire dati personali nella descrizione.

I rapporti di assistenza servono solo a diagnosticare il problema segnalato, non sono usati per statistiche e sono conservati per 12 mesi. L’accesso è riservato all’amministrazione del progetto; il tuo indirizzo IP non viene salvato con il rapporto. La base è il legittimo interesse a rispondere alla tua richiesta e mantenere l’app, ai sensi dell’art. 6(1)(f) GDPR.

## Statistiche e memoria del browser

Umami viene caricato per tutti i visitatori per misurare visualizzazioni, clic e download. Non usa cookie di tracciamento. Può trattare URL di pagina/provenienza, browser, sistema, dispositivo e posizione approssimativa. I valori UTM nei link descrivono le fonti delle campagne. Terento li trasmette tramite URL senza salvare campagne nel browser. Le statistiche servono a migliorare il sito e misurare le campagne sulla base del legittimo interesse, art. 6(1)(f) GDPR. Non ci sono banner di consenso analitico o interruttori sul sito; contattaci per opporti. Le statistiche sono separate dalle impostazioni diagnostiche dell’app.

La lingua scelta viene memorizzata come `terento-language` nella memoria locale. Questa preferenza richiesta è separata dall’analisi. Cloudflare può usare cookie di sicurezza secondo le impostazioni di protezione.

## Destinatari e conservazione

Sito, installer web, API e database usano Hostinger; Cloudflare distribuisce e protegge il traffico. Umami opera su `stats.enduristas.lt`. Consulta [Cloudflare](https://www.cloudflare.com/privacypolicy/) e [Hostinger](https://www.hostinger.com/legal/privacy-policy) per i loro trattamenti. Le configurazioni possono comportare trattamenti fuori dallo SEE; contattaci per le disposizioni applicabili.

La politica di conservazione della diagnostica inviata e delle note dell’installer web è di 24 mesi. L’accesso è riservato all’amministrazione del progetto. I backup cifrati del database dell’API e della configurazione del server sono conservati fino a 14 giorni su un dispositivo separato controllato dal progetto. La corrispondenza di assistenza è conservata finché necessaria per la richiesta, controversie collegate o obblighi legali. Chiedici altri periodi specifici dei servizi o informazioni su un rapporto.

## Scelte e diritti

Puoi richiedere accesso, rettifica, cancellazione o limitazione e opporti ai trattamenti basati sul legittimo interesse. La portabilità si applica quando ricorrono i requisiti legali.

Scrivi a [privacy@terento.app](mailto:privacy@terento.app). Normalmente rispondiamo entro un mese e spieghiamo eventuali proroghe previste dalla legge. I rapporti non sono associati a un account o identificatore diretto del dispositivo; potrebbero servire informazioni per individuare il tuo. Puoi presentare reclamo all’ [autorità lituana VDAI](https://vdai.lrv.lt/) o a un’altra autorità competente.

## Campi tecnici della diagnostica

La compatibilità può includere un nome modello MTP ripulito, USB VID/PID, trasporto, categoria dell’origine dell’identità (mai il valore), versioni mappe, orari, ID casuali, fase dell’errore, codici autorizzati app/nativi, stato scrittura/pulizia e avanzamento approssimativo. Gli import personali usano categorie generiche. Nessun flusso invia manifesti, ID oggetti MTP, hash delle mappe o errori non filtrati.

I rapporti possono includere anche la descrizione originale del modello XML (fino a 160 caratteri) e il codice prodotto del modello (fino a 64 lettere ASCII, cifre o trattini). Questi dati identificano un modello, non un singolo orologio. Sono esclusi documenti XML completi, Unit ID e numeri di serie. Le associazioni dei codici e le correzioni amministrative sono conservate separatamente dal rapporto originale.

Aggiornamento: 10 ottobre 2026.
