Radio Spot Watcher — v2.84 stable

Radio Spot Watcher est une application temps réel pour radioamateurs.
Elle se connecte automatiquement à un cluster DX (telnet), récupère les spots HF/VHF/UHF, les affiche, les filtre et les met en forme en direct.

Objectif :

- Voir qui est actif maintenant, sur quelle bande, quel mode, et depuis quel pays.
- Surveiller des indicatifs perso (watchlist).
- Suivre les pays rares (Most Wanted DXCC).
- Avoir un aperçu clair des tendances (stats, bande active, etc.).

Cette version documente la v2.84 "stable".

✨ Fonctions principales

1. Connexion cluster DX

- Connexion telnet automatique au cluster (par défaut dxfun.com:8000).
- Tentative automatique de reconnexion si la session tombe.
- Indicateur d’état :
   - Vert = connecté
   - Rouge = hors ligne
- Le nom du cluster actif est affiché dans l’interface.

2. Tableau des spots en direct

- Les spots sont affichés dès leur réception.
- Colonnes typiques :
   - UTC (heure du spot)
   - Fréq (kHz ou MHz)
   - Call (indicatif repéré)
   - Mode (SSB, CW, FT8, etc.)
   - Bande (20m, 6m, 2m…)
   - DXCC (pays)
   - Grid (locator si présent)
   - Spotter (qui a spotté)
- Le dernier spot reçu apparaît en haut du tableau.
- Les indicatifs sont cliquables (ouverture QRZ).
- Les lignes correspondant à un indicatif surveillé (watchlist) sont mises en évidence visuellement.

3. Filtres Bande / Mode

- Menu déroulant "Bande" → toutes / 160m / 80m / … / 2m / 70cm / QO-100.
- Menu déroulant "Mode" → tous / SSB / CW / FT8 / RTTY / SAT / etc.
- Les filtres agissent en direct sur le tableau des spots sans recharger toute l’app.

4. Watchlist (surveillance d’indicatifs)

- Possibilité d’ajouter un ou plusieurs indicatifs à surveiller.
- Les entrées de la watchlist sont affichées dans l’entête avec un style "badge".
- Chaque badge a un bouton (poubelle) pour retirer l’indicatif de la surveillance.
- Quand un spot correspond à un indicatif surveillé :
   - La ligne est surlignée (évidente visuellement).
   - Cela attire l’œil immédiatement.

5. Most Wanted DXCC

- Liste des entités DXCC les plus recherchées (îles / expéditions rares).
- Affichées dans des cartes/pastilles (deux colonnes).
- Affiche le nom du pays / de l’île.
- Icône drapeau prévue par pays (ou par entité DXCC) pour l’identification visuelle rapide.

But : savoir si une expédition rare apparaît dans le cluster.

6. Carte des spots

- Carte (Leaflet) qui affiche les spots récents.
- Chaque spot est converti en coordonnées (approx) selon le pays / locator / info connue.
- Les marqueurs sont colorés selon la bande.
   - Exemple : 20m, 40m, 6m → couleurs différentes.
- Possibilité de réduire/agrandir l’affichage carte dans la colonne droite.

7. Statistiques en direct

- Graphiques bande / activité.
- Histogramme du nombre de spots par bande sur les dernières minutes.
- Courbes en bas de page (ou dans la colonne droite sous la carte selon layout).
- Mise à jour automatique au fil de l’eau.

8. Flux RSS DX News

- Intégration d’un flux d’actus DX (annonces d’expéditions, alertes).
- Les titres récents sont affichés dans un panneau.
- Couleur du flux revue (lisible sur thème sombre OU thème clair).

9. Thèmes de couleur (UI)

- Deux grandes orientations d’UI sont supportées par conception :
   - Thème sombre / style "console opérateur" (fond gris très foncé, texte vert/jaune)
   - Thème clair moderne (gris clair + bleuté)
- Les couleurs des lignes "spot surveillé" (watchlist) sont personnalisables dans un bloc CSS.
- L’idée : l’utilisateur pourra ajuster facilement le style sans toucher à la logique Python.

10. En-tête d’état

En haut de l’écran on trouve :

- Version logicielle (ex: "Radio Spot Watcher v2.84 stable stable stable").
- Statut cluster + hôte/port.
- Nombre total de spots reçus.
- Nombre de spots reçus dans les 5 dernières minutes.
- Heure de dernière mise à jour.
- Menus Bande / Mode.
- Zone Watchlist.

Le tout tient sur une ligne pour un look "tableau de bord" type station radio.

