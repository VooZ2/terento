# Privatumas

Trumpas pranešimas apie viešą svetainę **terento.app**. Tai atskiras puslapis nuo [teisinės informacijos](/legal/).

Tai nėra macOS programos privatumo politika ir ne Freizeitkarte ar OpenStreetMap politika. Žemėlapius atsisiunčiate iš pirminio teikėjo; tie failai nėra Terento asmens duomenų rinkinys.

**Būsena.** Duomenų valdytojo tapatybė ir kontaktas dar nenurodyti. Projektą skelbia Terento talkininkai. Kai bus paskirtas juridinis asmuo — įrašysime čia. El. pašto adreso nėra; jo nesugalvokite.

## Ko čia nėra

Nėra paskyros, prisijungimo ir privalomo el. pašto. Įrenginio būsena ir Terento manifestai pagal projekto taisykles lieka jūsų „Mac“ kompiuteryje ir MVP metu nesiunčiami į Terento serverį kaip debesies laikrodžio profilis.

libmtp ir libusb naudojamos tik native macOS programoje, ne šioje svetainėje. Kūrimo versijos naudoja Homebrew, o produkcinė programa naudoja teisinių pranešimų skyriuje aprašytas prisegtas dinamines bibliotekas.

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

Kol nėra valdytojo kontakto, šių teisių įgyvendinimas per Terento kanalą yra ribotas. Tai pripažįstama atvirai. Šis tekstas tų teisių nesumažina.

Tikslas — pristatyti statinę svetainę, ją apsaugoti ir matyti agreguotą lankomumą. Pilną BDAR 6 str. pagrindo formulę gali nurodyti tik paskirtas valdytojas; ji bus papildyta kartu su tapatybe.

Šis pranešimas yra skaidrumo tekstas, ne teisinė konsultacija.
