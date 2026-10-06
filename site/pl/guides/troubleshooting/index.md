---
title: "Mac nie widzi zegarka Garmin? Rozwiązywanie problemów — Terento"
canonical: https://terento.app/pl/guides/troubleshooting/
---

Rozwiązywanie problemów

# Rozwiązywanie problemów z zegarkiem Garmin i mapami na Macu

Znajdź swój problem – od zegarka Garmin, którego Mac nie widzi, po nieudane pobieranie mapy – i wykonaj krótkie kroki. Jeśli nic nie pomaga, wyślij raport, abyśmy mogli się temu przyjrzeć.

Połączenie

## Problemy z połączeniem zegarka Garmin

### Mac nie widzi zegarka Garmin

Podłącz zegarek bezpośrednio do Maca kablem USB do przesyłania danych, odblokuj go i poczekaj do 2 minut: Terento wykryje go automatycznie.

1. Użyj kabla do przesyłania danych. Kable tylko do ładowania i niektóre huby USB nie działają.
2. Poczekaj do 2 minut, aż Terento sprawdzi połączenie.
3. Jeśli zegarek nadal się nie pojawia, odłącz go, odczekaj kilka sekund i podłącz ponownie.
4. Jeśli otwarta jest inna aplikacja, zobacz [Garmin Express lub inna aplikacja używa zegarka](https://terento.app/pl/guides/troubleshooting/#garmin-busy).

### Garmin Express lub inna aplikacja używa zegarka

Zamknij Garmin Express i aplikacje do przesyłania plików, takie jak Android File Transfer, OpenMTP czy MacDroid: z połączenia z zegarkiem może korzystać tylko jedna aplikacja naraz.

1. Zamknij Garmin Express, Android File Transfer, OpenMTP, MacDroid i inne aplikacje MTP. Jeśli Terento wskaże aplikację, zamknij najpierw ją.
2. Zamknij też Pobieranie obrazów, Zdjęcia i Podgląd, jeśli są otwarte.
3. Jeśli zegarek widać w Finderze, wysuń go tam.
4. Odłącz zegarek, podłącz go ponownie, a następnie wybierz w Terento „Refresh”.

### Podłączono kilka urządzeń Garmin

Odłącz wszystkie urządzenia Garmin oprócz zegarka, którego chcesz użyć: Terento obsługuje jedno urządzenie Garmin naraz.

1. Odłącz inne zegarki, liczniki rowerowe i urządzenia ręczne Garmin.
2. Pozostaw wybrany zegarek podłączony i poczekaj, aż Terento go znajdzie.

### Mac nie rozpoznaje zegarka Garmin: tryb USB (MTP)

Jeśli Terento informuje, że zegarek nie jest gotowy do przesyłania plików, ustaw w zegarku tryb USB na MTP, o ile Twój model ma to ustawienie.

1. Na zegarku otwórz tryb USB, zwykle w Ustawienia › System. Nie każdy model go ma.
2. Wybierz MTP.
3. Odłącz zegarek i podłącz go ponownie.

### Zegarek Garmin wykryty, ale niegotowy

Jeśli Terento znajdzie zegarek, ale połączenie nie będzie gotowe w ciągu 2 minut, odłącz zegarek i podłącz go ponownie. Sporadyczne zawieszanie się połączenia to znane ograniczenie obecnej bety.

1. Zamknij inne aplikacje, które mogą korzystać z zegarka. Zobacz [Garmin Express lub inna aplikacja używa zegarka](https://terento.app/pl/guides/troubleshooting/#garmin-busy).
2. Spróbuj innego portu USB lub innego kabla.
3. Jeśli problem się powtarza, uruchom zegarek ponownie i podłącz go jeszcze raz.

### Zegarek Garmin przestał odpowiadać

Odłącz zegarek, odczekaj kilka sekund i podłącz go ponownie: połączenie zostało przerwane albo zegarek przestał odpowiadać Terento.

1. Jeśli Terento instalowało, aktualizowało lub usuwało mapę, po ponownym podłączeniu otwórz „Manage maps” i sprawdź wynik, zanim spróbujesz ponownie.
2. Uruchom zegarek ponownie, jeśli sytuacja się powtarza.

Sprawdzanie

## Sprawdzanie zegarka i map

### Instalacja map niedostępna dla tego modelu Garmin

Terento instaluje mapy tylko na zegarkach Garmin z obsługą map, które są włączone w Terento. Nadal możesz podłączyć zegarek i przeglądać mapy.

1. Sprawdź, czy Twój model zegarka obsługuje mapy.
2. Terento sprawdza swoją aktualną listę przy każdym podłączeniu. Jeśli Twój model zostanie włączony później, podłącz zegarek ponownie.
3. Podaj nam dokładny model, abyśmy mogli go sprawdzić. Zobacz [Jak zgłosić problem z Terento](https://terento.app/pl/guides/troubleshooting/#send-report).

### Terento nie mogło sprawdzić zegarka Garmin

Sprawdź, czy Mac ma połączenie z internetem, i podłącz zegarek ponownie: Terento potrzebuje internetu, aby sprawdzić, czy na tym zegarku można instalować mapy.

1. Otwórz dowolną stronę, aby upewnić się, że Mac jest online.
2. Odłącz zegarek i podłącz go ponownie, aby powtórzyć sprawdzenie.
3. Jeśli nadal się nie udaje, odczekaj kilka minut i spróbuj ponownie.

### Lista map Garmin się nie wczytuje lub Terento wymaga aktualizacji

Jeśli Terento nie może wczytać aktualnej listy map, sprawdź połączenie z internetem i spróbuj ponownie za kilka minut. Nie dotyczy to map, które już są na zegarku.

1. Jeśli ta wersja Terento jest zbyt stara dla aktualnej listy map, a Terento informuje o nowszej wersji, zainstaluj aktualizację.
2. Dopóki Terento pokazuje starszą zapisaną listę map, instalowanie i aktualizowanie map z katalogu pozostaje niedostępne, aż będzie można sprawdzić aktualną listę.

Pobieranie i miejsce

## Pobieranie map i wolne miejsce

### Nie udało się pobrać mapy Garmin

Sprawdź połączenie z internetem i spróbuj później: Terento pobiera każdą mapę bezpośrednio od jej dostawcy, a dostawcy bywają wolni lub chwilowo niedostępni.

1. Przeczytaj powód podany obok mapy. Jeśli dostawca jest niedostępny lub pobieranie zostało wstrzymane, spróbuj później.
2. Uruchom instalację ponownie.

### Za mało miejsca na Macu, aby pobrać mapę

Zwolnij miejsce na Macu i spróbuj ponownie: Terento potrzebuje tymczasowego miejsca, aby pobrać i przygotować mapę.

1. Usuń niepotrzebne pliki i opróżnij Kosz.
2. Spróbuj ponownie. Duże regiony wymagają więcej miejsca.

### Za mało miejsca na mapy Garmin w zegarku

Wybierz mniejszy region albo usuń mapę, której już nie potrzebujesz: Terento sprawdza wolne miejsce na zegarku przed instalacją i jej nie rozpoczyna, jeśli mapy się nie zmieszczą.

1. Wybierz mniejszy region lub mniej map.
2. Otwórz „Manage maps” i usuń mapę, której już nie potrzebujesz.
3. Aktualizacja wymaga dodatkowego miejsca podczas sprawdzania nowej mapy. Zwolnij miejsce, jeśli aktualizacja nie może się rozpocząć.

Instalacja i aktualizacje

## Instalowanie, aktualizowanie i usuwanie map

### Instalacja mapy nie powiodła się: pozostałość mapy na zegarku

Usuń pozostałą mapę w „Manage maps”, a potem zainstaluj ją ponownie. Jeśli instalacja zatrzyma się po rozpoczęciu kopiowania, część mapy może pozostać na zegarku, a Terento nie usuwa jej automatycznie.

1. Podłącz zegarek ponownie i poczekaj, aż Terento będzie gotowe.
2. Otwórz „Manage maps” i sprawdź listę.
3. Jeśli mapa z nieudanej instalacji jest na liście, usuń ją, a następnie zainstaluj ponownie.
4. Jeśli znowu się nie uda, [wyślij raport](https://terento.app/pl/guides/troubleshooting/#send-report).

### Aktualizacja lub usuwanie mapy trwa długo

W obecnej becie jest to oczekiwane: podczas aktualizacji lub usuwania mapy wskaźnik może przez chwilę stać na wysokim procencie przed zakończeniem. Pozostaw zegarek podłączony, a Maca wybudzonego.

1. Nie odłączaj zegarka, gdy Terento pracuje.
2. Poczekaj, aż Terento poinformuje o zakończeniu.
3. Jeśli Terento zgłosi błąd, podłącz zegarek ponownie i sprawdź „Manage maps”, zanim spróbujesz ponownie.

Nadal masz problem?

## Pomoc

### Jak zgłosić problem z Terento

Na ekranie błędu wybierz „Report issue”: Terento otworzy GitHuba z już wypełnionym raportem zapisanym na Macu.

1. Później możesz użyć „Report latest failure” w „Diagnostics”.
2. Jeśli formularz na GitHubie jest pusty, kliknij pole raportu, naciśnij ⌘A, a potem ⌘V.
3. Sprawdź raport przed publikacją: zgłoszenia na GitHubie są publiczne.
4. Nie masz konta GitHub? Napisz na [hello@terento.app](mailto:hello@terento.app?subject=Terento%20installation%20issue), podając model zegarka, region mapy i opis tego, co się stało.

Pierwszy raz z Terento?

## Zacznij od instrukcji instalacji w trzech krokach.

[Przeczytaj instrukcję instalacji na Macu](https://terento.app/pl/guides/install-garmin-maps-mac/)
