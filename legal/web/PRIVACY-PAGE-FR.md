# Confidentialité

Cet avis concerne le site Terento, l’application macOS et l’installateur web. Aucun compte n’est nécessaire. Vos cartes et données d’appareil restent sur votre Mac ou dans votre navigateur ; les diagnostics et statistiques limités décrits ci-dessous sont transmis séparément.

## Contact

Responsable du traitement : particulier. Consultez [À propos de Terento](/fr/about/) ou contactez [privacy@terento.app](mailto:privacy@terento.app) au sujet de vos données.

## Diagnostics de l’application

Deux flux sont activés par défaut pour améliorer la fiabilité et la compatibilité. Il n’y a pas de choix de partage pendant l’installation. Désactivez chaque flux dans **Terento → Diagnostics** sans limiter l’application. Cela arrête les futurs envois et vide la file correspondante non envoyée. Les rapports transmis ne peuvent pas être supprimés depuis l’application ; utilisez le contact ci-dessus pour vos demandes.

- **Compatibilité :** modèle et micrologiciel de la montre, versions de l’application et de macOS, fournisseur/cartes sélectionnés, résultat et informations techniques limitées sur les erreurs.
- **Utilisation des cartes :** fournisseur, carte/région, résultat du téléchargement ou de l’installation, heure, build et identifiants aléatoires d’opération/événement. Les imports `.img` personnels sont exclus.

Les rapports excluent les Garmin Unit IDs, valeurs de numéros de série, comptes, chemins locaux, cartes et journaux bruts. Les rapports individuels sont privés ; seuls des résultats agrégés de compatibilité vérifiés sont publiés. Le fondement est l’intérêt légitime à améliorer la fiabilité et la couverture des appareils, selon l’article 6(1)(f) du RGPD.

## Installateur web

L’installateur web permet d’installer des cartes sur votre montre depuis Google Chrome, sans l’application. Chrome lit sur votre ordinateur ce dont il a besoin, comme le modèle de la montre, l’espace libre et les cartes.

Quand vous choisissez une carte, le serveur de Terento la télécharge depuis le fournisseur d’origine et la transmet à votre navigateur. Cette copie est faite pour votre seule demande, n’est pas partagée et est supprimée dès que votre navigateur l’a reçue, ou après deux heures si elle n’est pas récupérée. Le fournisseur voit le serveur de Terento, pas vous. Pour chaque copie, le serveur conserve un enregistrement de la carte (fournisseur, carte, région et version), de sa taille, de la part reçue par votre navigateur, des horaires et du résultat, sans rien sur vous, votre navigateur ou votre montre. Ces enregistrements sont conservés 24 mois.

La page envoie à Terento, à chaque étape, de courtes notes qui ne vous identifient pas : si ce navigateur peut être utilisé, si la montre s’est connectée et comment chaque installation, mise à jour ou suppression de carte s’est terminée. Elles contiennent :

- le modèle de la montre et sa version logicielle
- le système d’exploitation et le navigateur, avec leur version principale
- le fournisseur, la carte, sa tranche de taille et s’il s’agit d’une nouvelle installation ou d’une mise à jour
- l’étape en échec, un code de motif fixe, des codes d’erreur standard du navigateur, de notre serveur ou de la montre, et la durée d’écriture et de vérification
- un code aléatoire créé à chaque ouverture de la page, pour regrouper les étapes d’une même visite

Elles ne contiennent jamais le numéro de série ou l’Unit ID de votre montre, votre adresse IP, des noms de fichiers, la liste des cartes de votre montre ni de texte d’erreur. Votre adresse IP n’est gardée que brièvement en mémoire pour limiter le nombre de requêtes d’un même ordinateur, et n’est pas enregistrée. Ces notes nous montrent quelles montres et quels systèmes et navigateurs fonctionnent et nous aident à corriger les échecs. La base est l’intérêt légitime selon l’article 6(1)(f) du RGPD. La page n’a pas d’interrupteur ; contactez-nous pour vous opposer. Les notes individuelles sont privées et conservées 24 mois.

Certaines données restent dans votre navigateur, pas sur notre serveur : les cartes installées par l’installateur web et sur quelle montre, pour pouvoir les mettre à jour ou les supprimer en toute sécurité, une copie temporaire d’une carte jusqu’à son installation et la langue choisie. Pour reconnaître la montre, il enregistre un code à sens unique tiré des données de la montre et d’une valeur aléatoire, qui ne permet pas de retrouver le numéro de série. Effacer dans Chrome les données du site de l’installateur web supprime tout cela. L’installateur web ne charge pas les statistiques du site.

## Connexions du site et de l’application

Les requêtes au site, à l’installateur web, à l’API, au catalogue et aux mises à jour peuvent communiquer votre adresse IP et des métadonnées aux hébergeurs et services de sécurité. Dans l’application, les cartes du catalogue sont téléchargées directement depuis Freizeitkarte, OpenTopoMap, MapRando ou BBBike ; leurs règles de confidentialité s’appliquent à ces connexions. La vérification au démarrage récupère des informations de version, pas l’application.

Ces connexions fournissent le contenu et les fonctions demandées et protègent contre les abus. Le traitement de sécurité repose sur l’intérêt légitime selon l’article 6(1)(f) du RGPD.

