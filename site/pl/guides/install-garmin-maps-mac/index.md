---
title: "Darmowe mapy na zegarek Garmin z Maca — Terento"
canonical: https://terento.app/pl/guides/install-garmin-maps-mac/
---

# Zainstaluj darmowe mapy na zegarku Garmin z Maca

Terento instaluje darmowe mapy OpenStreetMap albo Twój własny plik mapy na zegarku Garmin z obsługą map. Nie kopiujesz żadnych plików samodzielnie, a mapy Garmin pozostają bez zmian.

[Pobierz](https://terento.app/pl/download/)

Używasz Linuksa? [Zainstaluj mapy z przeglądarki](https://terento.app/pl/guides/install-garmin-maps-linux/).

## Czego potrzebujesz

- Mac z Apple Silicon i macOS 13 lub nowszym
- Zegarek Garmin z obsługą map
- Kabel USB obsługujący przesyłanie danych

Po podłączeniu Terento sprawdza zegarek i informuje, czy może zainstalować mapy. Strona [Kompatybilność](https://terento.app/pl/compatibility/) pokazuje modele z udanymi instalacjami; brak modelu nie oznacza, że nie jest obsługiwany.

## Zainstaluj mapę

1. Pobierz i otwórz Terento

[Pobierz Terento](https://terento.app/pl/download/), przeciągnij je z obrazu dysku do folderu Aplikacje i otwórz je stamtąd. Przy pierwszym otwarciu macOS zapyta, czy otworzyć aplikację pobraną z internetu: wybierz Otwórz.

2. Podłącz zegarek

Zamknij Garmin Express, jeśli jest otwarty. Odblokuj zegarek i podłącz go do Maca kablem USB do przesyłania danych, a nie kablem tylko do ładowania. Jeśli macOS zapyta, czy zezwolić na połączenie akcesorium, wybierz Zezwól. Terento znajdzie zegarek w ciągu 1–2 minuty i sprawdzi, czy może zainstalować mapy.

[Mac nie widzi zegarka Garmin](https://terento.app/pl/guides/troubleshooting/#connect-watch)

Terento pokazuje podłączony zegarek Garmin i stan wykrywania
Terento rozpoznaje podłączony zegarek Garmin przed instalacją.

3. Wybierz mapę

Wybierz mapę z katalogu albo dodaj własny zgodny plik .img. [Porównaj style map](https://terento.app/pl/map-styles/), aby zobaczyć, jak każda mapa pokazuje drogi i szlaki.

1. Wybierz z katalogu

Wybierz dostawcę i region z katalogu.

2. Dodaj własną mapę

Dodaj zgodną mapę .img z Maca.

Terento pokazuje dostawców, regiony map innych firm i dostępne miejsce na Garminie
Wybierz mapę z katalogu albo dodaj własny zgodny plik.

4. Zainstaluj

Rozpocznij instalację i nie odłączaj zegarka, dopóki Terento nie poinformuje, że mapa jest gotowa. Potem odłącz zegarek.

Terento pokazuje ukończoną instalację mapy na zegarku Garmin
Pozostaw zegarek podłączony do zakończenia przesyłania i sprawdzania.

## Wyświetl mapę na zegarku

Odłącz zegarek, otwórz jego ustawienia map i włącz nową mapę. Jeśli nie ma jej na liście, uruchom zegarek ponownie. Jeśli kilka map obejmuje ten sam obszar, wyłącz te, których nie chcesz widzieć.

Nadal jej nie widać? Napisz na [hello@terento.app](mailto:hello@terento.app?subject=Terento%20installation%20issue) i podaj dokładny model zegarka, region mapy oraz opis problemu.

## Jeśli coś nie działa

### Terento nie wykrywa zegarka

Odczekaj 1–2 minuty po podłączeniu. Jeśli zegarek nadal się nie pojawia, podłącz go ponownie, sprawdź kabel do transmisji danych i zamknij inne aplikacje, które mogą z niego korzystać. Więcej pomocy: [Mac nie widzi zegarka Garmin](https://terento.app/pl/guides/troubleshooting/#connect-watch), [Garmin Express lub inna aplikacja używa zegarka](https://terento.app/pl/guides/troubleshooting/#garmin-busy), [Mac nie rozpoznaje zegarka Garmin: tryb USB (MTP)](https://terento.app/pl/guides/troubleshooting/#usb-mode).

### Instalacja lub aktualizacja jest niedostępna

Tymczasowo niedostępne mapy pozostają widoczne. Przeczytaj powód podany obok mapy. Jeśli dostawca jest niedostępny lub pobieranie zostało wstrzymane, spróbuj później. Jeśli Terento nie może sprawdzić bieżącej dostępności, sprawdź połączenie internetowe i spróbuj ponownie. Zainstalowane mapy pozostają dostępne. Więcej pomocy: [Lista map Garmin się nie wczytuje lub Terento wymaga aktualizacji](https://terento.app/pl/guides/troubleshooting/#catalog-unavailable), [Nie udało się pobrać mapy Garmin](https://terento.app/pl/guides/troubleshooting/#download-failed).

### Instalacja nie powiodła się

Na ekranie nieudanej instalacji wybierz „Report issue”. Terento otwiera GitHuba z już wypełnionym raportem. Sprawdź go przed publikacją: zgłoszenia na GitHubie są publiczne. Jeśli potrzebujesz pomocy e-mailem, podaj model zegarka, region mapy i opisz, co się stało. Więcej pomocy: [Instalacja mapy nie powiodła się: pozostałość mapy na zegarku](https://terento.app/pl/guides/troubleshooting/#leftover-map), [Jak zgłosić problem z Terento](https://terento.app/pl/guides/troubleshooting/#send-report).

[Zobacz wszystkie rozwiązania](https://terento.app/pl/guides/troubleshooting/)

## Odinstalowanie Terento

Zamknij Terento i przenieś je z folderu Aplikacje do Kosza. Mapy na zegarku zostają. Terento przechowuje informacje o zainstalowanych mapach w ~/Library/Application Support/Terento: zachowaj ten folder, jeśli możesz ponownie zainstalować Terento, aby nadal mogło aktualizować i usuwać te mapy. Aby usunąć wszystko, usuń też ten folder, ~/Library/Caches/Terento, ~/Library/Logs/Terento i ~/Library/Preferences/app.terento.mac.plist.
