---
title: "Dépannage des cartes Garmin sur Mac — Terento"
canonical: https://terento.app/fr/guides/troubleshooting/
---

Dépannage

# Résoudre les problèmes courants de Terento

Trouvez le problème affiché par Terento et suivez les étapes courtes correspondantes. Si rien ne fonctionne, envoyez un rapport pour que nous puissions l’examiner.

Connexion

## Connecter votre montre

### Terento attend votre montre

Terento détecte la montre automatiquement après la connexion. Cela peut prendre jusqu’à 2 minutes.

1. Connectez la montre directement à votre Mac avec un câble USB qui permet le transfert de données. Les câbles de recharge seule et certains hubs ne fonctionnent pas.
2. Déverrouillez la montre.
3. Attendez jusqu’à 2 minutes pendant que Terento vérifie la connexion.
4. Si la montre n’apparaît toujours pas, débranchez-la, attendez quelques secondes et reconnectez-la.

### Une autre app utilise la montre

Une seule app à la fois peut utiliser la connexion de la montre.

1. Quittez Garmin Express et toute autre app capable d’ouvrir la montre, par exemple une app de transfert de fichiers.
2. Si la montre apparaît dans le Finder, éjectez-la.
3. Reconnectez la montre, puis choisissez « Refresh » dans Terento.

### Plusieurs appareils Garmin sont connectés

Terento fonctionne avec un seul appareil Garmin à la fois.

1. Déconnectez tous les appareils Garmin sauf la montre que vous voulez utiliser.
2. Gardez cette montre connectée et attendez que Terento la trouve.

### La montre n’est pas prête pour le transfert de fichiers

Certaines montres Garmin disposent d’un réglage Mode USB qui détermine comment elles se connectent à un ordinateur.

1. Sur la montre, cherchez Mode USB, généralement dans Paramètres › Système. Tous les modèles ne l’ont pas.
2. Si le réglage existe, choisissez MTP.
3. Déconnectez la montre et reconnectez-la.

### La montre est détectée mais n’est pas prête

Terento a détecté la montre, mais la connexion n’était pas prête dans les 2 minutes. Les blocages occasionnels de connexion sont une limite connue de la bêta actuelle.

1. Débranchez la montre et reconnectez-la.
2. Fermez les autres apps susceptibles d’utiliser la montre.
3. Essayez un autre port USB ou un autre câble.
4. Si le problème persiste, redémarrez la montre et reconnectez-la.

### La montre ne répond plus

La connexion a été perdue ou la montre ne répond plus à Terento.

1. Débranchez la montre, attendez quelques secondes et reconnectez-la.
2. Si Terento installait, mettait à jour ou supprimait une carte, ouvrez « Manage maps » après la reconnexion et vérifiez le résultat avant de réessayer.
3. Redémarrez la montre si cela se reproduit.

Vérifications

## Vérifications de la montre et des cartes

### Ce modèle de montre n’est pas activé pour l’installation de cartes

Terento installe des cartes uniquement sur les montres Garmin prenant en charge les cartes et activées dans Terento. Vous pouvez tout de même connecter la montre et parcourir les cartes.

