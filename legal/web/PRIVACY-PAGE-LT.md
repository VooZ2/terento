# Privatumas

Trumpas pranešimas apie viešą svetainę **terento.app** ir Terento macOS beta
programą. Tai atskiras puslapis nuo [teisinės informacijos](/legal/).

Tai nėra Freizeitkarte, OpenTopoMap ar OpenStreetMap politika. Žemėlapius atsisiunčiate iš
pirminio teikėjo; tie failai nėra Terento asmens duomenų rinkinys.

**Būsena.** Projektą kaip privatus asmuo skelbia Gediminas. Privatumo
klausimams: [privacy@terento.app](mailto:privacy@terento.app). Jei pasikeis
duomenų valdytojas, šis puslapis bus atnaujintas.

## Ko čia nėra

Nėra paskyros, prisijungimo ir privalomo el. pašto. Įrenginio būsena,
žemėlapiai, Terento manifestai ir vietiniai diegimo įrašai lieka jūsų „Mac“
kompiuteryje. Jie nesiunčiami kaip debesies laikrodžio profilis.

libmtp ir libusb naudojamos tik native macOS programoje, ne šioje svetainėje. Kūrimo versijos naudoja Homebrew, o produkcinė programa naudoja teisinių pranešimų skyriuje aprašytas prisegtas dinamines bibliotekas.

## Anoniminė suderinamumo diagnostika programoje

macOS beta pagal nutylėjimą siunčia privatumą tausojančią anoniminę
suderinamumo diagnostiką į `api.terento.app`, kad gerintų diegimo patikimumą
ir suderinamumo aprėptį pagal laikrodžio modelį bei firmware. Diegimo lange
nėra dalijimosi pasirinkimo. Šį srautą galima bet kada išjungti per
**Terento → Diagnostics**; išjungimas neblokuoja diegimo ir nemažina programos
funkcionalumo.

Siunčiami tik privatumą tausojantys suderinamumo duomenys: atsitiktiniai įvykio ir vieno
diegimo paspaudimo operacijos ID, laikas, laikrodžio modelis ar šeima,
išvalyta žalia MTP modelio etiketė, firmware, USB VID/PID, MTP transportas,
kategorija, nurodanti tik ar vietinė tapatybė gauta iš MTP serijos numerio,
Garmin Unit ID, ar buvo neprieinama, teikėjas, pasirinkti regionai,
žemėlapio ir tiksli Terento beta/build versija, kiekvieno žemėlapio rezultatas,
kontroliuojamas nesėkmės etapas ir kodas, ar prasidėjo rašymas bei cleanup, ir
apytikslis perdavimo progreso intervalas. Iki rašymo įvykusios teikėjo ar
validavimo klaidos neblogina laikrodžio suderinamumo statistikos. Ataskaitose
nėra Garmin Unit ID ar serijos numerio reikšmės, vietinio laikrodžio rakto, paskyros,
el. pašto, vietinių kelių, MTP object ID, manifestų, žemėlapių failų ar hash,
nefiltruoto klaidos teksto ar diagnostikos žurnalų.

Šie duomenys naudojami gerinti Terento programos kokybę, diegimo patikimumą ir
palaikomų įrenginių aprėptį. Būsimą dalijimąsi galima sustabdyti per
**Terento → Diagnostics**. Programa neturi įkeltos diagnostikos trynimo
veiksmo; su privatumo teisių klausimais kreipkitės į
[privacy@terento.app](mailto:privacy@terento.app).

## Anoniminė žemėlapių naudojimo diagnostika

Programa pagal nutylėjimą siunčia atskirą privatumą tausojančios anoniminės
žemėlapių naudojimo diagnostikos srautą, kad matuotų žemėlapių atsisiuntimo ir
diegimo rezultatus. Įvykis gali turėti tik atsitiktinius įvykio ir operacijos
ID, laiką, teikėją, žemėlapį, regioną, įvykio tipą, rezultatą ir programos
build. Jame nėra laikrodžio modelio ar identifikatoriaus, serijos numerio ar
Garmin Unit ID reikšmės, paskyros, vietinio kelio, manifesto, žemėlapio failo
ar diagnostikos žurnalo. Šį srautą galima išjungti per **Terento →
Diagnostics**; tai neriboja diegimo. Pasirinktinių `.img` diegimai siunčiami
tik kaip suderinamumo diagnostika, niekada ne kaip žemėlapių naudojimo
diagnostika.

## Diagnostikos saugojimas

Suderinamumo ir žemėlapių naudojimo diagnostika Terento PostgreSQL duomenų
bazėje saugoma ne ilgiau kaip 24 mėnesius, po to pašalinama. Prieiga prie
atskirų įvykių apribota privačiai administravimo paslaugai. Programa neturi
naudotojui skirto įkeltos diagnostikos trynimo veiksmo.

