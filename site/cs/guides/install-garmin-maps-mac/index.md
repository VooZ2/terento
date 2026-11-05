---
title: "Bezplatné mapy do hodinek Garmin z Macu — Terento"
canonical: https://terento.app/cs/guides/install-garmin-maps-mac/
---

# Instalace bezplatných map do hodinek Garmin z Macu

Terento nainstaluje bezplatné mapy OpenStreetMap nebo váš vlastní mapový soubor do hodinek Garmin s podporou map. Sami nekopírujete žádné soubory a mapy od Garminu zůstanou beze změny.

[Stáhnout](https://terento.app/cs/download/)

Používáte Linux? [Nainstalujte mapy z prohlížeče](https://terento.app/cs/guides/install-garmin-maps-linux/).

## Co potřebujete

- Mac s Apple Silicon a macOS 13 nebo novějším
- Hodinky Garmin s podporou map
- USB kabel pro přenos dat

Po připojení Terento hodinky zkontroluje a řekne vám, zda do nich může nainstalovat mapy. Stránka [Kompatibilita](https://terento.app/cs/compatibility/) uvádí modely s úspěšnými instalacemi; chybějící model nemusí znamenat, že není podporovaný.

## Instalace mapy

1. Stáhněte a otevřete Terento

[Stáhněte Terento](https://terento.app/cs/download/), přetáhněte ho z obrazu disku do složky Aplikace a otevřete ho odtud. Při prvním otevření se macOS zeptá, zda otevřít aplikaci staženou z internetu: zvolte Otevřít.

2. Připojte hodinky

Ukončete Garmin Express, pokud je otevřený. Odemkněte hodinky a připojte je k Macu USB kabelem pro přenos dat, ne kabelem jen pro nabíjení. Pokud se macOS zeptá, zda povolit připojení příslušenství, zvolte Povolit. Terento hodinky najde do 1–2 minut a ověří, zda do nich může nainstalovat mapy.

[Mac nevidí hodinky Garmin](https://terento.app/cs/guides/troubleshooting/#connect-watch)

Terento zobrazuje připojené hodinky Garmin a stav rozpoznání
Terento před instalací rozpozná připojené hodinky Garmin.

3. Vyberte mapu

Vyberte mapu z katalogu nebo přidejte vlastní kompatibilní soubor .img. [Porovnejte styly map](https://terento.app/cs/map-styles/) a podívejte se, jak každá mapa zobrazuje silnice a stezky.

1. Vybrat z katalogu

Vyberte poskytovatele a oblast z katalogu.

2. Přidat vlastní mapu

Přidejte kompatibilní mapu .img z Macu.

Terento zobrazuje poskytovatele, oblasti map třetích stran a dostupné místo v Garminu
Vyberte mapu z katalogu nebo přidejte vlastní kompatibilní soubor.

4. Instalujte

Spusťte instalaci a nechte hodinky připojené, dokud Terento neoznámí, že je mapa připravená. Potom hodinky odpojte.

Terento zobrazuje dokončenou instalaci mapy do hodinek Garmin
Nechte hodinky připojené do dokončení přenosu a kontroly.

## Zobrazení mapy v hodinkách

Odpojte hodinky, otevřete jejich nastavení map a novou mapu zapněte. Pokud v seznamu není, hodinky restartujte. Pokud stejnou oblast pokrývá více map, vypněte ty, které vidět nechcete.

Mapa stále není vidět? Napište na [hello@terento.app](mailto:hello@terento.app?subject=Terento%20installation%20issue) a uveďte přesný model hodinek, oblast mapy a popis problému.

## Když něco nefunguje

### Terento hodinky nerozpozná

Po připojení počkejte 1–2 minuty. Pokud se hodinky stále nezobrazí, připojte je znovu, ověřte datový kabel a ukončete ostatní aplikace, které je mohou používat. Další pomoc: [Mac nevidí hodinky Garmin](https://terento.app/cs/guides/troubleshooting/#connect-watch), [Hodinky používá Garmin Express nebo jiná aplikace](https://terento.app/cs/guides/troubleshooting/#garmin-busy), [Hodinky Garmin nejsou rozpoznány: režim USB (MTP)](https://terento.app/cs/guides/troubleshooting/#usb-mode).

### Instalace nebo aktualizace není dostupná

Dočasně nedostupné mapy zůstávají viditelné. Přečtěte si důvod uvedený vedle mapy. Pokud je poskytovatel nedostupný nebo je stahování pozastavené, zkuste to později. Pokud Terento nemůže ověřit aktuální dostupnost, zkontrolujte připojení k internetu a zkuste to znovu. Nainstalované mapy zůstávají dostupné. Další pomoc: [Seznam map Garmin se nenačte nebo Terento potřebuje aktualizaci](https://terento.app/cs/guides/troubleshooting/#catalog-unavailable), [Stažení mapy Garmin se nezdařilo](https://terento.app/cs/guides/troubleshooting/#download-failed).

### Instalace se nezdařila

Na obrazovce neúspěšné instalace zvolte „Report issue“. Terento otevře GitHub s již vyplněnou zprávou. Před zveřejněním ji zkontrolujte: hlášení na GitHubu jsou veřejná. Pro pomoc e-mailem uveďte model hodinek, oblast mapy a popis problému. Další pomoc: [Instalace mapy selhala: v hodinkách zůstal zbytek mapy](https://terento.app/cs/guides/troubleshooting/#leftover-map), [Jak nahlásit potíž s Terento](https://terento.app/cs/guides/troubleshooting/#send-report).

[Zobrazit všechna řešení](https://terento.app/cs/guides/troubleshooting/)

## Odinstalace Terento

Ukončete Terento a přesuňte ho ze složky Aplikace do koše. Mapy v hodinkách zůstanou. Terento si údaje o nainstalovaných mapách ukládá do ~/Library/Application Support/Terento: tuto složku si ponechte, pokud budete Terento instalovat znovu, aby tyto mapy mohlo dál aktualizovat a odstraňovat. Chcete-li odstranit vše, smažte i tuto složku, ~/Library/Caches/Terento, ~/Library/Logs/Terento a ~/Library/Preferences/app.terento.mac.plist.
