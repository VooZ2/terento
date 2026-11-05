---
title: "Cartes pour montre Garmin sous Linux avec Chrome — Terento"
canonical: https://terento.app/fr/guides/install-garmin-maps-linux/
---

# Installer des cartes Garmin sous Linux

Sous Linux, l’installateur web Terento installe des cartes gratuites sur les montres Garmin compatibles avec les cartes, directement depuis votre navigateur. Linux a d’abord besoin d’une règle d’autorisation pour que le navigateur puisse utiliser la montre en USB.

[Ouvrir l’installateur web](https://terento.app/fr/install/)

Sur Mac ? Lisez le guide pour une [montre Garmin](https://terento.app/fr/guides/install-garmin-maps-mac/) ou un [Garmin Edge](https://terento.app/fr/guides/install-garmin-maps-edge-mac/).

## Ce qu’il vous faut

- Chrome, Microsoft Edge, Opera ou Brave sur un ordinateur Linux. Firefox ne peut pas se connecter aux appareils USB.
- Un câble USB de données, pas un câble de charge seule.
- Une montre Garmin compatible avec les cartes, déverrouillée.

## Installer une carte depuis le navigateur

1. Donner l’accès USB au navigateur

Ouvrez le Terminal et collez cette commande. Elle ajoute une règle udev pour les appareils Garmin et demande une fois votre mot de passe administrateur. Débranchez ensuite la montre, puis rebranchez-la.

```
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="091e", MODE="0660", GROUP="plugdev", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/70-garmin.rules >/dev/null && sudo udevadm control --reload-rules && sudo udevadm trigger
```

2. Ouvrir l’installateur web et connecter

[Ouvrez l’installateur web](https://terento.app/fr/install/), choisissez « Connectez votre montre », puis l’entrée contenant « Garmin » dans son nom. La liste peut rester vide une ou deux minutes pendant que la montre se prépare.

3. Choisir les cartes et installer

Choisissez un pays ou une région, puis « Installer des cartes ». Gardez l’onglet ouvert et la montre connectée jusqu’à la fin.

## Si cela ne fonctionne pas

### Le navigateur ne peut pas ouvrir la montre

Votre gestionnaire de fichiers utilise peut-être la montre. Éjectez-la depuis celui-ci sans la débrancher, puis rechargez la page. Si vous avez ajouté la règle avec la montre branchée, débranchez-la puis rebranchez-la.

### La liste du navigateur reste vide

Laissez la liste ouverte jusqu’à deux minutes. Si aucune entrée contenant « Garmin » n’apparaît, essayez un autre câble USB de données et vérifiez que la montre est déverrouillée.

### Le navigateur n’a pas d’accès USB

Un navigateur installé en paquet Snap peut ne pas obtenir l’accès USB. Utilisez le navigateur issu de son paquet officiel .deb ou .rpm.
