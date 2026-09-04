# Terento.app vizualinis ir produkto pristatymo auditas

Audito data: 2026-09-04
Audituotos kalbos / maršrutai: vokiečių versija `/de/`, su pagrindinio turinio
patikra kitose viešose svetainės skiltyse.
Audituota: pagrindinis landing puslapis, mobili navigacija, DUK,
`/de/compatibility/`, `/de/download/`, `/de/guides/install-garmin-maps-mac/` ir
`/de/about/`.

## Audito apimtis

Vertinau, ar svetainė:

- per pirmas sekundes paaiškina, kokį rezultatą gauna žmogus;
- sukuria pakankamai pasitikėjimo beta atsisiuntimui;
- vizualiai atrodo kaip kokybiškos native macOS programos pristatymas;
- išlaiko hierarchiją, ritmą ir skaitomumą desktop bei mobile ekranuose;
- nuosekliai tęsia kelią nuo pažado iki suderinamumo ir atsisiuntimo.

## Užfiksuota įrodymų medžiaga

Naršyklėje užfiksuoti ir audito metu peržiūrėti šie ekranai:

1. Home desktop pirmas ekranas — 1440 × 900 CSS px, šviesi tema.
2. Home desktop vidurinė dalis — „Connect → Install → Ready“ ir produkto
   demonstracija.
3. Home desktop DUK / providerio zona.
4. Home mobile pirmas ekranas — 390 × 844 CSS px.
5. Home mobile atidaryta navigacija.
6. Home mobile funkcijų, suderinamumo, DUK ir footerio būsenos.
7. Compatibility desktop ir mobile pirmi ekranai.
8. Compatibility išskleistas statusų paaiškinimas.
9. Download desktop ir mobile pirmi ekranai.
10. Guide ir About desktop pirmi ekranai.

