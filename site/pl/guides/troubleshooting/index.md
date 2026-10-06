---
title: "Rozwiązywanie problemów z mapami Garmin na Macu — Terento"
canonical: https://terento.app/pl/guides/troubleshooting/
---

Rozwiązywanie problemów

# Rozwiązywanie typowych problemów z Terento

Znajdź problem, który pokazuje Terento, i wykonaj krótkie kroki. Jeśli nic nie pomaga, wyślij raport, abyśmy mogli się temu przyjrzeć.

Połączenie

## Podłączanie zegarka

### Terento czeka na zegarek

Terento wykrywa zegarek automatycznie po podłączeniu. Może to potrwać do 2 minut.

1. Podłącz zegarek bezpośrednio do Maca kablem USB obsługującym przesyłanie danych. Kable tylko do ładowania i niektóre huby nie działają.
2. Odblokuj zegarek.
3. Poczekaj do 2 minut, aż Terento sprawdzi połączenie.
4. Jeśli zegarek nadal się nie pojawia, odłącz go, odczekaj kilka sekund i podłącz ponownie.

### Inna aplikacja używa zegarka

Z połączenia z zegarkiem może korzystać tylko jedna aplikacja naraz.

1. Zamknij Garmin Express i inne aplikacje, które mogą otwierać zegarek, np. aplikacje do przesyłania plików.
2. Jeśli zegarek widać w Finderze, wysuń go tam.
3. Podłącz zegarek ponownie, a następnie wybierz w Terento „Refresh”.

### Podłączono więcej niż jedno urządzenie Garmin

Terento obsługuje jedno urządzenie Garmin naraz.

1. Odłącz wszystkie urządzenia Garmin oprócz zegarka, którego chcesz użyć.
2. Pozostaw ten zegarek podłączony i poczekaj, aż Terento go znajdzie.

### Zegarek nie jest gotowy do przesyłania plików

Niektóre zegarki Garmin mają ustawienie trybu USB, które określa sposób łączenia z komputerem.

1. Na zegarku poszukaj trybu USB, zwykle w Ustawienia › System. Nie każdy model go ma.
2. Jeśli to ustawienie jest dostępne, wybierz MTP.
3. Odłącz zegarek i podłącz go ponownie.

### Zegarek został wykryty, ale nie jest gotowy

Terento wykryło zegarek, ale połączenie nie było gotowe w ciągu 2 minut. Sporadyczne zawieszanie się połączenia to znane ograniczenie obecnej bety.

1. Odłącz zegarek i podłącz go ponownie.
2. Zamknij inne aplikacje, które mogą korzystać z zegarka.
3. Spróbuj innego portu USB lub innego kabla.
4. Jeśli problem się powtarza, uruchom zegarek ponownie i podłącz go jeszcze raz.

### Zegarek przestał odpowiadać

Połączenie zostało przerwane albo zegarek przestał odpowiadać Terento.

1. Odłącz zegarek, odczekaj kilka sekund i podłącz go ponownie.
2. Jeśli Terento instalowało, aktualizowało lub usuwało mapę, po ponownym podłączeniu otwórz „Manage maps” i sprawdź wynik, zanim spróbujesz ponownie.
3. Uruchom zegarek ponownie, jeśli sytuacja się powtarza.

Sprawdzanie

## Sprawdzanie zegarka i map

### Ten model zegarka nie jest włączony do instalacji map

Terento instaluje mapy tylko na zegarkach Garmin z obsługą map, które są włączone w Terento. Nadal możesz podłączyć zegarek i przeglądać mapy.

