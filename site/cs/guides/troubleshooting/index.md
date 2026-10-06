---
title: "Řešení potíží s mapami Garmin na Macu — Terento"
canonical: https://terento.app/cs/guides/troubleshooting/
---

Řešení potíží

# Řešení běžných potíží s Terento

Najděte potíž, kterou Terento zobrazuje, a postupujte podle krátkých kroků. Pokud nic nepomůže, pošlete zprávu, abychom se na to mohli podívat.

Připojení

## Připojení hodinek

### Terento čeká na hodinky

Terento hodinky po připojení najde automaticky. Může to trvat až 2 minuty.

1. Připojte hodinky přímo k Macu USB kabelem, který podporuje přenos dat. Kabely jen pro nabíjení a některé huby nefungují.
2. Odemkněte hodinky.
3. Počkejte až 2 minuty, než Terento ověří připojení.
4. Pokud se hodinky stále nezobrazí, odpojte je, počkejte několik sekund a připojte je znovu.

### Hodinky používá jiná aplikace

Připojení k hodinkám může v jednu chvíli používat jen jedna aplikace.

1. Ukončete Garmin Express a další aplikace, které mohou hodinky otevřít, například aplikace pro přenos souborů.
2. Pokud se hodinky zobrazují ve Finderu, vysuňte je tam.
3. Hodinky znovu připojte a v Terento zvolte „Refresh“.

### Je připojeno více zařízení Garmin

Terento pracuje vždy jen s jedním zařízením Garmin.

1. Odpojte všechna zařízení Garmin kromě hodinek, které chcete použít.
2. Nechte tyto hodinky připojené a počkejte, až je Terento najde.

### Hodinky nejsou připravené na přenos souborů

Některé hodinky Garmin mají nastavení režimu USB, které určuje, jak se připojují k počítači.

1. V hodinkách vyhledejte režim USB, obvykle v Nastavení › Systém. Ne každý model ho má.
2. Pokud nastavení existuje, zvolte MTP.
3. Hodinky odpojte a znovu připojte.

### Hodinky jsou rozpoznané, ale nejsou připravené

Terento hodinky rozpoznalo, ale připojení nebylo připravené do 2 minut. Občasné zaseknutí připojení je známé omezení aktuální bety.

1. Hodinky odpojte a znovu připojte.
2. Ukončete další aplikace, které mohou hodinky používat.
3. Zkuste jiný USB port nebo jiný kabel.
4. Pokud se to opakuje, restartujte hodinky a znovu je připojte.

### Hodinky přestaly odpovídat

Připojení se přerušilo nebo hodinky přestaly Terento odpovídat.

1. Hodinky odpojte, počkejte několik sekund a znovu je připojte.
2. Pokud Terento právě instalovalo, aktualizovalo nebo odstraňovalo mapu, po připojení otevřete „Manage maps“ a před dalším pokusem zkontrolujte výsledek.
3. Pokud se to opakuje, restartujte hodinky.

Kontroly

## Kontrola hodinek a map

### Tento model hodinek není povolen pro instalaci map

Terento instaluje mapy jen do hodinek Garmin s podporou map, které jsou v Terento povolené. Hodinky přesto můžete připojit a procházet mapy.

