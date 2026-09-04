# Terento.app — galutinis sujungtas taisymų sąrašas

Šis dokumentas sujungia vartotojo pateiktą sutarimo planą ir 2026-09-04 gyvo
puslapio audito radinius. Tai yra darbų planas su užfiksuotu lokalių pakeitimų
statusu; tai nėra publikavimo ar deploy patvirtinimas.

## Sutarimas

Svetainė atitinka Terento brandą: rami, techniška, patikima ir neperkrauta.
Pagrindinė problema ne vizualinė sistema, o tai, kad svetainė geriau parduoda
produkto kategoriją nei pačią idėją ir vartotojo rezultatą.

Tikslas: lankytojas per kelias sekundes turi suprasti:

1. kokią problemą Terento pašalina;
2. kokį rezultatą gauna su savo Garmin laikrodžiu;
3. kodėl beta yra saugi ir patikima;
4. ar jo konkretus modelis bei Mac yra tinkami;
5. koks yra kitas aiškus veiksmas.

## Sąmoningai nedarome

- Hero CTA tiesiai į DMG — lieka kelias į Download puslapį.
- JSON-LD `UtilitiesApplication` pakeitimo.
- `<title>` perrašymo į brand promise, nes SEO title turi likti informatyvus.
- Naujos vizualinės sistemos, spalvotų kortelių ar „adventure lifestyle“
  krypties.
- AI sugeneruoto kraštovaizdžio.
- Antro CTA spalvos — `Warm Stone` netampa antru primary veiksmu.

## 0. Sprendimo vartai: viena vieša release/provider truth — UŽDARYTA

**Prioritetas: P0 / sprendimas priimtas 2026-09-04.**

Patvirtintas dabartinis variantas: **Terento yra Beta stadijoje ir palaiko du
map provider’ius — `Freizeitkarte` bei `OpenTopoMap`.** Tai reiškia ne bendrą
visų Garmin įrenginių pažadą, o konkrečią dabartinio Beta release capability.

Viešas release truth turi būti formuluojamas taip:

- du provider’iai yra dabartinėje Beta, per tą pačią provider-neutral
  acquisition/lifecycle architektūrą;
- providerio katalogas ir įsigijimas yra atskiri nuo konkretaus Garmin modelio
  suderinamumo;
- viešas suderinamumas lieka modelis po modelio ir remiasi tikra evidence;
- `OpenTopoMap` optional contours ar kitos papildomos variacijos nėra
  automatiškai įtraukiamos į pažadą, jei jų neapima konkretus release;
- ateities provider’iai nėra dabartinio release truth dalis, tačiau gali būti
  įtraukti iki FZK/OTM update vartų uždarymo tik po atskiros source, licencijos,
  metadata, artifact, acquisition ir saugumo peržiūros; nėra fiksuoto maksimalaus
  provider’ių skaičiaus, o maždaug penki yra dabartinis UI orientyras.

P0 įgyvendinimo metu vienu dokumentacijos ir public-copy sync’u sulyginti Home,
Download, Guide, About, legal copy, provider catalog fallback, Compatibility
copy ir produkto screenshot’ai. Viešame tekste vartojama `Beta` formuluotė;
`Pre-MVP` ir `pre-release` release stadijos kalba pašalinta. „MVP“ gali likti
tik vidiniuose scope ir gate dokumentuose, jei jis ten apibrėžia produkto ribas,
o ne release stadiją.

**P0 statusas: PASS — sprendimas ir viešo scope sync įgyvendinti 2026-09-04.**

Uždarymo patikra:

- visos šešios lokalizacijos vienodai įvardija dabartinę Beta ir abu provider’ius;
- Home provider katalogo fallback ir dinaminis katalogas leidžia viešai rodyti dabartinius aktyvius provider’ius — šiuo metu `Freizeitkarte` bei `OpenTopoMap`;
- dabartines viešas suderinamumo eilutes sprendžia `/admin`, o svetainė jas gauna per API; viešai rodomi statusai nuo `TESTED`, `TESTING` lieka vidinis;
- Download, Guide, About ir Compatibility copy nebesiunčia prieštaringo `Pre-MVP` ar bendro Garmin pažado;
- legal/privacy tekstai jau buvo suderinti su abiejų provider’ių naudojimu;
- produkto screenshot’uose abu provider’iai jau matomi, todėl jų keisti nereikėjo;
- generatorių parity, struktūrinių duomenų ir statinio Compatibility scope kontraktai praeina.