## Kas veikia svetainėje

### Cloudflare

DNS ir HTTPS kraštą teikia Cloudflare. Paprastai tai reiškia turinio pristatymą, TLS ir apsaugą nuo kenksmingo srauto. Terento dokumentacijoje nurodytas tik šis kraštas — ne Workers, ne R2, ne Turnstile.

Kad svetainė veiktų ir būtų saugi, gali būti tvarkomi IP adresai ir užklausų metaduomenys. Taikoma [Cloudflare privatumo politika](https://www.cloudflare.com/privacypolicy/). Duomenys gali būti tvarkomi ir už Lietuvos ar ES ribų — priklausomai nuo Cloudflare sąrankos.

Cloudflare **gali** nustatyti saugumo slapukus (pvz. `__cf_bm`, `cf_clearance`), jei skydelyje įjungiama botų apsauga ar iššūkiai. Tai priklauso nuo Cloudflare nustatymų. Šiuo metu, stebint įprastą atsakymą, tokių slapukų nepastebėta — čia nerašome, kad jie yra, jei jų nėra.

### Umami statistika

Gamybinė svetainė krauna Umami scenarijų iš `stats.enduristas.lt` visiems
lankytojams, kad būtų skaičiuojami apsilankymai ir atsisiuntimo įvykiai. Umami
teigia ir scenarijus patvirtina: **sekimo slapukų nenaudoja**. Nėra paskyros,
el. pašto ir asmeninio profilio per kelis apsilankymus. Lankomumo statistika
tvarkoma pagal Terento teisėtą interesą pagal BDAR 6 straipsnio 1 dalies f punktą:
suprasti svetainės pasiekiamumą ir kampanijų veikimą, gerinti viešą svetainę ir
remti nemokamą atvirojo kodo projektą.

Paprastai fiksuojama: kelias, nuoroda (referrer), naršyklė, operacinė sistema,
įrenginio tipas ir šalies lygio kontekstas. Kampanijos nuorodų atsisiuntimo
įvykiai gali turėti neasmenines UTM reikšmes šaltiniams ir kūrybos variantams
atskirti. Terento neįjungia Umami `identify()`.

Žr. [Umami DUK](https://umami.is/docs/faq).

### Kalbos pasirinkimas

Jei patys pasirenkate svetainės kalbą, naršyklėje gali būti įrašytas `terento-language` (`localStorage`). Tai jūsų prašoma nuostata, kad kitą kartą atsidarytų ta pati kalba — ne reklamos stebėjimas.

## Slapukai — kas taikoma

**Sutikimo juostos nereikia.**

Svetainė nenaudoja reklamos ar profiliavimo slapukų. Statistika (Umami) be
sekimo slapukų ir be asmeninio profiliavimo įjungta visiems lankytojams. Kalbos
`localStorage` — tik tada, kai pasirenkate kalbą. Cloudflare saugumo slapukai,
jei kada nors atsirastų, būtų infrastruktūrai, ne marketingui.

Analitikai nėra sutikimo popup’o ar nustatymo. Jei norite nesutikti su tokiu
tvarkymu, kreipkitės adresu [privacy@terento.app](mailto:privacy@terento.app).

Poraštėje nerašykite absoliutaus „slapukai nenaudojami“, jei Cloudflare sąranka gali pasikeisti. Tikslesnė formulė: lankomumo statistika slapukų nenaudoja; daugiau — šiame puslapyje.

## Jūsų teisės

Pagal BDAR galite turėti teisę susipažinti su duomenimis, juos taisyti, ištrinti, apriboti tvarkymą, nesutikti ir pateikti skundą priežiūros institucijai. Lietuvoje tai Valstybinė duomenų apsaugos inspekcija (VDAI).

Būsimą diagnostikos dalijimąsi galima sustabdyti per **Terento → Diagnostics**.
Programa neturi įkeltos diagnostikos trynimo veiksmo. Šias teises galite
įgyvendinti kreipdamiesi adresu
[privacy@terento.app](mailto:privacy@terento.app). Šis tekstas tų teisių
nesumažina.

Tikslas — pristatyti ir apsaugoti svetainę, matyti agreguotą lankomumą bei
gerinti programos ir suderinamumo kokybę. Lankomumo statistika ir privatumą
tausojanti anoniminė diagnostika tvarkomos pagal teisėtą interesą (BDAR 6 str.
1 d. f p.).

Šis pranešimas yra skaidrumo tekstas, ne teisinė konsultacija.