1. Sprawdź, czy Twój model zegarka obsługuje mapy.
2. Terento sprawdza swoją aktualną listę przy każdym podłączeniu. Jeśli Twój model zostanie włączony później, podłącz zegarek ponownie.
3. Podaj nam dokładny model, abyśmy mogli go sprawdzić. Zobacz [Wyślij raport](https://terento.app/pl/guides/troubleshooting/#send-report).

### Terento nie mogło sprawdzić tego zegarka

Terento potrzebuje połączenia z internetem, aby sprawdzić, czy na tym zegarku można instalować mapy.

1. Sprawdź, czy Mac jest połączony z internetem.
2. Podłącz zegarek ponownie, aby powtórzyć sprawdzenie.
3. Jeśli nadal się nie udaje, odczekaj kilka minut i spróbuj ponownie.

### Nie udało się sprawdzić dostępności map

Terento nie mogło wczytać aktualnej listy map albo ta wersja Terento jest dla niej zbyt stara. Nie dotyczy to map, które już są na zegarku.

1. Sprawdź połączenie z internetem i spróbuj ponownie za kilka minut.
2. Jeśli Terento informuje o nowszej wersji, zainstaluj aktualizację.
3. Dopóki Terento pokazuje starszą zapisaną listę map, instalowanie i aktualizowanie map z katalogu pozostaje niedostępne, aż będzie można sprawdzić aktualną listę.

Pobieranie i miejsce

## Pobieranie i wolne miejsce

### Pobieranie mapy nie powiodło się

Terento pobiera każdą mapę bezpośrednio od jej dostawcy. Dostawcy bywają wolni lub chwilowo niedostępni.

1. Sprawdź połączenie z internetem.
2. Przeczytaj powód podany obok mapy. Jeśli dostawca jest niedostępny lub pobieranie zostało wstrzymane, spróbuj później.
3. Uruchom instalację ponownie.

### Za mało wolnego miejsca na Macu

Terento potrzebuje tymczasowego miejsca na Macu, aby pobrać i przygotować mapę.

1. Zwolnij miejsce na Macu, np. usuwając niepotrzebne pliki.
2. Spróbuj ponownie. Duże regiony wymagają więcej miejsca.

### Za mało wolnego miejsca na zegarku

Terento sprawdza wolne miejsce na zegarku przed instalacją i jej nie rozpoczyna, jeśli mapy się nie zmieszczą.

1. Wybierz mniejszy region lub mniej map.
2. Usuń w „Manage maps” mapę, której już nie potrzebujesz.
3. Aktualizacja wymaga dodatkowego miejsca podczas sprawdzania nowej mapy. Zwolnij miejsce, jeśli aktualizacja nie może się rozpocząć.

Instalacja i aktualizacje

## Instalacja, aktualizacja i usuwanie

### Instalacja nie powiodła się po zapisaniu mapy

Jeśli instalacja zatrzyma się po rozpoczęciu kopiowania, część mapy może pozostać na zegarku. Terento nie usuwa jej automatycznie.

1. Podłącz zegarek ponownie i poczekaj, aż Terento będzie gotowe.
2. Otwórz „Manage maps” i sprawdź listę.
3. Jeśli mapa z nieudanej instalacji jest na liście, usuń ją, a następnie zainstaluj ponownie.
4. Jeśli znowu się nie uda, [wyślij raport](https://terento.app/pl/guides/troubleshooting/#send-report).

### Aktualizacja lub usuwanie trwa długo

Podczas aktualizacji lub usuwania mapy wskaźnik może przez chwilę stać na wysokim procencie przed zakończeniem. W obecnej becie jest to oczekiwane.

1. Pozostaw zegarek podłączony, a Maca wybudzonego, aż Terento poinformuje o zakończeniu.
2. Nie odłączaj zegarka, gdy Terento pracuje.
3. Jeśli Terento zgłosi błąd, podłącz zegarek ponownie i sprawdź „Manage maps”, zanim spróbujesz ponownie.

Nadal masz problem?

## Pomoc

### Wyślij raport

Gdy instalacja, aktualizacja lub usuwanie się nie powiedzie, Terento zapisuje na Macu raport, który pomaga nam zbadać problem.

1. Na ekranie błędu wybierz „Report issue”. Później możesz użyć „Report latest failure” w „Diagnostics”.
2. Terento otworzy GitHuba z wypełnionym raportem. Jeśli formularz jest pusty, kliknij pole raportu, naciśnij ⌘A, a potem ⌘V.
3. Sprawdź raport przed publikacją: zgłoszenia na GitHubie są publiczne.
4. Nie masz konta GitHub? Napisz na [hello@terento.app](mailto:hello@terento.app?subject=Terento%20installation%20issue), podając model zegarka, region mapy i opis tego, co się stało.

Pierwszy raz z Terento?

## Zacznij od instrukcji instalacji w trzech krokach.

[Przeczytaj instrukcję instalacji na Macu](https://terento.app/pl/guides/install-garmin-maps-mac/)