## Pass 1 — Compatibility truth ir pasitikėjimas

### 1.1 Loading būsena vietoje netikrų nulių — P1

**Problema:** Compatibility puslapis pirmo renderio metu trumpam rodo `0`
modelių ir `0` sėkmingų instaliacijų, nors po maždaug 1–1,5 s atsiranda realūs
`4` ir `19`.

**Taisyti:**

- visų 6 Compatibility HTML suvestinėje rodyti lokalizuotą loading tekstą,
  ne `0`;
- palikti `aria-busy="true"` ant `#compatibility-summary` ir `#watch-grid`;
- `updateSummary()` bei `render()` nuimti `aria-busy` tik gavus settled
  atsakymą;
- `!publicStatsResponse.ok` ir ne-local režime mesti klaidą, kad veiktų
  esamas `#compatibility-error` kelias;
- quiet refresh klaidos atveju nekeisti jau parodytų skaičių;
- klaida turi būti atskirta nuo teisėto, realaus `0` rezultato.

**Testai:** Compatibility JS `ok / non-ok / quiet fail` keliai, lokalizuotos
loading ir error copy, be console klaidų.

**1.1 statusas: įgyvendinta.** Pradinė būsena dabar rodo lokalizuotą loading
tekstą, sėkmingas atsakymas parodo skaičius, o HTTP / tinklo klaida nebegali
būti pateikta kaip klaidinantis `0`. Fono atnaujinimo klaida išlaiko jau
įkeltus rezultatus.

### 1.2 Crawlable suderinamumo snapshot — P2, sprendimas patvirtintas

Pridėti `site/compatibility/public-models.snapshot.json`, jeigu tai lieka
priimta architektūros kryptis.

- Snapshot naudoja tą patį public API formatą ir tuos pačius
  `TESTING / TESTED / SUPPORTED / VERIFIED` slenksčius.
- Tai nėra antras rankinis modelių sąrašas.
- Pirmas HTML piešinys ir `<noscript>` naudoja snapshot’ą, JS jį pakeičia
  gyvais duomenimis.
- Snapshot atnaujinamas tik realiai pasikeitus evidence duomenims.
- Negalima įrašyti išgalvotų ar nepatvirtintų modelių.

**1.2 statusas: įgyvendinta.** Įtrauktas iš API sugeneruotas
`site/compatibility/public-models.snapshot.json`, iš jo sugeneruojamas pradinis
Compatibility HTML kortelių piešinys ir lokalizuotas `<noscript>` sąrašas.
JavaScript pirmiausia atvaizduoja snapshot’ą, o gavęs API atsakymą jį pakeičia
gyvais duomenimis. Snapshot atnaujinimui naudojamas atskiras validatorius,
kuris nekeičia failo, jei evidence duomenys nepasikeitė.

### 1.3 Scope ir gyvų skaičių taisyklė — P1

Home scope sekcijoje palikti vieną ramų teiginį su nuoroda į Compatibility,
pvz. „Confirmed from real installs — see the list“. Home neturi rodyti senstančių
gyvų modelių ar instaliacijų skaičių; tie skaičiai priklauso Compatibility
puslapiui arba jo snapshot’ui.

**1.3 statusas: įgyvendinta.** Hero jau aiškiai komunikuoja, kad suderinamumas
patvirtinamas modelis po modelio. Home Scope sekcija turi nuorodą į
Compatibility ir nerodo senstančių modelių ar instalacijų skaičių, todėl
papildomas copy dubliavimas nereikalingas.

## Pass 2 — CTA hierarchija, konversija ir accessibility

### 2.1 Header Download tampa aiškiu primary veiksmu — P1

- `site/site-shell.js` `navLink("download")` paversti kompaktišku
  `.download-action` su `Interactive Primary` spalva.
