---
title: "Instalace map Garmin v Linuxu z Chrome — Terento"
canonical: https://terento.app/cs/guides/install-garmin-maps-linux/
---

Průvodce pro Linux

# Instalace map Garmin v Linuxu

V Linuxu webový instalátor Terento nahraje bezplatné mapy do hodinek Garmin s podporou map přímo z prohlížeče. Linux nejdřív potřebuje jedno pravidlo oprávnění, aby prohlížeč mohl hodinky používat přes USB.

## Co potřebujete

- Chrome, Microsoft Edge, Operu nebo Brave na počítači s Linuxem. Firefox se nemůže připojit k zařízením USB.
- Datový kabel USB, ne kabel jen pro nabíjení.
- Odemčené hodinky Garmin s podporou map.

Tři kroky

## Instalace mapy z prohlížeče

1. Dejte prohlížeči přístup k USB

Otevřete Terminál a vložte tento příkaz. Přidá pravidlo udev pro zařízení Garmin a jednou se zeptá na heslo správce. Pak hodinky odpojte a znovu připojte.

```
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="091e", MODE="0660", GROUP="plugdev", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/70-garmin.rules >/dev/null && sudo udevadm control --reload-rules && sudo udevadm trigger
```

2. Otevřete webový instalátor a připojte

Otevřete webový instalátor, zvolte „Připojte hodinky“ a pak položku se slovem „Garmin“ v názvu. Seznam může minutu nebo dvě zůstat prázdný, než se hodinky připraví.

3. Vyberte mapy a nainstalujte

Vyberte zemi nebo oblast a zvolte „Instalovat mapy“. Nechte kartu otevřenou a hodinky připojené, dokud nebude vše hotovo.

Řešení potíží

## Když to nefunguje

### Prohlížeč nemůže hodinky otevřít

Hodinky možná používá správce souborů. Vysuňte je tam bez odpojení kabelu a znovu načtěte stránku. Pokud jste pravidlo přidali s připojenými hodinkami, odpojte je a znovu připojte.

### Seznam v prohlížeči zůstává prázdný

Nechte seznam otevřený až dvě minuty. Pokud se neobjeví položka se slovem „Garmin“ v názvu, zkuste jiný datový kabel USB a zkontrolujte, že jsou hodinky odemčené.

### Prohlížeč nemá přístup k USB

Prohlížeč nainstalovaný jako balíček Snap nemusí dostat přístup k USB. Použijte prohlížeč z jeho oficiálního balíčku .deb nebo .rpm.

Připraveno?

## Otevřete webový instalátor a připojte hodinky.

[Otevřít webový instalátor](https://terento.app/cs/install/)