Pagrindinis puslapis: [terento.app](https://terento.app).
Puslapiai buvo stebėti realiame `Codex In-app Browser`; desktop capture buvo
1440 × 900 CSS px, mobile capture — 390 × 844 CSS px, `deviceScaleFactor` — 1.
Naršyklės console `error` ir `warn` įrašų audito metu nerasta.

Browser connector šioje aplinkoje leidžia ekranus parodyti tiesiogiai audito
žinutėse, tačiau neeksportuoja jų į projekto failus. Todėl ekrano įrodymai yra
inline capture audito sesijoje, o ne atskiri PNG failai.

## Bendra išvada

Vizualiai svetainė yra gera ir jau turi atpažįstamą produkto charakterį —
rami, techniška, patikima, labiau „premium utility“ nei triukšmingas SaaS
landing puslapis. Desktop hero balansas, tipografija, spalvų disciplina ir
tikro produkto UI screenshot’ai veikia.

Vis dėlto tai dar nėra geriausiai įmanoma programos pristatymo svetainė.
Šiuo metu ji labiau pristato „ką daro Terento“, nei parduoda momentą „kodėl
man to reikia ir ką gausiu po kelių minučių“. Didžiausias laimėjimas būtų ne
dar daugiau dekoracijos, o ryškesnis rezultato pažadas, anksčiau parodytas
įrodymas ir griežtesnis turinio / beta scope nuoseklumas.

Apytikslis vertinimas: **7,5 / 10 kaip vizualinis beta landing puslapis**;
**6,5 / 10 kaip atsisiuntimą turinti produkto konversijos svetainė**.

## Stiprybės

- **Brandas atrodo nuosekliai.** Instrument Sans antraštėms ir Inter UI bei
  tekstui sudaro aiškią hierarchiją. Logotipas, off-white fonas, mėlynas CTA
  ir tamsus footeris sukuria savitą, ne Garmin kopijos įspūdį.
- **Hero kompozicija desktop’e stipri.** Kairėje yra aiškus pažadas ir vienas
  pagrindinis CTA, dešinėje — realistiškas produkto vaizdas. Virš lenkimo
  matoma pati programa, todėl puslapis neatrodo kaip vien abstrakti idėja.
- **Mobile reflow tvarkingas.** 390 px pločio ekrane antraštė, tekstas, CTA ir
  produkto vaizdas išlieka suprantami; horizontalus overflow nepastebėtas.
  Mobilus meniu naudoja pakankamai didelius taikinius.
- **Pasitikėjimo sluoksniai egzistuoja.** `Beta`, Apple Silicon reikalavimas,
  modelis po modelio tikrinama suderinamumo politika, suderinamumo puslapis,
  release versija ir gidas sudaro gerą bazę atsargiam atsisiuntimui.
- **Saugumo idėja pateikta gerai.** „Garmin- und Systemkarten bleiben
  geschützt“ yra konkretesnis ir raminantis pažadas nei bendras „safe“.
- **Accessibility bazė nebloga.** Yra skip link, semantiniai heading’ai,
  atidaromi DUK elementai ir aiškiai matomas keyboard focus ring.

## Prioritetiniai radiniai

### [P1] Hero parduoda kategoriją, bet ne pakankamai aiškiai parduoda rezultatą

**Vieta:** Home hero, `/de/` pirmas ekranas.

**Įrodymas:** antraštė „Dein Gerät, bereit für dein nächstes Ziel.“ ir tekstas
„Eine native macOS-App zum Installieren und Verwalten von Drittanbieter-Karten
auf Garmin-Smartwatches.“ gerai apibūdina produktą, tačiau lankytojas dar
negauna vieno konkretaus atsakymo: kuo tai geriau už dabartinį varginantį
procesą ir kas bus padaryta už jį.

**Poveikis:** žmogus supranta, kad tai yra žemėlapių įrankis, bet ne iš karto
supranta, kad Terento pašalina BaseCamp / rankinio failų kopijavimo / formato
spėliojimo naštą. „Beta herunterladen“ prašo veiksmo anksčiau, nei sukuriamas
pakankamas asmeninis motyvas.

**Pataisa:** palikti dabartinę emocinę antraštę kaip brand’o sluoksnį arba ją
perrašyti rezultato kryptimi, o subheadline padaryti konkretesnį, pvz.:

> Put the map you need on your Garmin watch — from your Mac, without the old
> manual file-transfer routine.

Po juo pridėti vieną trumpą antrinę nuorodą „Check your watch first“ / lokalizuotą
atitikmenį į Compatibility. Pirminis CTA turėtų aiškiai sakyti „Download the
free beta“, jei tai atitinka dabartinį release copy.

### [P1] Viešas providerio pažadas turi būti sulygintas su patvirtintu Beta scope

**Vieta:** Home providerio sekcija ir produkto screenshot’ai.

**Įrodymas:** puslapis rodo `Freizeitkarte` ir `OpenTopoMap`; `Install maps` bei
`Manage maps` screenshot’uose taip pat matomas `OpenTopoMap`.

**Poveikis:** tai ne vien vizualinė detalė — tai keičia beta pažadą. Audito
metu ši vieta buvo neaiški, tačiau po audito patvirtinta, kad dabartinė Beta
oficialiai palaiko abu provider’ius. Todėl problema nėra pats
`OpenTopoMap` buvimas, o tai, kad puslapis turi aiškiai komunikuoti Beta
ribas: du provider’iai, bet ne bendras visų Garmin modelių pažadas.

**Pataisa:** vienu release truth sync’u sulyginti Home, Download, Guide, legal
copy, katalogo vaizdus ir app screenshot’us su patvirtinta Beta + dviejų
providerių capability. Viešame tekste naudoti `Beta`, o ne seną
`Pre-MVP-Beta` formuluotę, jei kalbama apie release stadiją.

### [P1] Standartinio teksto nuorodų spalva tikėtina per mažo kontrasto

**Vieta:** `.text-link`, `.scope-link`, guide / download informacinės nuorodos.

**Įrodymas:** užfiksuotas `--link-text: #416979` ant `--off-white: #F7F3EC`;
apskaičiuotas kontrastas apie **3,52:1**. Tai yra žemiau 4,5:1 ribos įprastam
14–15 px tekstui. CTA kontrastas buvo apie 4,78:1 ir atrodo geriau.

**Poveikis:** secondary link’ai yra svarbūs konversijos ir suderinamumo keliui,
bet daliai naudotojų gali būti per blankūs, ypač mažesniuose ekranuose.

**Pataisa:** patamsinti `--link-text` iki patikrinto varianto, pvz.
`#315466`, arba išlaikyti esamą spalvą tik didesniam tekstui ir suteikti
nuorodoms aiškų underline. Po pakeitimo pakartoti kontrasto patikrą visose
lokalėse ir light/dark temose.

### [P2] Desktop ritmas per daug ištemptas ir palieka „tuščią produktą“ įspūdį

**Vieta:** Home tarp „Verbinden → Installieren → Loslegen“, dviejų produkto
showcase sekcijų ir Compatibility/providerio zonos.

**Įrodymas:** 1440 px capture matyti didelės tuščios zonos po trijų žingsnių
kortelėmis ir po produkto screenshot’u, kol pasirodo kitas turinio blokas.
Puslapis atrodo tvarkingas, bet kai kuriuose viewport’uose lankytojas ilgai
nemato naujos informacijos.

**Poveikis:** premium editorial ritmas tampa nebe tyla, o scroll friction. Tai
mažina produkto tempo pojūtį ir silpnina „connect → choose → ready“ istoriją.

**Pataisa:** pirmiausia pamatuoti, kiek kiekvienas blokas turi užimti realaus
viewport’o; tada mažinti tik per didelius tarpus per esamus tokenus ir
selector’ius `.experience.section`, `.steps`, `.product-showcase` bei
`.scope-section`. Geriau palikti vieną sąmoningą hero „breath“, o ne kartoti
tą pačią tuštumą keturis kartus.

### [P2] Pirmas produkto screenshot’as rodo būseną, bet ne pagrindinį „aha“ momentą

**Vieta:** Home hero image.

**Įrodymas:** hero vaizdas rodo „Your Garmin“, prijungtą fēnix 8 ir storage
juostą. Regiono pasirinkimas ir map install procesas parodomi žemiau, mažesniu
masteliu.

**Poveikis:** pirmame ekrane ne iš karto matoma tai, dėl ko žmogus atėjo —
žemėlapis pasirinktas, saugiai įdiegtas ir laikrodis pasiruošęs. Dabartinis
vaizdas labiau parduoda device detection nei map outcome.

**Pataisa:** naudoti aukščiausios raiškos realų produkto asset’ą ir apsvarstyti
hero kompoziciją, kurioje vienu žvilgsniu matomas „device ready“ bei map
selection / successful install rezultatas. Nereikia papildomos iliustracijos;
reikia geriau parinkti tikrą app screen state. Jei screenshot’ai nėra
lokalizuojami, bent jau sumažinti jų priklausomybę nuo anglų kalbos.

### [P2] Produkto UI screenshot’ai ne visada kalba ta pačia kalba kaip puslapis

**Vieta:** vokiečių Home puslapio produkto screenshot’ai.

**Įrodymas:** aplinkinis puslapis yra vokiečių kalba, bet app UI yra „Your
Garmin“, „Install maps“, „Manage maps“, „Refresh“.

**Poveikis:** beta produktas atrodo šiek tiek nebaigtas arba kaip maketas iš
ankstesnio etapo. Tai ypač pastebima, nes screenshot’ai yra pagrindinis
produkto patikimumo įrodymas.

**Pataisa:** pasirinkti vieną iš dviejų aiškių krypčių: (a) app screenshot’ai
visose lokalėse tampa sąmoningai neutraliu, mažiau tekstiniu UI vaizdu; arba
(b) turėti locale-specific screenshot’us bent svarbiausioms lokalėms. Nevertėtų
rodyti vokiečių puslapyje pusiau lokalizuoto angliško produkto kaip galutinio
vaizdo.

### [P2] Compatibility puslapis trumpam rodo nulius vietoje loading būsenos

**Vieta:** `/de/compatibility/` pirmas renderis.

**Įrodymas:** šviežiai atidarius puslapį užfiksuota „0 Modelle mit Nachweis“ ir
„0 erfolgreiche Installationen“, o po maždaug 1–1,5 s atsirado tikrieji
`4 Modelle` ir `19 erfolgreiche Installationen`. Console klaidų nebuvo.

**Poveikis:** žmogus gali palaikyti, kad projektas neturi nė vieno patvirtinto
modelio arba kad puslapis sugedęs. Tai ypač pavojinga, nes Compatibility yra
tiesioginis pasitikėjimo sluoksnis prieš Download.

**Pataisa:** kol API duomenys neįkelti, rodyti skeleton / „Loading compatibility
evidence…“ būseną; neskaičiuoti `0` kaip realaus rezultato. API klaidos atveju
rodyti „Data temporarily unavailable — retry“, o ne tuščią katalogą.

### [P2] Kalbos pasirinkiklis vizualiai remiasi vien vėliavėlėmis

**Vieta:** desktop header kalbos meniu.

**Įrodymas:** atidarytame meniu matomos tik vėliavėlės; DOM turi gerus
`aria-label` įvardijimus (`English`, `Deutsch`, `Français`, `Polski`, `Čeština`,
`Italiano`), tačiau CSS slepia tekstinius pavadinimus per
`.language-option > span:not(.language-option-flag) { display: none; }`.

**Poveikis:** vizualiai kalbos pasirinkimas tampa spėlione, ypač panašių ar
mažai pažįstamų vėliavėlių atveju. Semantinis accessibility sluoksnis padeda,
bet regintis naudotojas gauna mažiau aiškumo nei galėtų.

**Pataisa:** desktop meniu rodyti vėliavėlę ir kalbos pavadinimą, pažymėti
aktyvią kalbą tekstu ir/arba `aria-current`. Jei Lietuvos auditorija yra
reikšminga, įvertinti lietuviškos lokalės pridėjimą atskirai nuo šio vizualinio
fix’o.

### [P2] Žinutė kartojasi per dažnai ir praranda aštrumą

**Vieta:** Home hero, scope sekcija, final CTA ir About.

**Įrodymas:** „Dein Gerät, bereit für dein nächstes Ziel.“ ir labai artimos
formuluotės kartojamos keliuose pagrindiniuose taškuose.

**Poveikis:** brand’o frazė tampa šūkiu-placeholder’iu, o ne progresuojančia
istorija. Lankytojas turėtų gauti skirtingus atsakymus skirtinguose etapuose:
kas tai yra, kodėl saugu, ką daryti dabar.

**Pataisa:**

- Hero: aiškus vartotojo rezultatas.
- Scope / Compatibility: konkretus įrodymas ir ribos.
- Final CTA: konkretus kitas veiksmas su beta / platformos reikalavimu.

## Accessibility ir techninės patikros ribos

### Patvirtinta iš matomo įrodymo

- Matomas keyboard focus ring ant pagrindinio hero CTA.
- Mobile CTA turi pakankamą plotį ir patogų paspaudimo aukštį.
- Heading hierarchija ir landmarks iš esmės aiškūs.
- DUK bei Compatibility statusų paaiškinimas turi atidaromą būseną.
- 390 px capture nerodė horizontalaus overflow.
- Console `error` ir `warn` įrašų nerasta.

### Ko šis auditas nepatvirtina

- pilno WCAG atitikimo;
- viso puslapio keyboard tab order ir focus restoration po meniu uždarymo;
- screen reader elgsenos su visais paslėptais responsive navigation elementais;
- realaus download, Gatekeeper, notarization ar DMG paleidimo kelio;
- network failure, slow API, reduced-motion, dark-mode ir zoom 200 % elgsenos;
- realaus Garmin įrenginio suderinamumo ar map visibility.

## Rekomenduojama darbų eilė

1. Sulyginti viešą providerio / beta scope su vienu canonical release truth.
2. Perrašyti hero subheadline į rezultato pažadą ir pridėti antrinę
   suderinamumo nuorodą.
3. Sutvarkyti Compatibility loading / error būsenas, kad `0` neatrodytų kaip
   tikras rezultatas.
4. Patamsinti standartinių nuorodų spalvą arba suteikti joms underline ir
   pakartoti kontrasto testą.
5. Sumažinti tik perteklinį desktop whitespace; nekeisti visos dabartinės
   editorial krypties.
6. Sulyginti app screenshot’ų kalbą su puslapio locale ir pirmame ekrane
   parodyti map-ready outcome.
7. Po to atlikti atskirą copy/localization polish pass visoms šešioms lokalėms.

## Galutinis vertinimas

Terento.app jau atrodo geriau nei tipinis ankstyvos stadijos projektas: turi tikrą
vizualinę sistemą, realų produkto vaizdą, aiškią struktūrą ir gana patikimą
toną. Ji **parduoda idėją iš dalies** — ypač „native Mac įrankio“ ir saugesnio
proceso idėją — bet dar nepakankamai agresyviai parduoda vartotojo rezultatą.

Jei būtų sutvarkyti pirmi keturi prioritetai, svetainė taptų ne tik graži, bet
ir daug įtikinamesnė: lankytojas greičiau suprastų problemą, pamatytų įrodymą,
žinotų ribas ir drąsiau spaustų Download.