- Tą pačią hierarchiją naudoti mobile meniu.
- `Warm Stone` palikti ne-primary.
- `Tests/run-site-umami-conversion-tests.sh` pakeisti iš draudimo į tikrinimą,
  kad header Download tikrai yra `.download-action`.
- Desktop aktyviam nav link’ui (`[aria-current="page"]`) palikti ramų
  Graphite/weight variantą, ne konkuruojantį CTA.

**2.1 statusas: įgyvendinta.** Desktop ir mobile Header `Download` dabar
naudoja kompaktišką `.download-action`, o aktyvi Download būsena desktop’e
lieka rami. Įėjimas į Download puslapį fiksuojamas kaip
`download-cta-click` su `location: "header-nav"`; tikras DMG/ZIP paspaudimas
lieka atskiru `download-click` event’u.

### 2.2 Hero CTA ir tracking — P1

- `.hero-download-action`: apie 15 px tekstas, apie 52 px aukštis, daugiau
  horizontalaus padding pagal brand button spec.
- Hero kelio rodyklę pakeisti iš `↘` į `→`; failo download link’ai gali likti
  be rodyklės.
- `site/privacy-consent.js` hero selektorių pakeisti iš
  `.hero-copy .text-link` į `.hero-copy a.download-action`.
- Hero event location: `home-hero`; header event location: `header-nav`.
- DMG/ZIP download-click tracking palikti veikiančius.

**2.2 statusas: įgyvendinta.** Hero CTA dabar turi aiškesnį 52 px aukščio
primary veiksmą su didesniu horizontaliu tarpu, o rodyklė `↘` pakeista į `→`
visose šešiose lokalizacijose. `download-cta-click` su `location: "home-hero"`
ir Download puslapio DMG/ZIP tracking išlaikyti.

### 2.3 Hero antrinis kelias į suderinamumą — P1

Po primary CTA pridėti vieną ramų text link į Compatibility. Jis turi padėti
atsakyti „ar mano laikrodis tinka?“ prieš download’ą ir netapti antru spalvotu
CTA.

**2.3 statusas: įgyvendinta.** Po Hero „Download“ CTA pridėta viena rami,
lokalizuota „Compatibility“ nuoroda visose šešiose lokalizacijose. Ji naudoja
shared `text-link` stilių, turi 44 px paspaudimo zoną, nekuria antro spalvoto
CTA ir registruoja `compatibility-link-click` su `location: "home-hero"`.

### 2.4 Download puslapio pasitikėjimo ir veiksmų hierarchija — P1

- DMG lieka primary.
- ZIP tampa secondary action arba text link.
- Release notes lieka tertiary.
- Pašalinti žemos vertės trust eilutę, nes nematerialiai nepagerina Download
  sprendimo ir dubliuoja kitus signalus.
- `Import a compatible map file from your Mac` įrašyti į EN HTML ir visas
  `translations.download.*` lokalizacijas.
- `.img` eilutės turi būti aiškiai aprašytos kaip supported import, ne kaip
  neriboto formato pažadas.

**2.4 statusas: įgyvendinta.** Trijų stulpelių informacinė matrica ir produkto
screenshot’as pašalinti. Viršuje palikti atsisiuntimo veiksmai, o apačioje
Requirements ir Beta status pateikti kaip du aiškūs balti sprendimo blokai.
DMG yra primary, ZIP secondary, release notes — tertiary. „What is included“
blokas pašalintas, nes jo funkcijų inventorius dubliuoja kitus paviršius ir
nepadeda priimti atsisiuntimo sprendimo. Pasitikėjimo eilutė `Free · Notarized ·
Open source` taip pat pašalinta; jos informacija dubliavo kitus signalus.
Release-to-details tarpas sutrumpintas, kortelių antraštės atskirtos nuo
turinio, o Requirements punktų ritmas sugriežtintas. Atskirasis pasikartojantis
Apple Silicon tekstas pašalintas; reikalavimas lieka tik Requirements bloke.
Compatibility nuoroda turi `compatibility-link-click` su
`location: "download-page"`; `.img` aprašytas kaip palaikomas trečiosios šalies
importas.

