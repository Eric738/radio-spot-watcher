Radio Spot Watcher — v2.85 (2025-10-28)
======================================

Résumé
------
Radio Spot Watcher est une web‑app légère pour suivre les spots DX en temps réel depuis un DX cluster (telnet), afficher la carte, le tableau des spots, flux RSS, watchlist et statistiques (charts).  
La version 2.85 ajoute des améliorations visuelles, une palette étendue (option "extended" de 10 couleurs) et un bloc Horloges (UTC + heure locale). Les charts sont dessinés en canvas (renderer maison) et la palette est configurable.

Principales fonctionnalités
---------------------------
- Connexion en lecture à un DX cluster (TCP/telnet) et parsing de lignes "DX".
- Tableau des derniers spots (watchlist, filtres Bande/Mode).
- Carte Leaflet avec cluster et marquage des spots.
- Export CSV des spots.
- Flux RSS (récupération périodique).
- Bloc "Most Wanted" (statique par défaut).
- Statistiques / charts (activité par bande et par mode).
- UI avec sélection de palette (incluant palette "extended" 10 couleurs).
- Horloges affichant UTC et heure locale (mise à jour chaque seconde).
- Persistence locale des spots (spots.json) et logs (rspot.log).

Prérequis
---------
- Python 3.8+ recommandé
- pip
- Dépendances Python :
  - Flask
  - requests
  - feedparser

Installation rapide
------------------
1. Cloner / copier le script python (le fichier principal ; ex: rspot.py).
2. Installer les dépendances :
   - pip install Flask requests feedparser
   - (optionnel) créer un virtualenv : python -m venv venv && source venv/bin/activate