## Assistance et signalements publics

Si vous nous écrivez, nous recevons votre adresse, message et pièces jointes pour répondre et examiner le problème. N’envoyez pas de cartes, d’identifiants de connexion ou d’identifiants privés d’appareil. L’assistance repose sur l’intérêt légitime à répondre aux demandes et maintenir l’application.

Un ticket GitHub est distinct des diagnostics automatiques : vous le vérifiez et l’envoyez ; son contenu et votre nom de compte peuvent être publics. La [politique de GitHub](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement) s’applique. Les dons facultatifs passent par [Buy Me a Coffee](https://www.buymeacoffee.com/privacy-policy), qui traite les données de paiement selon ses conditions.

## Rapports d’assistance

Lorsque l’application propose d’envoyer un rapport d’assistance à Terento, le rapport n’est envoyé que si vous choisissez de l’envoyer, après en avoir vu le contenu. Il contient les détails nettoyés également utilisés pour les rapports GitHub : versions de l’application et de macOS, modèle et variante de la montre, étape en échec, catégorie et message d’erreur, fournisseur et région de la carte, durées, ainsi que la description que vous ajoutez. Il exclut les numéros de série, Unit IDs, comptes, chemins locaux, journaux bruts et cartes ; aucun compte GitHub n’est nécessaire. N’indiquez pas de données personnelles dans la description.

Les rapports d’assistance servent uniquement à diagnostiquer le problème signalé, ne sont pas utilisés pour les statistiques et sont conservés 12 mois. L’accès est réservé à l’administration du projet ; votre adresse IP n’est pas enregistrée avec le rapport. Le fondement est l’intérêt légitime à répondre à votre demande et maintenir l’application, selon l’article 6(1)(f) du RGPD.

## Statistiques et stockage du navigateur

Umami est chargé pour tous les visiteurs pour mesurer les pages vues, clics et téléchargements. Il n’utilise pas de cookies de suivi. Il peut traiter les URL de page/provenance, navigateur, système, appareil et localisation approximative. Les valeurs UTM des liens décrivent les sources de campagne. Terento les transmet dans les URL sans stocker les campagnes dans votre navigateur. Les statistiques servent à améliorer le site et mesurer les campagnes sur la base de l’intérêt légitime, article 6(1)(f) du RGPD. Il n’y a ni bandeau de consentement analytique ni interrupteur sur le site ; contactez-nous pour vous opposer. Ces statistiques sont distinctes des réglages de diagnostic de l’app.

Une langue choisie est mémorisée sous `terento-language` dans le stockage local. Cette préférence demandée est distincte de l’analytique. Cloudflare peut utiliser des cookies de sécurité selon ses réglages.

## Destinataires et conservation

Le site, l’installateur web, l’API et la base de données utilisent Hostinger ; Cloudflare assure la diffusion et la protection du trafic. Umami fonctionne à `stats.enduristas.lt`. Consultez [Cloudflare](https://www.cloudflare.com/privacypolicy/) et [Hostinger](https://www.hostinger.com/legal/privacy-policy) pour leurs traitements. Les configurations peuvent impliquer des traitements hors EEE ; contactez-nous pour les modalités applicables.

La politique de conservation des diagnostics transmis et des notes de l’installateur web est de 24 mois. L’accès est réservé à l’administration du projet. Des sauvegardes chiffrées de la base de données de l’API et de la configuration du serveur sont conservées jusqu’à 14 jours sur un équipement distinct contrôlé par le projet. Les échanges d’assistance sont conservés tant que nécessaires au traitement de la demande, des litiges associés ou des obligations légales. Contactez-nous au sujet d’autres durées propres aux services ou d’un rapport précis.

## Vos choix et droits

Vous pouvez demander accès, rectification, effacement ou limitation et vous opposer aux traitements fondés sur l’intérêt légitime. La portabilité s’applique lorsque ses conditions légales sont réunies.

Écrivez à [privacy@terento.app](mailto:privacy@terento.app). Nous répondons normalement sous un mois et expliquons toute prolongation légale. Les rapports ne sont pas liés à un compte ou identifiant direct d’appareil ; des précisions peuvent être nécessaires pour retrouver le vôtre. Vous pouvez saisir l’[autorité lituanienne VDAI](https://vdai.lrv.lt/) ou une autre autorité compétente.

## Champs techniques des diagnostics

La compatibilité peut aussi inclure un libellé MTP nettoyé, USB VID/PID, transport, catégorie de source d’identité (jamais sa valeur), versions des cartes, horodatages, identifiants aléatoires, étape d’échec, codes d’erreur autorisés, état d’écriture/nettoyage et progression approximative. Les imports personnels utilisent des catégories générales. Aucun flux n’envoie de manifestes, identifiants d’objets MTP, empreintes de cartes ou erreurs non filtrées.

Les rapports peuvent aussi contenir la description originale du modèle XML (160 caractères maximum) et son code produit (64 lettres ASCII, chiffres ou traits d’union maximum). Ces données désignent un modèle, pas une montre individuelle. Les documents XML complets, Unit IDs et numéros de série sont exclus. Les correspondances des codes et les corrections administratives sont conservées séparément du rapport original.

Mise à jour : 10 octobre 2026.