### 2.5 Footer ir dark mode — P2

- Footer lockup naudoti `logo-white.svg`; header lieka su `logo-sky.svg`.
- „Open-source project“ footer statusą paversti nuoroda į
  `https://github.com/VooZ2/terento`.
- Support / Buy Me a Coffee palikti atskirai.
- Dark mode footeriui pridėti viršutinį border arba atskirą paviršių, nes dabar
  `--footer-bg` sutampa su dark `--off-white`.
- Pridėti antrą `theme-color` meta su
  `media="(prefers-color-scheme: dark)"` ir Graphite spalva.

**2.5 statusas: įgyvendinta.** Footer’is naudoja `logo-white.svg`, o
„Open-source project“ tapo nuoroda į GitHub; „Support Terento“ liko atskiras
veiksmas. Abi nuorodos gauna Umami eventą ir `location: "footer"` per bendrą
privacy-safe instrumentavimo skriptą: atitinkamai `project-link-click` su
`destination: "github"` ir `support-click` su `destination: "buymeacoffee"`.
Dark mode footer’is turi aiškų viršutinį border’į, o visi vieši puslapiai turi
atskirą tamsaus režimo `theme-color`.

### 2.6 Kalbos pasirinkiklis — P2

- Trigger’yje naudoti `EN / DE / FR / PL / CS / IT`, ne emoji vėliavėles.
- Dropdown’e rodyti vėliavėlę ir pilną kalbos vardą.
- Pašalinti arba perrašyti
  `.language-option > span:not(.language-option-flag) { display: none; }`.
- Aktyviai kalbai rodyti aiškią būseną ir išlaikyti `aria-current`.
- Header/footer navigacija lieka vienoje vietoje — `site/site-shell.js` — po
  to `python3 scripts/normalize-public-shell.py`.
- Visos Home/Download/About/Guide copy pataisos eina per visas 6 kalbas.

**2.6 statusas: įgyvendinta.** Trigger’yje rodomas aktyvios kalbos kodas,
dropdown’e — vėliavėlė ir pilnas kalbos vardas. Aktyvus variantas išlaiko
`aria-current="page"`, o mobile dropdown’e kalbos sudėtos į vienodas 44 px
eilučių juostas be dekoratyvinių rodyklių.

### 2.7 Nuorodų kontrastas — P1

**Problema:** `--link-text: #416979` ant `--off-white: #F7F3EC` buvo apie
3,52:1; 14–15 px standartinėms nuorodoms tai tikėtina per mažai.

**Taisyti:** patamsinti `--link-text` iki patikrinto varianto, pvz.
`#315466`, arba naudoti aiškų underline. Pakartoti kontrasto testą light/dark
temose ir visose 6 lokalėse. Rodyklėms bei text link’ams taip pat patikrinti
kontrastą, ne tik primary CTA.

**2.7 statusas: įgyvendinta.** Šviesaus režimo `--link-text` pakeistas į
`#315466`, o tokenai sugeneruoti iš `brand/DESIGN_TOKENS.json`. Bendras
privacy-safe Umami loader’is dabar instrumentuoja visas vidines
Compatibility nuorodas (išskyrus kalbos pasirinkimus), Terento GitHub
projekto ir issues nuorodas, el. paštą bei išorinius Garmin/Apple support
linkus. Kiekvienam priskiriamas eventas, `location` ir, kai naudinga,
`destination`; esami konkretūs CTA location’ai išlaikomi.

## Pass 3 — Hero copy, story ir layout ritmas

### 3.1 Hero H1 paliekamas, lede tampa rezultato pažadu — P1

H1 palikti. Lede turi aiškiai pasakyti rezultatą ir pakeitimą:

> Put the map you need on your Garmin watch — from your Mac, without the old
> manual file-transfer routine.

Lokaliuose variantuose išlaikyti tą pačią prasmę: žemėlapis laikrodyje iš
Mac, be senos programinės įrangos ir rankinio failų medžio. `BaseCamp` lieka
FAQ/gide, kad hero nebūtų perkrautas Garmin terminologija.

