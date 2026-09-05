# Soukromí

Oznámení se vztahuje na web Terento a aplikaci macOS. Aplikace nevyžaduje účet. Mapy a záznamy zařízení zůstávají na vašem Macu; omezená diagnostika popsaná níže se sdílí samostatně.

## Kontakt

Správce údajů: soukromá osoba. Přečtěte si [O Terento](/cs/about/) nebo napište na [privacy@terento.app](mailto:privacy@terento.app) ohledně svých údajů.

## Diagnostika aplikace

Dva proudy jsou standardně zapnuté pro zlepšení spolehlivosti a kompatibility. Během instalace není volba sdílení. Každý proud vypnete v **Terento → Diagnostics** bez omezení aplikace. Zastaví se další sdílení a smaže jeho neodeslaná fronta. Odeslané zprávy nelze smazat v aplikaci; žádosti ohledně soukromí zašlete na kontakt výše.

- **Kompatibilita:** model a firmware hodinek, verze aplikace a macOS, poskytovatel/mapy, výsledek instalace a omezené technické údaje o chybách.
- **Použití map:** poskytovatel, mapa/oblast, výsledek stažení či instalace, čas, build a náhodná ID operací/událostí. Vlastní importy `.img` jsou z tohoto proudu vyloučeny.

Zprávy neobsahují Garmin Unit IDs, hodnoty sériových čísel, účty, místní cesty, mapy ani surové protokoly. Jednotlivé zprávy jsou soukromé; zveřejňují se jen ověřené souhrnné výsledky kompatibility. Základem jsou oprávněné zájmy na spolehlivosti a pokrytí zařízení podle čl. 6 odst. 1 písm. f GDPR.

## Připojení webu a aplikace

Požadavky na web, API, katalog a aktualizace mohou poskytovatelům hostingu a zabezpečení zpřístupnit IP adresu a metadata. Mapy se stahují přímo od Freizeitkarte či OpenTopoMap; pro tato připojení platí jejich pravidla soukromí. Kontrola při spuštění načítá informace o vydání, nikoli aplikaci.

Připojení poskytují obsah, požadované funkce a ochranu před zneužitím. Bezpečnostní zpracování se opírá o oprávněné zájmy podle čl. 6 odst. 1 písm. f GDPR.

## Pomoc a veřejná hlášení

Pokud nám napíšete, obdržíme adresu, zprávu a přílohy pro odpověď a prošetření problému. Neposílejte mapy, přihlašovací údaje ani soukromé identifikátory zařízení. Podpora se opírá o oprávněné zájmy na vyřizování požadavků a údržbě aplikace.

GitHub issue je oddělené od automatické diagnostiky: sami jej zkontrolujete a odešlete; obsah a jméno účtu mohou být veřejné. Platí [pravidla GitHubu](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement). Dobrovolné příspěvky probíhají přes [Buy Me a Coffee](https://www.buymeacoffee.com/privacy-policy), které zpracovává platební údaje podle vlastních podmínek.

## Statistiky a úložiště prohlížeče

Umami se načítá všem návštěvníkům pro měření zobrazení, kliknutí a stažení. Nepoužívá sledovací cookies. Může zpracovávat URL stránky a odkazujícího webu, prohlížeč, systém, zařízení a přibližnou polohu. UTM v odkazech popisují zdroje kampaní. Terento je předává v URL bez ukládání kampaní do prohlížeče. Statistiky slouží zlepšování webu a měření kampaní na základě oprávněných zájmů, čl. 6 odst. 1 písm. f GDPR. Na webu není analytický souhlasový banner ani přepínač; pro námitku nás kontaktujte. Statistiky webu jsou oddělené od nastavení diagnostiky aplikace.

Vybraný jazyk se ukládá jako `terento-language` do místního úložiště. Tato vyžádaná preference je oddělena od analytiky. Cloudflare může podle nastavení ochrany používat bezpečnostní cookies.

## Příjemci a uchovávání

Web, API a databáze využívají Hostinger; Cloudflare poskytuje a chrání provoz. Umami běží na `stats.enduristas.lt`. Podrobnosti poskytovatelů: [Cloudflare](https://www.cloudflare.com/privacypolicy/) a [Hostinger](https://www.hostinger.com/legal/privacy-policy). Konfigurace mohou zahrnovat zpracování mimo EHP; kontaktujte nás pro platná opatření.

Pravidlo uchovávání odeslané diagnostiky je 24 měsíců. Přístup má správa projektu. Korespondence podpory se uchovává po dobu potřebnou k vyřízení žádosti, souvisejících sporů nebo právních povinností. Zeptejte se na další lhůty konkrétních služeb nebo zprávu.

## Vaše volby a práva

Můžete žádat přístup, opravu, výmaz či omezení a vznést námitku proti zpracování založenému na oprávněných zájmech. Přenositelnost platí při splnění zákonných podmínek.

Kontaktujte [privacy@terento.app](mailto:privacy@terento.app). Běžně odpovíme do měsíce a případné zákonné prodloužení vysvětlíme. Zprávy nejsou spojeny s účtem ani přímým identifikátorem zařízení; k nalezení vaší zprávy můžeme potřebovat další údaje. Stížnost můžete podat u [litevského úřadu VDAI](https://vdai.lrv.lt/) nebo jiného příslušného dozorového úřadu.

## Technická diagnostická pole

Kompatibilita může zahrnovat očištěný název modelu MTP, USB VID/PID, transport, kategorii zdroje identity (nikdy hodnotu identifikátoru), vydání map, čas, náhodná ID, fázi selhání, povolené chybové kódy, stav zápisu/úklidu a hrubý průběh. Vlastní importy používají obecná označení zdroje. Žádný proud neposílá manifesty, ID objektů MTP, hashe map ani nefiltrované chyby.

Aktualizováno: 5. září 2026.
