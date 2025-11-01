# Radio Spot Watcher — v2.87 (2025-10-31)

## Résumé
**Radio Spot Watcher** est une application web légère qui permet de surveiller en temps réel les spots DX reçus sur un cluster telnet. 
Elle affiche les spots sur une carte du monde, un tableau dynamique, des graphiques d’activité, des flux RSS et une watchlist. 
Cette version 2.87 introduit la **mise à jour automatique de la base DXCC** (`dxcc_latest.json`), un **thème clair modernisé**, et des améliorations de performances.

---

## Fonctionnalités principales
- Connexion automatique au **cluster DXFun.com (port 8000)** avec bascule automatique vers un cluster de secours (F5LEN). 
- Tableau temps réel des spots (avec filtres bande/mode). 
- Carte du monde interactive (Leaflet.js). 
- Export CSV des spots reçus. 
- Flux RSS intégrés (DX-World, ClubLog). 
- Section “Most Wanted DXCC” mise à jour automatiquement. 
- Graphiques d’activité par bande et heure (Matplotlib). 
- Interface responsive et thème clair personnalisable. 
- Watchlist avec ajout/suppression et surbrillance automatique. 
- Synchronisation automatique du fichier DXCC. 
- Persistance locale des données (`spots.json`, `rspot.log`).

---

## Prérequis
- **Python 3.8+** 
- **pip** 
- Modules Python :
  ```bash
  pip install Flask requests feedparser matplotlib


---

Installation

1. Cloner ou copier le projet :

git clone https://github.com/Eric738/radio-spot-watcher.git
cd radio-spot-watcher


2. (Optionnel) Créer un environnement virtuel :

python3 -m venv venv
source venv/bin/activate


3. Lancer :

./start.sh


4. Ouvrir le navigateur :

http://127.0.0.1:8000




---

Variables d’environnement

Variable Description Valeur par défaut

PORT Port HTTP 8000
CLUSTER_HOST Hôte du cluster dxfun.com
CLUSTER_PORT Port cluster 8000
CLUSTER_FALLBACK_HOST Cluster de secours f5len.dxcluster.net
CLUSTER_FALLBACK_PORT Port secours 8000
CLUSTER_CALLSIGN Indicatif utilisateur F1SMV
MAX_SPOTS Nombre de spots en mémoire 200
MAX_MAP_SPOTS Spots visibles sur la carte 30
RSS_UPDATE_INTERVAL Mise à jour RSS (sec) 300
WANTED_UPDATE_INTERVAL Mise à jour Most Wanted (sec) 600
DXCC_FILE Base DXCC locale dxcc_latest.json
SPOTS_FILE Fichier spots spots.json
LOG_FILE Journal d’activité rspot.log



---

Endpoints HTTP

/ → interface principale

/spots.json → liste complète des spots

/status.json → état (cluster, DXCC, version)

/rss.json → flux RSS

/wanted.json → liste “Most Wanted”

/stats.json → statistiques

/export.csv → export CSV

/healthz → test de santé



---

Fichiers générés

Fichier Rôle

spots.json Historique des spots
dxcc_latest.json Base DXCC auto-mise à jour
rspot.log Journal d’activité



---

Personnalisation

Thèmes disponibles : default, ocean, sunset, contrast.

Watchlist enregistrée dans le navigateur.

Filtres bande/mode mémorisés par session.

Taille de carte et couleurs de spots sauvegardées.

Palette de 10 couleurs sélectionnable dans l’interface.



---

Mise à jour automatique DXCC

Au démarrage :

1. Charge le fichier local dxcc_latest.json.


2. Vérifie s’il existe une version plus récente sur :
https://raw.githubusercontent.com/Eric738/radio-spot-watcher/main/dxcc_latest.json


3. Met à jour automatiquement si nécessaire.


4. Journalise :

[DXCC] Mise à jour réussie (340 entités)




---

Exemple de service systemd

Créer /etc/systemd/system/radiospot.service :

[Unit]
Description=Radio Spot Watcher
After=network.target

[Service]
User=radio
WorkingDirectory=/home/radio/radio-spot-watcher
ExecStart=/usr/bin/python3 /home/radio/radio-spot-watcher/src/webapp.py
Restart=on-failure
Environment=PORT=8000

[Install]
WantedBy=multi-user.target

Puis activer :

sudo systemctl daemon-reload
sudo systemctl enable radiospot
sudo systemctl start radiospot


---

Dépannage

Aucun spot affiché
Vérifier la connexion :

ping dxfun.com
telnet dxfun.com 8000

DXCC manquant
Créer un fichier vide :

touch src/dxcc_latest.json

Il sera mis à jour automatiquement.

Port occupé
Modifier dans start.sh :

export PORT=8080

RSS vide
Attendre quelques minutes (limite de requêtes).



---

Exemple de log console

[INFO] Initialisation v2.87
[CLUSTER] Connecté à dxfun.com:8000
[DXCC] 340 entités chargées
[SOLAR] Données NOAA OK


---

Structure du projet

radio-spot-watcher/
│
├── src/
│   ├── webapp.py
│   ├── dxcc_latest.json
│   ├── static/
│   └── templates/
│
├── start.sh
└── README.md


---

Journal des modifications — v2.87

Date : 2025-10-31

Ajout : mise à jour automatique du DXCC depuis GitHub

Amélioration : interface, lisibilité et performance

Correctif : rafraîchissement RSS et persistance des spots

Préparation : palette de couleurs utilisateur



---

Sécurité

Pas d’authentification intégrée.
→ Utiliser un VPN ou proxy pour un accès distant.

Aucune donnée personnelle stockée ou transmise.

Les endpoints JSON sont réservés à un usage local.



---

Contribution

Pull requests bienvenues.

Ouvrir une issue avant toute modification majeure.

Tests recommandés : parsing DX, RSS, DXCC, graphiques.



---

Commandes utiles

curl -s http://127.0.0.1:8000/status.json | jq
curl -s http://127.0.0.1:8000/spots.json | jq '.spots | length'
wget http://127.0.0.1:8000/export.csv


---

Licence

Projet radioamateur développé par F1SMV, assisté de ChatGPT-5.
Libre pour usage personnel ou éducatif, redistribution autorisée avec mention de l’auteur et conservation du numéro de version.
Sous licence MIT.