**3.1 statusas: įgyvendinta lokaliai.** H1 dabar tiesiai kalba apie žemėlapių
įdiegimą į Garmin laikrodžius: `Install maps on Garmin watches, simply.` Lede
paaiškina visą veiksmų seką ir pašalina rankinį failų perkėlimą: `Install,
update, and manage third-party maps from a native macOS app — without manual
file transfers.` Visose šešiose lokalizacijose pašalintos pasikartojančios Beta
ir Apple Silicon Hero eilutės; vienintelis Beta statusas lieka eyebrow
eilutėje.

### 3.2 Constraint eilutės sutraukiamos — P1

Po CTA palikti vieną ramią, faktišką eilutę, pvz.:

> Free · Notarized · Apple Silicon · compatibility confirmed model by model.

Lokali copy neturi paversti reikalavimų triukšmingu warning bloku. Esamas
`.hero-status` testas `Tests/site-home-copy-cta-tests.cjs` turi tikrinti visas
6 lokalizacijas.

### 3.3 „Connect → Install → Go“ tampa vizualiai uždara istorija — P1

- How it works antraštę rodyti tik vieną kartą; nebedubliuoti jos su fraze apie
  tris paprastus žingsnius.
- Connect, Install ir Done rodyti kaip vieną aiškią seką: desktop’e su
  horizontalia jungiamąja linija, mobile’e be jungiančių linijų; mobile’e
  žodžius atskirti tos pačios sky-blue spalvos bullet’ais.
- Problem statement turi aiškiai pasakyti, kad trečiųjų šalių žemėlapių
  diegimas yra paprastas ir greitas, be papildomos programinės įrangos,
  atskirų atsisiuntimo žingsnių ar techninių žinių.
- Install žingsnyje ir showcase copy pabrėžti du kelius: katalogo žemėlapius
  pagal regioną arba savo suderinamą .img žemėlapį.
- Manage copy turi nurodyti, kad Terento šalina tik savo valdomus trečiųjų
  šalių žemėlapius, o originalūs Garmin žemėlapiai lieka apsaugoti.
- Install maps ir Manage maps sujungti į vieną produkto feature bloką su dviem
  aiškiais tabs mygtukais. Vienu metu rodyti tik pasirinktą panelį, kad turinys
  nebetemptų puslapio ir abu kadrai išlaikytų vieną vizualinę hierarchiją.
- Install maps naudoti esamą aukštos raiškos katalogo/importo produkto kadrą;
  Manage maps — esamą įdiegtų žemėlapių valdymo kadrą. Numeracija paliekama
  tik Connect / Install / Done sekai, ne produkto kadrams.
- ready-to-install ir installing-maps kadrų į Home nedėti: vienas install-maps
  kadras geriausiai parodo katalogą ir .img importą, o diegimo progreso būsena
  yra per techninė pirmam įspūdžiui.
- How it works, tabs ir feature blokų copy lokalizuoti per generatorių ir
  site/localized-content.js; tabs turi veikti su pele, klaviatūra ir išlaikyti
  tinkamą ARIA būseną.

**3.3 statusas: įgyvendinta lokaliai.** How it works rodoma kaip mažas eyebrow,
o pagrindinė antraštė yra `Connect → Install → Done`; desktop’e naudojamos
ankstesnio stiliaus sky-blue rodyklės, o mobile’e — tos pačios spalvos bullet’ai.
Numeruota seka desktop’e turi jungiamąją liniją, workflow antraštė desktop’e
lieka vienoje eilutėje, tačiau mobile’e visos linijos pašalintos, kad žingsniai
būtų lengvi ir nesuskaidyti į techninę schemą.
Install maps ir Manage maps dabar yra viename tabs feature bloke; vienu metu
rodomas tik pasirinktas produkto kadras. Naudojami esami aukštos raiškos
katalogo/importo ir įdiegtų žemėlapių valdymo kadrai. Pašalintas perteklinis
storage review pažadas; Manage copy apsiriboja Terento valdomais trečiųjų
šalių žemėlapiais ir aiškiai apsaugo originalius Garmin žemėlapius. Pakeitimai
sugeneruoti visoms šešioms lokalizacijoms, patikrinti desktop, mobile ir
klaviatūros sąveikoje. Tabs kampai suvienodinti su kompaktišku button stiliumi,
o pakeitimai laikomi lokaliai iki bendro Pass 3 deploy.

