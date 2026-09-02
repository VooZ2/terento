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

## Suderinamumo ataskaitos programoje

Naujo diegimo metu macOS beta prieš diegimą rodo suderinamumo duomenų
dalijimosi pasirinkimą. Naujam diegimui jis pažymėtas pagal nutylėjimą, tačiau
jį galima atžymėti prieš diegiant. Atžymėjimas neblokuoja diegimo ir nemažina
programos funkcionalumo.

Jei pasirinkimas paliekamas įjungtas ir diegimas tęsiamas, siunčiami tik
privatumą tausojantys suderinamumo duomenys: atsitiktiniai įvykio ir vieno
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

Dalijimąsi galima sustabdyti, o įkeltas ataskaitas ištrinti programoje per
**About Terento → Privacy**.

## Kas veikia svetainėje

### Cloudflare

DNS ir HTTPS kraštą teikia Cloudflare. Paprastai tai reiškia turinio pristatymą, TLS ir apsaugą nuo kenksmingo srauto. Terento dokumentacijoje nurodytas tik šis kraštas — ne Workers, ne R2, ne Turnstile.

Kad svetainė veiktų ir būtų saugi, gali būti tvarkomi IP adresai ir užklausų metaduomenys. Taikoma [Cloudflare privatumo politika](https://www.cloudflare.com/privacypolicy/). Duomenys gali būti tvarkomi ir už Lietuvos ar ES ribų — priklausomai nuo Cloudflare sąrankos.

Cloudflare **gali** nustatyti saugumo slapukus (pvz. `__cf_bm`, `cf_clearance`), jei skydelyje įjungiama botų apsauga ar iššūkiai. Tai priklauso nuo Cloudflare nustatymų. Šiuo metu, stebint įprastą atsakymą, tokių slapukų nepastebėta — čia nerašome, kad jie yra, jei jų nėra.

### Umami statistika

Gamybinė svetainė krauna Umami scenarijų iš `stats.enduristas.lt`, kad būtų skaičiuojami apsilankymai. Umami teigia ir scenarijus patvirtina: **sekimo slapukų nenaudoja**. Nėra paskyros, el. pašto ir asmeninio profilio per kelis apsilankymus.

Paprastai fiksuojama: kelias, nuoroda (referrer), naršyklės ir įrenginio tipas, šalies lygio kontekstas. Terento neįjungia Umami `identify()`. Scenarijus gali perskaityti `localStorage` raktą `umami.disabled`, jei jį nustatėte patys kaip atsisakymą.

Žr. [Umami DUK](https://umami.is/docs/faq).

### Kalbos pasirinkimas

Jei patys pasirenkate svetainės kalbą, naršyklėje gali būti įrašytas `terento-language` (`localStorage`). Tai jūsų prašoma nuostata, kad kitą kartą atsidarytų ta pati kalba — ne reklamos stebėjimas.

## Slapukai — kas taikoma

**Sutikimo juostos nereikia.**

Svetainė nenaudoja reklamos ar profiliavimo slapukų. Statistika (Umami) be slapukų ir be asmeninio profiliavimo. Kalbos `localStorage` — tik tada, kai pasirenkate kalbą. Cloudflare saugumo slapukai, jei kada nors atsirastų, būtų infrastruktūrai, ne marketingui.

Jei tai pasikeistų (pvz. būtų įjungti neesminiai slapukai ar profiliuojanti analitika), šį puslapį reikėtų atnaujinti ir tada — tik tada — prašyti sutikimo.

Poraštėje nerašykite absoliutaus „slapukai nenaudojami“, jei Cloudflare sąranka gali pasikeisti. Tikslesnė formulė: lankomumo statistika slapukų nenaudoja; daugiau — šiame puslapyje.

## Jūsų teisės

Pagal BDAR galite turėti teisę susipažinti su duomenimis, juos taisyti, ištrinti, apriboti tvarkymą, nesutikti ir pateikti skundą priežiūros institucijai. Lietuvoje tai Valstybinė duomenų apsaugos inspekcija (VDAI).

Šias teises galite įgyvendinti kreipdamiesi adresu
[privacy@terento.app](mailto:privacy@terento.app). Šis tekstas tų teisių
nesumažina.

Tikslas — pristatyti ir apsaugoti svetainę, matyti agreguotą lankomumą bei
gerinti programos suderinamumą. Lankomumo statistika tvarkoma su jūsų sutikimu
(BDAR 6 str. 1 d. a p.), o suderinamumo ataskaitos siunčiamos tik tęsiant
diegimą su matomu, pagal nutylėjimą pažymėtu pasirinkimu; jų tvarkymas grindžiamas
BDAR 6 str. 1 d. a p. sutikimu.

Šis pranešimas yra skaidrumo tekstas, ne teisinė konsultacija.
