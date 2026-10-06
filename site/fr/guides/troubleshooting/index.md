---
title: "Montre Garmin non détectée sur Mac ? Dépannage — Terento"
canonical: https://terento.app/fr/guides/troubleshooting/
---

Dépannage

# Résoudre les problèmes de montre Garmin et de cartes sur Mac

Trouvez votre problème, d’une montre Garmin que le Mac ne détecte pas à un téléchargement de carte qui échoue, et suivez les étapes courtes. Si rien ne fonctionne, envoyez un rapport pour que nous puissions l’examiner.

Connexion

## Problèmes de connexion de la montre Garmin

### Montre Garmin non détectée sur Mac

Connectez la montre directement à votre Mac avec un câble USB qui transfère les données, déverrouillez-la et attendez jusqu’à 2 minutes : Terento la détecte automatiquement.

1. Utilisez un câble de données. Les câbles de recharge seule et certains hubs USB ne fonctionnent pas.
2. Attendez jusqu’à 2 minutes pendant que Terento vérifie la connexion.
3. Si la montre n’apparaît toujours pas, débranchez-la, attendez quelques secondes et reconnectez-la.
4. Si une autre app est ouverte, voir [Garmin Express ou une autre app utilise la montre](https://terento.app/fr/guides/troubleshooting/#garmin-busy).

### Garmin Express ou une autre app utilise la montre

Quittez Garmin Express et les apps de transfert de fichiers comme Android File Transfer, OpenMTP ou MacDroid : une seule app à la fois peut utiliser la connexion de la montre.

1. Quittez Garmin Express, Android File Transfer, OpenMTP, MacDroid et les autres apps MTP. Si Terento nomme une app, quittez-la en premier.
2. Fermez aussi Transfert d’images, Photos et Aperçu s’ils sont ouverts.
3. Si la montre apparaît dans le Finder, éjectez-la.
4. Débranchez la montre, reconnectez-la, puis choisissez « Refresh » dans Terento.

### Plusieurs appareils Garmin connectés

Déconnectez tous les appareils Garmin sauf la montre que vous voulez utiliser : Terento fonctionne avec un seul Garmin à la fois.

1. Débranchez les autres montres, compteurs vélo et appareils portables Garmin.
2. Gardez la montre choisie connectée et attendez que Terento la trouve.

### Montre Garmin non reconnue : mode USB (MTP)

Si Terento indique que la montre n’est pas prête pour le transfert de fichiers, réglez le mode USB de la montre sur MTP, si votre modèle dispose de ce réglage.

1. Sur la montre, ouvrez Mode USB, généralement dans Paramètres › Système. Tous les modèles ne l’ont pas.
2. Choisissez MTP.
3. Déconnectez la montre et reconnectez-la.

### Montre Garmin détectée mais pas prête

Si Terento trouve la montre mais que la connexion n’est pas prête dans les 2 minutes, débranchez la montre et reconnectez-la. Les blocages occasionnels de connexion sont une limite connue de la bêta actuelle.

1. Quittez les autres apps susceptibles d’utiliser la montre. Voir [Garmin Express ou une autre app utilise la montre](https://terento.app/fr/guides/troubleshooting/#garmin-busy).
2. Essayez un autre port USB ou un autre câble.
3. Si le problème persiste, redémarrez la montre et reconnectez-la.

### La montre Garmin ne répond plus

Débranchez la montre, attendez quelques secondes et reconnectez-la : la connexion a été perdue ou la montre ne répond plus à Terento.

1. Si Terento installait, mettait à jour ou supprimait une carte, ouvrez « Manage maps » après la reconnexion et vérifiez le résultat avant de réessayer.
2. Redémarrez la montre si cela se reproduit.

Vérifications

## Vérifications de la montre et des cartes

### Installation de cartes indisponible pour ce modèle Garmin

Terento installe des cartes uniquement sur les montres Garmin prenant en charge les cartes et activées dans Terento. Vous pouvez tout de même connecter la montre et parcourir les cartes.

1. Vérifiez que votre modèle de montre prend en charge les cartes.
2. Terento consulte sa liste actuelle à chaque connexion. Si votre modèle est activé plus tard, reconnectez la montre.
3. Indiquez-nous votre modèle exact pour que nous puissions l’examiner. Voir [Signaler un problème avec Terento](https://terento.app/fr/guides/troubleshooting/#send-report).

### Terento n’a pas pu vérifier votre montre Garmin

Vérifiez que votre Mac est connecté à Internet, puis reconnectez la montre : Terento a besoin d’Internet pour vérifier si des cartes peuvent être installées sur cette montre.

1. Ouvrez un site web pour confirmer que votre Mac est en ligne.
2. Débranchez la montre et reconnectez-la pour relancer la vérification.
3. Si cela échoue encore, attendez quelques minutes et réessayez.

### La liste des cartes Garmin ne se charge pas ou Terento doit être mis à jour

Si Terento ne peut pas charger la liste actuelle des cartes, vérifiez votre connexion Internet et réessayez dans quelques minutes. Les cartes déjà présentes sur votre montre ne sont pas concernées.

1. Si cette version de Terento est trop ancienne pour la liste actuelle et que Terento indique qu’une version plus récente est disponible, installez la mise à jour.
2. Tant que Terento affiche une ancienne liste enregistrée, l’installation et la mise à jour des cartes du catalogue restent indisponibles jusqu’à ce que la liste actuelle puisse être vérifiée.

Téléchargements et espace

## Téléchargement des cartes et espace libre

### Échec du téléchargement de la carte Garmin

Vérifiez votre connexion Internet et réessayez plus tard : Terento télécharge chaque carte directement auprès de son fournisseur, et les fournisseurs sont parfois lents ou temporairement indisponibles.

1. Lisez la raison affichée à côté de la carte. Si le fournisseur est indisponible ou si les téléchargements sont suspendus, réessayez plus tard.
2. Relancez l’installation.

### Pas assez d’espace sur le Mac pour télécharger la carte

Libérez de l’espace sur votre Mac et réessayez : Terento a besoin d’espace temporaire pour télécharger et préparer une carte.

1. Supprimez les fichiers dont vous n’avez plus besoin et videz la corbeille.
2. Réessayez. Les grandes régions demandent plus d’espace.

### Pas assez d’espace sur la montre pour les cartes Garmin

Choisissez une région plus petite ou supprimez une carte dont vous n’avez plus besoin : Terento vérifie l’espace libre de la montre avant l’installation et ne commence pas si les cartes ne tiennent pas.

1. Choisissez une région plus petite ou moins de cartes.
2. Ouvrez « Manage maps » et supprimez une carte dont vous n’avez plus besoin.
3. Une mise à jour demande de l’espace supplémentaire pendant la vérification de la nouvelle carte. Libérez de l’espace si une mise à jour ne peut pas démarrer.

Installation et mises à jour

## Installation, mise à jour et suppression des cartes

### Échec de l’installation de la carte : carte restante sur la montre

Supprimez la carte restante dans « Manage maps », puis réinstallez-la. Si une installation s’arrête après le début de la copie, une partie de la carte peut rester sur la montre, et Terento ne la supprime pas automatiquement.

1. Reconnectez la montre et attendez que Terento soit prêt.
2. Ouvrez « Manage maps » et vérifiez la liste.
3. Si la carte de l’installation échouée y figure, supprimez-la, puis réinstallez-la.
4. Si cela échoue encore, [envoyez un rapport](https://terento.app/fr/guides/troubleshooting/#send-report).

### La mise à jour ou la suppression d’une carte prend du temps

C’est attendu dans la bêta actuelle : la mise à jour ou la suppression d’une carte peut rester un moment à un pourcentage élevé avant de se terminer. Gardez la montre connectée et votre Mac éveillé.

1. Ne débranchez pas la montre pendant que Terento travaille.
2. Attendez que Terento indique que c’est terminé.
3. Si Terento signale un échec, reconnectez la montre et vérifiez « Manage maps » avant de réessayer.

Toujours bloqué ?

## Obtenir de l’aide

### Signaler un problème avec Terento

Sur l’écran d’échec, choisissez « Report issue » : Terento ouvre GitHub avec le rapport enregistré sur votre Mac déjà rempli.

1. Plus tard, vous pouvez utiliser « Report latest failure » dans « Diagnostics ».
2. Si le formulaire GitHub est vide, cliquez dans le champ du rapport, appuyez sur ⌘A puis sur ⌘V.
3. Vérifiez le rapport avant de le publier : les issues GitHub sont publiques.
4. Pas de compte GitHub ? Écrivez à [hello@terento.app](mailto:hello@terento.app?subject=Terento%20installation%20issue) en indiquant le modèle de votre montre, la région de la carte et ce qui s’est passé.

Nouveau sur Terento ?

## Commencez par le guide d’installation en trois étapes.

[Lire le guide d’installation sur Mac](https://terento.app/fr/guides/install-garmin-maps-mac/)