### 3.4 Available maps provider cards — P1

- Pašalinti visą `Beta scope` bloką; suderinamumo kelias lieka Hero ir
  navigacijoje.
- `Available today` pakeisti į `Available maps`, o „Choose a map and get
  moving“ pakeisti į `Explore available maps.`.
- Providerius rodyti dviem tikromis kortelėmis, ne dekoratyvinėmis pill’ėmis.
- Kortelėse rodyti katalogo dydį ir 3–5 realius naudojimo privalumus; nerašyti
  licencijų ar techninių atsisiuntimo detalių.
- Skaičius atnaujinti iš viešo katalogo API, išlaikant server-rendered fallback,
  jei API nepasiekiamas.
- Neturi atsirasti providerio, kurio nėra uždarytame 0 skyriuje.

**3.4 statusas: įgyvendinta lokaliai.** Beta scope blokas pašalintas, o
Available maps sekcija dabar turi dvi provider cards. Freizeitkarte aiškiai
pozicionuojama kaip universalesnė hiking/cycling/outdoor mapa, o OpenTopoMap —
kaip topografijai ir reljefo detalumui skirta mapa. Kortelių paketų skaičiai
dinamiškai atnaujinami iš katalogo API ir turi statinį fallback. Pakeitimai
sugeneruoti visoms šešioms lokalizacijoms, patikrinti lokaliais testais ir
laikomi lokaliai iki bendro Pass 3 deploy.

### 3.5 Pasikartojančios brand frazės — P2

„Your device, ready…“ ir artimos formuluotės dabar kartojasi hero, final CTA ir
About vietose. Reikia atskirti jų funkciją:

- Hero: rezultatas ir produkto pažadas.
- Compatibility: įrodymas ir ribos.
- Final CTA: konkretus download veiksmas.
- About: kodėl projektas egzistuoja.

`About` generatoriuje po sąrašo palikti esamą `.final-cta`, bet keturis item
heading’us pakeisti iš `h2` į `h3`. Pakeitimus daryti per
`scripts/build-about-pages.py`.

FR `aventure` formuluotes pakeisti į `destination/readiness` kryptį ten, kur
jos kartojasi: Home H1, step 03, final CTA ir About.

**3.5 statusas: Home dalis įgyvendinta lokaliai, About atidėtas po Pass 3.**
Home FAQ eyebrow dabar yra klausimas naudotojui, Q2 atsakymas aiškiai kalba apie
paprastą ir greitą žemėlapių valdymą bei turi `guide-link-click` eventą su
`home-faq-basecamp` location. Q3 pakeistas į savo suderinamo `.img` žemėlapio
įkėlimą, o Q4 — į vėlesnių žemėlapių atnaujinimą be perteklinio kartojimo.
Final CTA dabar orientuotas į lengvesnį žemėlapių diegimą, o Home, Guide ir
Compatibility download veiksmo mygtukai visose lokalizacijose naudoja stabilų
„Download“ atitikmenį be „Beta“. `About` perrašymas lieka atskiram darbui po
Pass 3.

### 3.6 Desktop whitespace ir ritmas — P2

1440 px capture matyti per didelės tuščios zonos po trijų žingsnių kortelėmis,
po produkto screenshot’ais ir prieš providerio turinį.

Taisyti tik ritmą, ne brand’o kryptį:

- išmatuoti realų viewport’o santykį;
- mažinti perteklinį padding per `.experience.section`, `.steps` ir
  `.product-showcase`;
- palikti vieną sąmoningą hero „breath“;
- nekurti naujų kortelių ar dekoratyvinių užpildų vien tuščiai erdvei uždengti.

**3.6 statusas: uždaryta be papildomų pakeitimų.** Po 3.3–3.5 pakeitimų
pakartotinė desktop 1440 × 900 ir mobile 390 × 844 peržiūra neparodė kritinio
perteklinio vertikalaus tarpo. Workflow, showcase ir provider sekcijos turi
pakankamą atskyrimą, o likusi tuščia erdvė Hero zonoje yra sąmoninga Home
landing page kompozicijos dalis.