1. Ověřte, že váš model hodinek podporuje mapy.
2. Terento při každém připojení kontroluje svůj aktuální seznam. Pokud bude váš model povolen později, připojte hodinky znovu.
3. Napište nám přesný model, abychom ho mohli posoudit. Viz [Odeslat zprávu](https://terento.app/cs/guides/troubleshooting/#send-report).

### Terento nemohlo tyto hodinky zkontrolovat

Terento potřebuje připojení k internetu, aby ověřilo, zda lze do těchto hodinek instalovat mapy.

1. Zkontrolujte, že je Mac připojený k internetu.
2. Připojte hodinky znovu a spusťte tak kontrolu znovu.
3. Pokud to stále selhává, počkejte několik minut a zkuste to znovu.

### Dostupnost map nebylo možné ověřit

Terento nemohlo načíst aktuální seznam map nebo je tato verze Terento pro něj příliš stará. Mapy, které už jsou v hodinkách, to neovlivní.

1. Zkontrolujte připojení k internetu a zkuste to za několik minut znovu.
2. Pokud Terento hlásí novější verzi, nainstalujte aktualizaci.
3. Dokud Terento zobrazuje starší uložený seznam map, instalace a aktualizace map z katalogu zůstávají nedostupné, dokud nelze ověřit aktuální seznam.

Stahování a místo

## Stahování a volné místo

### Stažení mapy se nezdařilo

Terento stahuje každou mapu přímo od jejího poskytovatele. Poskytovatelé bývají někdy pomalí nebo dočasně nedostupní.

1. Zkontrolujte připojení k internetu.
2. Přečtěte si důvod uvedený vedle mapy. Pokud je poskytovatel nedostupný nebo je stahování pozastavené, zkuste to později.
3. Spusťte instalaci znovu.

### Na Macu není dost volného místa

Terento potřebuje na Macu dočasné místo ke stažení a přípravě mapy.

1. Uvolněte místo na Macu, například odstraněním souborů, které už nepotřebujete.
2. Zkuste to znovu. Velké oblasti potřebují více místa.

### V hodinkách není dost volného místa

Terento před instalací kontroluje volné místo v hodinkách a nezačne, pokud se mapy nevejdou.

1. Vyberte menší oblast nebo méně map.
2. V „Manage maps“ odstraňte mapu, kterou už nepotřebujete.
3. Aktualizace potřebuje během kontroly nové mapy místo navíc. Pokud se aktualizace nemůže spustit, uvolněte místo.

Instalace a aktualizace

## Instalace, aktualizace a odstranění

### Instalace selhala po zápisu mapy

Pokud se instalace zastaví po zahájení kopírování, může v hodinkách zůstat část mapy. Terento ji automaticky neodstraní.

1. Připojte hodinky znovu a počkejte, až bude Terento připravené.
2. Otevřete „Manage maps“ a zkontrolujte seznam.
3. Pokud je v seznamu mapa z nezdařené instalace, odstraňte ji a pak ji nainstalujte znovu.
4. Pokud to znovu selže, [pošlete zprávu](https://terento.app/cs/guides/troubleshooting/#send-report).

### Aktualizace nebo odstranění trvá dlouho

Při aktualizaci nebo odstranění mapy může ukazatel chvíli zůstat na vysokém procentu, než se akce dokončí. V aktuální betě je to očekávané.

1. Nechte hodinky připojené a Mac nespící, dokud Terento neoznámí dokončení.
2. Neodpojujte hodinky, zatímco Terento pracuje.
3. Pokud Terento ohlásí chybu, připojte hodinky znovu a před dalším pokusem zkontrolujte „Manage maps“.

Stále nic?

## Získání pomoci

### Odeslat zprávu

Když instalace, aktualizace nebo odstranění selže, Terento uloží na Mac zprávu, která nám pomůže problém prošetřit.

1. Na obrazovce chyby zvolte „Report issue“. Později můžete použít „Report latest failure“ v „Diagnostics“.
2. Terento otevře GitHub s vyplněnou zprávou. Pokud je formulář prázdný, klikněte do pole zprávy, stiskněte ⌘A a potom ⌘V.
3. Před zveřejněním zprávu zkontrolujte: hlášení na GitHubu jsou veřejná.
4. Nemáte účet na GitHubu? Napište na [hello@terento.app](mailto:hello@terento.app?subject=Terento%20installation%20issue) a uveďte model hodinek, oblast mapy a co se stalo.

Poprvé s Terento?

## Začněte průvodcem instalací ve třech krocích.

[Přečíst průvodce instalací na Macu](https://terento.app/cs/guides/install-garmin-maps-mac/)
