---
title: "Darmowe mapy na Garmin Edge z Maca — Terento"
canonical: https://terento.app/pl/guides/install-garmin-maps-edge-mac/
---

# Zainstaluj darmowe mapy na Garmin Edge z Maca

Nowsze liczniki rowerowe Garmin Edge nie pojawiają się na Macu jako dysk, więc nie da się po prostu skopiować na nie pliku mapy. Terento instaluje darmowe mapy OpenStreetMap albo Twój własny zgodny plik mapy na licznikach rowerowych Garmin Edge z obsługą map, takich jak Edge 540, 840 i 1050.

[Pobierz](https://terento.app/pl/download/)

## Czego potrzebujesz

- Mac z Apple Silicon i macOS 13 lub nowszym
- Nowszy Garmin Edge z obsługą map
- Kabel USB obsługujący przesyłanie danych

Po podłączeniu Terento sprawdza Edge i informuje, czy może zainstalować mapy. Strona [Kompatybilność](https://terento.app/pl/compatibility/) pokazuje modele z udanymi instalacjami; brak modelu nie oznacza, że nie jest obsługiwany.

## Zainstaluj mapę na Edge

1. Pobierz i otwórz Terento

[Pobierz Terento](https://terento.app/pl/download/), przeciągnij je z obrazu dysku do folderu Aplikacje i otwórz je stamtąd. Przy pierwszym otwarciu macOS zapyta, czy otworzyć aplikację pobraną z internetu: wybierz Otwórz.

2. Podłącz Edge

Zamknij Garmin Express, jeśli jest otwarty. Podłącz Edge bezpośrednio do Maca kablem USB do przesyłania danych, nie przez hub. Jeśli macOS zapyta, czy zezwolić na połączenie akcesorium, wybierz Zezwól. Terento znajdzie Edge w ciągu 2 minut i sprawdzi, czy może zainstalować mapy.

3. Wybierz mapę

Wybierz dostawcę i region z katalogu albo dodaj z Maca własny zgodny plik mapy .img. [Porównaj style map](https://terento.app/pl/map-styles/), aby zobaczyć, jak każda mapa pokazuje drogi i szlaki.

Terento pokazuje dostawców, regiony map innych firm i dostępne miejsce na Garminie
Wybierz mapę z katalogu albo dodaj własny zgodny plik.

4. Zainstaluj

Rozpocznij instalację i nie odłączaj Edge, dopóki Terento nie poinformuje, że instalacja się zakończyła. Potem odłącz Edge.

Terento pokazuje ukończoną instalację mapy
Nie odłączaj Edge, dopóki Terento nie poinformuje, że mapa jest gotowa.

## Wyświetl mapę na Edge

Odłącz Edge, otwórz jego ustawienia map i sprawdź, czy nowa mapa jest włączona. Jeśli nie ma jej na liście, uruchom Edge ponownie. Jeśli kilka map obejmuje ten sam obszar, wyłącz te, których nie chcesz widzieć.

## Jeśli coś nie działa

### Garmin Edge nie pojawia się w Terento

Użyj kabla USB do przesyłania danych, podłącz Edge bezpośrednio zamiast przez hub, zamknij Garmin Express i aplikacje do przesyłania plików, a potem poczekaj do 2 minut. Więcej pomocy: [Mac nie widzi zegarka Garmin](https://terento.app/pl/guides/troubleshooting/#connect-watch), [Garmin Express lub inna aplikacja używa zegarka](https://terento.app/pl/guides/troubleshooting/#garmin-busy).

### Instalacja lub aktualizacja jest niedostępna

Tymczasowo niedostępne mapy pozostają widoczne. Przeczytaj powód podany obok mapy. Jeśli dostawca jest niedostępny lub pobieranie zostało wstrzymane, spróbuj później. Jeśli Terento nie może sprawdzić bieżącej dostępności, sprawdź połączenie internetowe i spróbuj ponownie. Zainstalowane mapy pozostają dostępne. Więcej pomocy: [Lista map Garmin się nie wczytuje lub Terento wymaga aktualizacji](https://terento.app/pl/guides/troubleshooting/#catalog-unavailable), [Nie udało się pobrać mapy Garmin](https://terento.app/pl/guides/troubleshooting/#download-failed).

### Instalacja nie powiodła się

Na ekranie nieudanej instalacji wybierz „Report issue”. Terento otwiera GitHuba z już wypełnionym raportem. Sprawdź go przed publikacją: zgłoszenia na GitHubie są publiczne. Jeśli potrzebujesz pomocy e-mailem, podaj model Edge, region mapy i opisz, co się stało. Więcej pomocy: [Instalacja mapy nie powiodła się: pozostałość mapy na zegarku](https://terento.app/pl/guides/troubleshooting/#leftover-map), [Jak zgłosić problem z Terento](https://terento.app/pl/guides/troubleshooting/#send-report).

[Zobacz wszystkie rozwiązania](https://terento.app/pl/guides/troubleshooting/)

## Dlaczego Garmin Edge nie pojawia się na Macu

Nowsze modele Edge, takie jak Edge 540, 840 i 1050, przesyłają pliki przez USB tak jak telefony z Androidem. macOS nie obsługuje tego fabrycznie, dlatego Edge nie pojawia się w Finderze jako dysk, a poradniki, które każą skopiować plik mapy do folderu Garmin, nie działają w przypadku tych modeli. Terento komunikuje się z Edge bezpośrednio, więc nie potrzebujesz Android File Transfer ani OpenMTP.

## Starsze modele Edge

Starsze modele, takie jak Edge 1030 Plus i wcześniejsze, zwykle pojawiają się na Macu jako dysk USB. Na nich możesz samodzielnie skopiować zgodny plik mapy .img do folderu Garmin na dysku, bez Terento. Terento nie jest przeznaczone dla tych modeli.
