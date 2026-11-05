---
title: "Cartes gratuites sur Garmin Edge depuis un Mac — Terento"
canonical: https://terento.app/fr/guides/install-garmin-maps-edge-mac/
---

# Installer des cartes gratuites sur votre Garmin Edge depuis un Mac

Les compteurs vélo Garmin Edge récents n’apparaissent pas comme un disque sur un Mac : impossible d’y copier simplement un fichier de carte. Terento installe des cartes OpenStreetMap gratuites, ou votre propre fichier de carte compatible, sur les compteurs vélo Garmin Edge qui prennent en charge les cartes, comme les Edge 540, 840 et 1050.

[Télécharger](https://terento.app/fr/download/)

## Ce qu’il vous faut

- Mac Apple Silicon avec macOS 13 ou version ultérieure
- Garmin Edge récent prenant en charge les cartes
- Câble USB permettant le transfert de données

Après la connexion, Terento vérifie l’Edge et vous indique s’il peut installer des cartes. La page [Compatibilité](https://terento.app/fr/compatibility/) liste les modèles avec des installations réussies ; un modèle absent n’est pas forcément incompatible.

## Installer une carte sur votre Edge

1. Télécharger et ouvrir Terento

[Téléchargez Terento](https://terento.app/fr/download/), faites-le glisser de l’image disque vers Applications, puis ouvrez-le depuis ce dossier. À la première ouverture, macOS demande si vous voulez ouvrir une app téléchargée depuis Internet : choisissez Ouvrir.

2. Connecter l’Edge

Quittez Garmin Express s’il est ouvert. Connectez l’Edge directement au Mac avec un câble USB de données, sans passer par un hub. Si macOS demande d’autoriser la connexion de l’accessoire, choisissez Autoriser. Terento trouve l’Edge en 2 minutes maximum et vérifie s’il peut installer des cartes.

3. Choisir une carte

Choisissez un fournisseur et une région dans le catalogue, ou ajoutez depuis votre Mac votre propre fichier de carte .img compatible. [Comparez les styles de carte](https://terento.app/fr/map-styles/) pour voir comment chaque carte affiche routes et sentiers.

Terento affiche les fournisseurs, les régions de cartes tierces et l’espace Garmin disponible
Choisissez une carte dans le catalogue ou ajoutez votre propre fichier compatible.

4. Installer

Lancez l’installation et gardez l’Edge connecté jusqu’à ce que Terento indique que l’installation est terminée. Déconnectez ensuite l’Edge.

Terento affiche une installation de carte terminée
Gardez l’Edge connecté jusqu’à ce que Terento indique que la carte est prête.

## Afficher la carte sur votre Edge

Déconnectez l’Edge, ouvrez ses réglages de carte et vérifiez que la nouvelle carte est activée. Si elle n’est pas listée, redémarrez l’Edge. Si plusieurs cartes couvrent la même zone, désactivez celles que vous ne voulez pas voir.

## Si quelque chose ne fonctionne pas

### Le Garmin Edge n’apparaît pas dans Terento

Utilisez un câble USB de données, connectez l’Edge directement plutôt que via un hub, quittez Garmin Express et les apps de transfert de fichiers, puis attendez jusqu’à 2 minutes. Plus d’aide : [Montre Garmin non détectée sur Mac](https://terento.app/fr/guides/troubleshooting/#connect-watch), [Garmin Express ou une autre app utilise la montre](https://terento.app/fr/guides/troubleshooting/#garmin-busy).

### L’installation ou la mise à jour est indisponible

Les cartes temporairement indisponibles restent visibles. Lisez la raison affichée à côté de la carte. Si le fournisseur est inaccessible ou si les téléchargements sont suspendus, réessayez plus tard. Si Terento ne peut pas vérifier la disponibilité actuelle, vérifiez votre connexion Internet et réessayez. Vos cartes déjà installées restent disponibles. Plus d’aide : [La liste des cartes Garmin ne se charge pas ou Terento doit être mis à jour](https://terento.app/fr/guides/troubleshooting/#catalog-unavailable), [Échec du téléchargement de la carte Garmin](https://terento.app/fr/guides/troubleshooting/#download-failed).

### Échec de l’installation

Sur l’écran d’échec de l’installation, choisissez « Report issue ». Terento ouvre GitHub avec le rapport déjà rempli. Vérifiez-le avant de le publier : les issues GitHub sont publiques. Pour une aide par e-mail, indiquez le modèle de votre Edge, la région de la carte et ce qui s’est passé. Plus d’aide : [Échec de l’installation de la carte : carte restante sur la montre](https://terento.app/fr/guides/troubleshooting/#leftover-map), [Signaler un problème avec Terento](https://terento.app/fr/guides/troubleshooting/#send-report).

[Voir toutes les solutions](https://terento.app/fr/guides/troubleshooting/)

## Pourquoi votre Garmin Edge n’apparaît pas sur votre Mac

Les Edge récents, comme les Edge 540, 840 et 1050, échangent des fichiers en USB comme les téléphones Android. macOS ne prend pas ce mode en charge nativement : l’Edge n’apparaît donc pas comme un disque dans le Finder, et les guides qui conseillent de copier un fichier de carte dans le dossier Garmin ne fonctionnent pas pour ces modèles. Terento dialogue directement avec l’Edge : vous n’avez besoin ni d’Android File Transfer ni d’OpenMTP.

## Anciens modèles Edge

Les modèles plus anciens, comme l’Edge 1030 Plus et les précédents, apparaissent généralement sur un Mac comme un disque USB. Sur ceux-ci, vous pouvez copier vous-même un fichier de carte .img compatible dans le dossier Garmin du disque, sans Terento. Terento n’est pas conçu pour ces modèles.