1. Vérifiez que votre modèle de montre prend en charge les cartes.
2. Terento consulte sa liste actuelle à chaque connexion. Si votre modèle est activé plus tard, reconnectez la montre.
3. Indiquez-nous votre modèle exact pour que nous puissions l’examiner. Voir [Envoyer un rapport](https://terento.app/fr/guides/troubleshooting/#send-report).

### Terento n’a pas pu vérifier cette montre

Terento a besoin d’une connexion Internet pour vérifier si des cartes peuvent être installées sur cette montre.

1. Vérifiez que votre Mac est connecté à Internet.
2. Reconnectez la montre pour relancer la vérification.
3. Si cela échoue encore, attendez quelques minutes et réessayez.

### La disponibilité des cartes n’a pas pu être vérifiée

Terento n’a pas pu charger la liste actuelle des cartes, ou cette version de Terento est trop ancienne pour elle. Les cartes déjà présentes sur votre montre ne sont pas concernées.

1. Vérifiez votre connexion Internet et réessayez dans quelques minutes.
2. Si Terento indique qu’une version plus récente est disponible, installez la mise à jour.
3. Tant que Terento affiche une ancienne liste enregistrée, l’installation et la mise à jour des cartes du catalogue restent indisponibles jusqu’à ce que la liste actuelle puisse être vérifiée.

Téléchargements et espace

## Téléchargements et espace libre

### Le téléchargement de la carte a échoué

Terento télécharge chaque carte directement auprès de son fournisseur. Les fournisseurs sont parfois lents ou temporairement indisponibles.

1. Vérifiez votre connexion Internet.
2. Lisez la raison affichée à côté de la carte. Si le fournisseur est indisponible ou si les téléchargements sont suspendus, réessayez plus tard.
3. Relancez l’installation.

### Espace libre insuffisant sur le Mac

Terento a besoin d’espace temporaire sur votre Mac pour télécharger et préparer une carte.

1. Libérez de l’espace sur votre Mac, par exemple en supprimant des fichiers dont vous n’avez plus besoin.
2. Réessayez. Les grandes régions demandent plus d’espace.

### Espace libre insuffisant sur la montre

Terento vérifie l’espace libre de la montre avant l’installation et ne commence pas si les cartes ne tiennent pas.

1. Choisissez une région plus petite ou moins de cartes.
2. Supprimez dans « Manage maps » une carte dont vous n’avez plus besoin.
3. Une mise à jour demande de l’espace supplémentaire pendant la vérification de la nouvelle carte. Libérez de l’espace si une mise à jour ne peut pas démarrer.

Installation et mises à jour

## Installations, mises à jour et suppressions

### L’installation a échoué après l’écriture de la carte

Si une installation s’arrête après le début de la copie, une partie de la carte peut rester sur la montre. Terento ne la supprime pas automatiquement.

1. Reconnectez la montre et attendez que Terento soit prêt.
2. Ouvrez « Manage maps » et vérifiez la liste.
3. Si la carte de l’installation échouée y figure, supprimez-la, puis réinstallez-la.
4. Si cela échoue encore, [envoyez un rapport](https://terento.app/fr/guides/troubleshooting/#send-report).

### Les mises à jour ou suppressions prennent du temps

La mise à jour ou la suppression d’une carte peut rester un moment à un pourcentage élevé avant de se terminer. C’est attendu dans la bêta actuelle.

1. Gardez la montre connectée et votre Mac éveillé jusqu’à ce que Terento indique que c’est terminé.
2. Ne débranchez pas la montre pendant que Terento travaille.
3. Si Terento signale un échec, reconnectez la montre et vérifiez « Manage maps » avant de réessayer.

Toujours bloqué ?

## Obtenir de l’aide

### Envoyer un rapport

Lorsqu’une installation, une mise à jour ou une suppression échoue, Terento enregistre sur votre Mac un rapport qui nous aide à analyser le problème.

1. Sur l’écran d’échec, choisissez « Report issue ». Plus tard, vous pouvez utiliser « Report latest failure » dans « Diagnostics ».
2. Terento ouvre GitHub avec le rapport déjà rempli. Si le formulaire est vide, cliquez dans le champ du rapport, appuyez sur ⌘A puis sur ⌘V.
3. Vérifiez le rapport avant de le publier : les issues GitHub sont publiques.
4. Pas de compte GitHub ? Écrivez à [hello@terento.app](mailto:hello@terento.app?subject=Terento%20installation%20issue) en indiquant le modèle de votre montre, la région de la carte et ce qui s’est passé.

Nouveau sur Terento ?

## Commencez par le guide d’installation en trois étapes.

[Lire le guide d’installation sur Mac](https://terento.app/fr/guides/install-garmin-maps-mac/)