Configuration (variables d'environnement)
-----------------------------------------
Le script lit quelques variables d'environnement (avec valeurs par défaut) :

- PORT : port HTTP (par défaut 8000)
- CLUSTER_HOST : hôte DX cluster (par défaut dxfun.com)
- CLUSTER_PORT : port DX cluster (par défaut 8000)
- CLUSTER_FALLBACK_HOST / CLUSTER_FALLBACK_PORT : fallback si primaire indisponible
- CLUSTER_CALLSIGN : callsign envoyé au cluster (par défaut F1ABC)
- MAX_SPOTS : nombre maximal de spots conservés en mémoire (défaut 200)
- MAX_MAP_SPOTS : nombre maximal de spots affichés sur la carte (défaut 30)
- RSS_UPDATE_INTERVAL : intervalle de mise à jour RSS en secondes (défaut 300)
- WANTED_UPDATE_INTERVAL : intervalle refresh Most Wanted (défaut 600)
- SPOTS_FILE : chemin du fichier de persistence des spots (défaut spots.json)
- CTY_FILE : fichier cty CSV (défaut cty.csv)
- LOG_FILE : fichier log (défaut rspot.log)

Lancer l'application
--------------------
Depuis le dossier contenant le script :

- Avec Python directement :
  - python rspot.py
  - par défaut écoute sur 0.0.0.0:8000 (ou PORT si défini).

- Tester l'interface :
  - Ouvrir http://127.0.0.1:8000 dans un navigateur.

Endpoints HTTP
--------------
- /            -> Interface web (HTML)
- /spots.json  -> JSON contenant la liste des spots et map_spots
  Exemple : { "spots": [...], "map_spots": [...] }
- /status.json -> Informations de statut (cluster_connected, cluster_host, version, dxcc_update, total_spots)
- /rss.json    -> Données RSS récupérées { "entries": [...] }
- /wanted.json -> Liste Most Wanted { "wanted": [...] }
- /stats.json  -> Agrégats : { "bands": {...}, "modes": {...} }
- /export.csv  -> Export CSV téléchargeable des spots
- /healthz     -> Ping de santé { "status": "ok", "version": "..." }

Fichiers générés / utilisés
---------------------------
- spots.json  : sauvegarde JSON des spots (persisté régulièrement et à chaque ajout).
- cty.csv     : (optionnel) fichier CTY pour résolution des préfixes -> pays. Si absent, fallback minimal embarqué est utilisé.
- rspot.log   : logs d'activité (rotating file handler si disponible).

Personnalisation UI
-------------------
- Palette : le sélecteur "Palette" permet de choisir entre plusieurs thèmes (default, ocean, sunset, contrast, extended). L'option "extended" fournit une palette de 10 couleurs utilisée par défaut pour les charts.
- Watchlist : stockée dans localStorage côté client.
- Filtres Bande / Mode : persistés côté navigateur (localStorage).
- Taille de la carte : persistée côté navigateur.

Dépendances Python
------------------
- Flask
- requests
- feedparser

Installation via requirements.txt (exemple)
------------------------------------------
Créer un fichier requirements.txt :
Flask
requests
feedparser

Puis :
- pip install -r requirements.txt

Service systemd (exemple)
-------------------------
Fichier /etc/systemd/system/radiospot.service (adapter chemins et utilisateur):
[Unit]
Description=Radio Spot Watcher
After=network.target

[Service]
User=youruser
WorkingDirectory=/chemin/vers/le/projet
ExecStart=/usr/bin/python3 /chemin/vers/le/projet/rspot.py
Restart=on-failure
Environment=PORT=8000

[Install]
WantedBy=multi-user.target

puis :
- sudo systemctl daemon-reload
- sudo systemctl enable radiospot
- sudo systemctl start radiospot
- sudo journalctl -u radiospot -f

Notes opérationnelles / dépannage
---------------------------------
- Port déjà utilisé : vérifier que le port configuré (8000) est libre ; change le via la variable PORT.
- Problèmes de connexion au cluster : vérifier host/port, connectivity réseau et firewall.
- RSS : certains flux peuvent refuser des requêtes fréquentes ou block CORS côté client. Le script récupère les flux côté serveur via feedparser.
- CTY : si cty.csv mal formaté, l'appli utilisera le fallback embarqué. Pour de meilleures correspondances, fournis un cty.csv avec colonnes prefix, country, lat, lon, continent.
- Logs : consulte rspot.log pour diagnostic. Si RotatingFileHandler indisponible, les logs seront toujours affichés sur stdout.
- Sauvegarde spots : spots.json est utilisé pour restaurer l'état au redémarrage — si corrompu, supprime-le pour repartir à zéro.

Changelog (v2.85)
-----------------
- Date : 2025-10-28
- Améliorations visuelles et robustesse générale
- Palette configurable et ajout d'une palette "extended" de 10 couleurs
- Bloc Horloges ajouté (UTC + heure locale)
- Charts (canvas renderer maison) maintenus ; palette utilisée en boucle pour colorer les barres
- Charts remontés dans la colonne droite (au-dessus du flux RSS)
- Bloc Most Wanted déplacé en bas de la colonne droite
- Diverses corrections : robustesse parsing cluster, gestion buffer, sauvegarde spots, gestion des threads


Sécurité
--------
- L'application n'implémente pas d'authentification native. Restreindre l'accès via reverse proxy (Nginx), firewall ou VPN si nécessaire.
- Valider l'usage public de l'endpoint export CSV si tu comptes exposer l'interface publiquement.

Contribution
------------
- Pull requests bienvenues. Pour des changements majeurs (ex: réarchitecture, DB), ouvre d'abord une issue pour discussion.
- Tests manuels : vérifier parsing des différentes variantes de lignes "DX", connexions aux flux RSS, changements de palette.

Exemples utilitaires (curl)
---------------------------
- Vérifier statut :
  curl -s http://127.0.0.1:8000/status.json | jq

- Récupérer spots :
  curl -s http://127.0.0.1:8000/spots.json | jq '.spots | length'

- Export CSV :
  wget http://127.0.0.1:8000/export.csv

licence /usage
---------------------------
Projet hobby radio amateur pensé par F1SMV mis en oeuvre par chatgpt5, utilisation personnelle ok, toute redistribution publique doit citer l'auteur et ne pas supprimer les mentions de version.

R