### 3.7 Pigūs nits — P3

- Įvertinti `overflow-wrap: anywhere` nuėmimą nuo `h1`, `h2`, `h3`, jei tai
  nebereikalinga lokalizacijoms.
- FAQ palikti vieną aiškią `FAQ` antraštę.

## Pass 4 — tikri visual asset’ai, ne nauja sistema

### 4.1 Kraštovaizdžio asset’as — P2, priklauso nuo failo

Repo neturi tinkamos peizažo nuotraukos. Jei vartotojas pateikia vieną tikrą
nuotrauką su licencija ir alt tekstu:

- naudoti siaurą full-bleed juostą prie final CTA arba šalia hero;
- laikyti ją žema, antrine pakopa;
- neperdažyti į UI spalvas;
- neleisti, kad ji konkuruotų su produkto screenshot’u.

Jei failas nepateiktas, Pass 4 kraštovaizdžio dalis nedaroma. AI kalnai ir
placeholder vaizdai netinka.

### 4.2 App screenshot’ai — P1/P2, scoped screenshot task

- Masteriai imami iš `site/assets/app/masters/`.
- Install / Manage kadruose naudoti regioną, atitinkantį pažadą
  (Alpių / Nordic / Baltijos), ir pašalinti `.img` eilutę iš kadro.
- Po pakeitimo pergeneruoti optimized AVIF/WebP/PNG ir atnaujinti
  cache-busting / `IMAGE_VERSION` generatoriuose.
- Hero `your-garmin` palikti, jei Device state yra aiškiausias first-screen
  įrodymas; keisti į Install tik tada, jei naujas kadras per 5 sekundes aiškiau
  parodo map-ready rezultatą.
- Vokiečių ir kitų lokalizuotų puslapių screenshot’ai neturi atrodyti kaip
  pusiau lokalizuotas angliškas produktas. Rinktis locale-specific kadrus arba
  sąmoningai neutralesnį, mažiau tekstinį app state.

## Lokalizacijos ir generatorių taisyklė

Visos viešos copy pataisos eina per 6 kalbas. Naudojami šaltiniai:

- header/footer: `site/site-shell.js`, tada `normalize-public-shell.py`;
- About: `scripts/build-about-pages.py`;
- Guide: `scripts/build-guide-pages.py`;
- Home/Download: HTML ir `site/localized-content.js`;
- structured data: `scripts/build-guide-pages.py` ir esami validatoriai.

Generated HTML rankiniu būdu netaisomas kaip vienintelis source fix.

## Testavimo ir naršyklės priėmimo vartai

Prieš priimant pakeitimus paleisti:

- `Tests/run-site-tests.sh`;
- layout, copy/CTA, Umami, SEO, FAQ ir generator parity testus;
- Compatibility `ok / loading / error / quiet refresh` testus;
- header CTA, hero rodyklės ir showcase class testus.

Naršyklėje pakartotinai patikrinti:

- Home, Download, About ir Compatibility;
- desktop 1440 × 900;
- mobile 390 × 844;
- Compatibility: loading → realūs skaičiai → API error → quiet refresh;
- mobilią navigaciją, DUK, kalbos meniu ir keyboard focus;
- light/dark spalvų kontrastą ir reduced-motion elgseną;
- visas 6 lokalizacijas.

## Siūloma diskusijos tvarka

0. P0 sprendimas jau uždarytas: **Beta + Freizeitkarte + OpenTopoMap**.
1. Patvirtinti Compatibility loading/error/snapshot elgesį ir public evidence
   ribas.
2. Patvirtinti header, hero ir Download CTA hierarchiją.
3. Patvirtinti hero lede, constraint eilutę ir Connect → Install → Go istoriją.
4. Patvirtinti screenshot’ų turinį, providerio copy, locale kryptį ir whitespace korekcijos
   ribas.
5. Tik tada spręsti apie kraštovaizdžio asset’ą.

Ši seka neleidžia polish’ui užmaskuoti release truth ar konversijos problemų.