🧠 Comment ça marche (résumé technique)

Backend

- Écrit en Python 3.11+.
- Framework web : Flask.
- Le code ouvre un socket telnet vers le cluster DX.
- Chaque ligne reçue est parsée avec des regex.
- Les spots sont stockés en mémoire (deque avec limite).
- Les stats (par bande) sont calculées en temps réel.
- La liste des Most Wanted peut venir d’un JSON embarqué (fallback) ou d’une source distante.
- Le backend expose des endpoints JSON (ex: "/spots.json", "/status.json", "/wanted.json", etc.) consommés en AJAX par le front.

Frontend

- HTML généré côté Python (template inline dans le code).
- CSS embarqué dans le même fichier (style sombre ou clair, selon version).
- JavaScript embarqué :
   - Rafraîchissement périodique des spots (fetch JSON).
   - Mise à jour de la carte et des graphes.
   - Gestion de la watchlist.
   - Application des filtres Bande / Mode sans rechargement complet.

Relance automatique

- Le script "start.sh" :
   - Active l’environnement virtuel Python (venv).
   - Vérifie si le port 8000 est déjà pris par une instance précédente → si oui, la tue.
   - Lance "webapp.py" sur "0.0.0.0:8000".
- En cas de déconnexion cluster, la boucle tente un reconnect.

Pas de base de données

- Tout tourne en mémoire.
- Watchlist et préférences peuvent être persistées plus tard dans un petit fichier JSON local (ex: "config.json"), mais ce n’est pas obligatoire pour démarrer.

🛠 Installation rapide (Raspberry Pi / Debian)

1. Installer les dépendances système de base :

sudo apt update
sudo apt install -y python3 python3-venv python3-pip telnet

2. Cloner le projet :

git clone https://github.com/<ton-compte>/radio-spot-watcher.git
cd radio-spot-watcher

3. Créer l’environnement Python :

python3 -m venv venv
source venv/bin/activate
pip install flask requests

«(d’autres libs Python standard sont déjà incluses dans la stdlib : "socket", "re", "threading", "collections.deque", etc.)»

4. Lancer :

./start.sh

5. Ouvrir dans le navigateur :

   - http://127.0.0.1:8000
   - ou depuis le LAN : http://IP_DU_PI:8000

💡 Astuce :
Si le cluster par défaut (dxfun.com:8000) est indisponible, l’appli tente un fallback (ex: autre cluster telnet connu).
Le statut "Connecté" / "Hors ligne" te le dira tout de suite.

🔧 Personnalisation

Changer l’indicatif par défaut

Dans le code, la variable "CALLSIGN" (ou similaire) sert pour l’identification auprès du cluster telnet.
Tu peux la remplacer par ton propre indicatif radioamateur.

Modifier les couleurs

Dans la section "<style>" intégrée :

- ".row-watch" ou équivalent : couleur des lignes quand un call surveillé apparaît.
- ".rss-item" : couleur du flux RSS.
- Palette globale : variables CSS (par ex. "--bg", "--text", etc. dans la version thème clair).

Ajouter une entité Most Wanted

Tu peux éditer la liste interne des entités rares (pays/îles DXCC) + associer un drapeau.
Idéalement, associer :

- code entité,
- libellé humain,
- emoji / icône drapeau (ou petite image inline),
- position dans la grille.

📌 Feuille de route (roadmap)

Priorités courtes :

1. Améliorer la watchlist :
   - plus de popup moche → champ inline + bouton +
   - icône poubelle pour retirer.
2. Drapeaux visibles dans "Most Wanted DXCC".
3. Couleurs lisibles du flux RSS en thème sombre.
4. Sauvegarde de la watchlist/local prefs dans un fichier JSON.
5. Choix utilisateur de la palette de couleur (clair/sombre + accents).

Idées moyennes :

- Sélecteur manuel du cluster (liste déroulante).
- Carte : possibilité de masquer/afficher certaines bandes.
- Bouton "Compacter" l’UI pour les petits écrans.


📜 Licence / usage

Projet hobby radioamateur pensé par Eric F1SMV et réalisé par Chatgpt5.
Utilisation personnelle OK.
Toute re-distribution publique doit citer l’auteur original du code et ne pas supprimer les mentions de version.


👋 Contact

Si tu trouves un bug, note :

- Version affichée dans l’interface (ex: v2.84 stable)
- Capture d’écran du haut de la page (barre d’état)
- Ce qui ne marche pas (ex: "Le flux RSS reste noir sur noir")

et ouvre un ticket / issue dans le repo GitHub.

73 ! 