---
title: "Cartes gratuites sur montre Garmin depuis un Mac — Terento"
canonical: https://terento.app/fr/guides/install-garmin-maps-mac/
---

# Installer des cartes gratuites sur votre montre Garmin depuis un Mac

Terento installe des cartes OpenStreetMap gratuites, ou votre propre fichier de carte, sur une montre Garmin compatible avec les cartes. Vous ne copiez aucun fichier vous-même, et vos cartes Garmin restent intactes.

[Télécharger](https://terento.app/fr/download/)

Sous Linux ? [Installez des cartes depuis le navigateur](https://terento.app/fr/guides/install-garmin-maps-linux/).

## Ce qu’il vous faut

- Mac Apple Silicon avec macOS 13 ou version ultérieure
- Montre Garmin prenant en charge les cartes
- Câble USB permettant le transfert de données

Après la connexion, Terento vérifie la montre et vous indique s’il peut installer des cartes. La page [Compatibilité](https://terento.app/fr/compatibility/) liste les modèles avec des installations réussies ; un modèle absent n’est pas forcément incompatible.

## Installer une carte

1. Télécharger et ouvrir Terento

[Téléchargez Terento](https://terento.app/fr/download/), faites-le glisser de l’image disque vers Applications, puis ouvrez-le depuis ce dossier. À la première ouverture, macOS demande si vous voulez ouvrir une app téléchargée depuis Internet : choisissez Ouvrir.

2. Connecter la montre

Quittez Garmin Express s’il est ouvert. Déverrouillez la montre et connectez-la au Mac avec un câble USB de données, pas un câble de charge seule. Si macOS demande d’autoriser la connexion de l’accessoire, choisissez Autoriser. Terento trouve la montre en 1 à 2 minutes et vérifie s’il peut installer des cartes.

[Montre Garmin non détectée sur Mac](https://terento.app/fr/guides/troubleshooting/#connect-watch)

Terento affiche une montre Garmin connectée et son état de détection
Terento reconnaît la montre Garmin connectée avant l’installation.

3. Choisir une carte

Choisissez une carte dans le catalogue ou ajoutez votre propre fichier .img compatible. [Comparez les styles de carte](https://terento.app/fr/map-styles/) pour voir comment chaque carte affiche routes et sentiers.

1. Choisir dans le catalogue

Choisissez un fournisseur et une région dans le catalogue.

2. Ajouter votre carte

Ajoutez une carte .img compatible depuis votre Mac.

Terento affiche les fournisseurs, les régions de cartes tierces et l’espace Garmin disponible
Choisissez une carte dans le catalogue ou ajoutez votre propre fichier compatible.

4. Installer

Lancez l’installation et gardez la montre connectée jusqu’à ce que Terento indique que la carte est prête. Déconnectez ensuite la montre.

Terento affiche une installation de carte terminée sur une montre Garmin
Gardez la montre connectée jusqu’à la fin du transfert et de la vérification.

## Afficher la carte sur votre montre

Déconnectez la montre, ouvrez ses réglages de carte et activez la nouvelle carte. Si elle n’est pas listée, redémarrez la montre. Si plusieurs cartes couvrent la même zone, désactivez celles que vous ne voulez pas voir.

Toujours invisible ? Écrivez à [hello@terento.app](mailto:hello@terento.app?subject=Terento%20installation%20issue) en indiquant le modèle exact de la montre, la région de la carte et ce qui s’est passé.

## Si quelque chose ne fonctionne pas

### Terento ne détecte pas la montre

Attendez 1 à 2 minutes après la connexion. Si la montre n’apparaît toujours pas, reconnectez-la, vérifiez que le câble permet les données et fermez les autres apps susceptibles de l’utiliser. Plus d’aide : [Montre Garmin non détectée sur Mac](https://terento.app/fr/guides/troubleshooting/#connect-watch), [Garmin Express ou une autre app utilise la montre](https://terento.app/fr/guides/troubleshooting/#garmin-busy), [Montre Garmin non reconnue : mode USB (MTP)](https://terento.app/fr/guides/troubleshooting/#usb-mode).

### L’installation ou la mise à jour est indisponible

Les cartes temporairement indisponibles restent visibles. Lisez la raison affichée à côté de la carte. Si le fournisseur est inaccessible ou si les téléchargements sont suspendus, réessayez plus tard. Si Terento ne peut pas vérifier la disponibilité actuelle, vérifiez votre connexion Internet et réessayez. Vos cartes déjà installées restent disponibles. Plus d’aide : [La liste des cartes Garmin ne se charge pas ou Terento doit être mis à jour](https://terento.app/fr/guides/troubleshooting/#catalog-unavailable), [Échec du téléchargement de la carte Garmin](https://terento.app/fr/guides/troubleshooting/#download-failed).

### Échec de l’installation

Sur l’écran d’échec de l’installation, choisissez « Report issue ». Terento ouvre GitHub avec le rapport déjà rempli. Vérifiez-le avant de le publier : les issues GitHub sont publiques. Pour une aide par e-mail, indiquez le modèle de votre montre, la région de la carte et ce qui s’est passé. Plus d’aide : [Échec de l’installation de la carte : carte restante sur la montre](https://terento.app/fr/guides/troubleshooting/#leftover-map), [Signaler un problème avec Terento](https://terento.app/fr/guides/troubleshooting/#send-report).

[Voir toutes les solutions](https://terento.app/fr/guides/troubleshooting/)

## Désinstaller Terento

Quittez Terento et placez-le dans la Corbeille depuis Applications. Les cartes déjà sur votre montre y restent. Terento conserve les informations sur les cartes qu’il a installées dans ~/Library/Application Support/Terento : gardez ce dossier si vous comptez réinstaller Terento, pour qu’il puisse encore mettre à jour et supprimer ces cartes. Pour tout supprimer, effacez aussi ce dossier, ~/Library/Caches/Terento, ~/Library/Logs/Terento et ~/Library/Preferences/app.terento.mac.plist.
