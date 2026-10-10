# Soukromí

Oznámení se vztahuje na web Terento, aplikaci macOS a webový instalátor. Nevyžadují účet. Mapy a záznamy zařízení zůstávají na vašem Macu nebo v prohlížeči; omezená diagnostika a statistiky popsané níže se sdílejí samostatně.

## Kontakt

Správce údajů: soukromá osoba. Přečtěte si [O Terento](/cs/about/) nebo napište na [privacy@terento.app](mailto:privacy@terento.app) ohledně svých údajů.

## Diagnostika aplikace

Dva proudy jsou standardně zapnuté pro zlepšení spolehlivosti a kompatibility. Během instalace není volba sdílení. Každý proud vypnete v **Terento → Diagnostics** bez omezení aplikace. Zastaví se další sdílení a smaže jeho neodeslaná fronta. Odeslané zprávy nelze smazat v aplikaci; žádosti ohledně soukromí zašlete na kontakt výše.

- **Kompatibilita:** model a firmware hodinek, verze aplikace a macOS, poskytovatel/mapy, výsledek instalace a omezené technické údaje o chybách.
- **Použití map:** poskytovatel, mapa/oblast, výsledek stažení či instalace, čas, build a náhodná ID operací/událostí. Vlastní importy `.img` jsou z tohoto proudu vyloučeny.

Zprávy neobsahují Garmin Unit IDs, hodnoty sériových čísel, účty, místní cesty, mapy ani surové protokoly. Jednotlivé zprávy jsou soukromé; zveřejňují se jen ověřené souhrnné výsledky kompatibility. Základem jsou oprávněné zájmy na spolehlivosti a pokrytí zařízení podle čl. 6 odst. 1 písm. f GDPR.

## Webový instalátor

Webový instalátor umožňuje instalovat mapy do hodinek z Google Chrome, bez aplikace. Chrome na vašem počítači přečte z hodinek, co potřebuje, například model, volné místo a mapy.

Když zvolíte mapu, server Terento ji stáhne od původního poskytovatele a předá ji vašemu prohlížeči. Kopie vzniká jen pro váš požadavek, nesdílí se a smaže se, jakmile ji prohlížeč má, nebo po dvou hodinách, pokud si ji nevyzvedne. Poskytovatel vidí server Terento, ne vás.

Stránka posílá Terento krátké anonymní zprávy o každém kroku: zda lze tento prohlížeč použít, zda se hodinky připojily a jak skončila každá instalace, aktualizace nebo odebrání mapy. Obsahují:

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
