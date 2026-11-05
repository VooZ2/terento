---
title: "Mapy na zegarek Garmin w Linuksie z Chrome — Terento"
canonical: https://terento.app/pl/guides/install-garmin-maps-linux/
---

# Instalowanie map Garmin w Linuksie

W Linuksie instalator webowy Terento wgrywa darmowe mapy na zegarki Garmin obsługujące mapy, prosto z przeglądarki. Najpierw Linux potrzebuje jednej reguły uprawnień, aby przeglądarka mogła używać zegarka przez USB.

[Otwórz instalator webowy](https://terento.app/pl/install/)

Masz Maca? Przeczytaj poradnik dla [zegarka Garmin](https://terento.app/pl/guides/install-garmin-maps-mac/) lub [Garmin Edge](https://terento.app/pl/guides/install-garmin-maps-edge-mac/).

## Czego potrzebujesz

- Chrome, Microsoft Edge, Opery lub Brave na komputerze z Linuksem. Firefox nie łączy się z urządzeniami USB.
- Kabla USB do transmisji danych, nie tylko do ładowania.
- Odblokowanego zegarka Garmin obsługującego mapy.

## Zainstaluj mapę z przeglądarki

1. Daj przeglądarce dostęp do USB

Otwórz Terminal i wklej to polecenie. Dodaje ono regułę udev dla urządzeń Garmin i raz prosi o hasło administratora. Potem odłącz zegarek i podłącz go ponownie.

```
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="091e", MODE="0660", GROUP="plugdev", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/70-garmin.rules >/dev/null && sudo udevadm control --reload-rules && sudo udevadm trigger
```

2. Otwórz instalator webowy i połącz

[Otwórz instalator webowy](https://terento.app/pl/install/), wybierz „Podłącz zegarek”, a potem pozycję ze słowem „Garmin” w nazwie. Lista może pozostać pusta przez minutę lub dwie, gdy zegarek się przygotowuje.

3. Wybierz mapy i zainstaluj

Wybierz kraj lub region, a potem „Zainstaluj mapy”. Nie zamykaj karty i nie odłączaj zegarka do zakończenia.

## Jeśli to nie działa

### Przeglądarka nie może otworzyć zegarka

Możliwe, że menedżer plików używa zegarka. Wysuń go tam bez odłączania kabla i odśwież stronę. Jeśli reguła została dodana przy podłączonym zegarku, odłącz go i podłącz ponownie.

### Lista w przeglądarce pozostaje pusta

Nie zamykaj listy przez maksymalnie dwie minuty. Jeśli nie pojawi się pozycja ze słowem „Garmin” w nazwie, spróbuj innego kabla USB do danych i sprawdź, czy zegarek jest odblokowany.

### Przeglądarka nie ma dostępu do USB

Przeglądarka zainstalowana jako pakiet Snap może nie mieć dostępu do USB. Użyj przeglądarki z jej oficjalnego pakietu .deb lub .rpm.
