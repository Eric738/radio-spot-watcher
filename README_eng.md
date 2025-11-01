# 📡 Radio Spot Watcher — v2.87 (2025-10-31)

Un moniteur DX Cluster moderne et léger pour radioamateurs. 
A modern and lightweight DX Cluster monitor for ham radio operators.

---

## 📘 Sommaire / Table of Contents
- [🇫🇷 Version Française](#-version-française)
  - [Résumé](#résumé)
  - [Fonctionnalités](#fonctionnalités)
  - [Installation](#installation)
  - [Variables d’environnement](#variables-denvironnement)
  - [Utilisation](#utilisation)
  - [Mise à jour DXCC](#mise-à-jour-dxcc)
  - [Dépannage](#dépannage)
  - [Structure du projet](#structure-du-projet)
  - [Journal des modifications](#journal-des-modifications)
- [🇬🇧 English Version](#-english-version)
  - [Overview](#overview)
  - [Features](#features)
  - [Setup](#setup)
  - [Environment Variables](#environment-variables)
  - [Usage](#usage)
  - [DXCC Auto-Update](#dxcc-auto-update)
  - [Troubleshooting](#troubleshooting)
  - [Project Structure](#project-structure)
  - [Changelog](#changelog)
- [🧭 Licence / License](#-licence--license)

---

## 🇫🇷 Version Française

### Résumé
**Radio Spot Watcher** est une application web permettant de suivre en temps réel les spots DX issus des clusters telnet (ex : DXFun, F5LEN). 
Elle affiche les stations sur une carte du monde, un tableau interactif, des graphiques, et des flux RSS DX-News.

### Fonctionnalités
- Connexion automatique au **cluster DXFun.com (port 8000)**, bascule automatique vers **F5LEN** si nécessaire. 
- Carte interactive mondiale (Leaflet.js) avec positions DX. 
- Tableau des spots en temps réel (bande, mode, DXCC, UTC). 
- Filtres Bande / Mode avec mémorisation. 
- Watchlist (ajout/suppression + surbrillance automatique). 
- Graphiques de trafic (Matplotlib). 
- Flux RSS **DX-World** et **ClubLog** intégrés. 
- Bloc “Most Wanted” avec drapeaux DXCC. 
- Thème clair modernisé et interface responsive. 
- Mise à jour automatique du fichier `dxcc_latest.json` via GitHub. 

---

### Installation
#### Prérequis :
- Python 3.8 ou supérieur 
- Modules requis :
  ```bash
  pip install Flask requests feedparser matplotlib

Installation :

git clone https://github.com/Eric738/radio-spot-watcher.git
cd radio-spot-watcher
python3 -m venv venv && source venv/bin/activate
./start.sh

Puis ouvre ton navigateur :

http://127.0.0.1:8000


---

Variables d’environnement

Variable Description Défaut

PORT Port HTTP 8000
CLUSTER_HOST Hôte du cluster dxfun.com
CLUSTER_PORT Port cluster 8000
CLUSTER_FALLBACK_HOST Cluster de secours f5len.dxcluster.net
CLUSTER_CALLSIGN Indicatif F1SMV
DXCC_FILE Base DXCC locale dxcc_latest.json
RSS_UPDATE_INTERVAL Actualisation RSS 300s
WANTED_UPDATE_INTERVAL Actualisation Most Wanted 600s



---

Utilisation

Depuis le dossier du projet :

python3 src/webapp.py

Endpoints utiles :

/spots.json → liste des spots

/wanted.json → liste “Most Wanted”

/status.json → état du cluster

/rss.json → flux RSS DX

/stats.json → statistiques

/export.csv → export des spots



---

Mise à jour DXCC

Au démarrage :

1. Lecture locale du fichier dxcc_latest.json.


2. Vérification sur GitHub :
https://raw.githubusercontent.com/Eric738/radio-spot-watcher/main/dxcc_latest.json


3. Mise à jour automatique si une version plus récente est disponible.


4. Log :

[DXCC] Mise à jour réussie (340 entités)




---

Dépannage

Aucun spot affiché :

ping dxfun.com
telnet dxfun.com 8000

DXCC manquant :

touch src/dxcc_latest.json

Port occupé :

export PORT=8080



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

Ajout : mise à jour DXCC automatique depuis GitHub

Amélioration : affichage des spots et performances

Correction : flux RSS / persistance spots

Préparation : palette de 10 couleurs utilisateur



---

🇬🇧 English Version

Overview

Radio Spot Watcher is a modern web app for real-time DX Cluster monitoring.
It displays DX spots on a world map, with statistics, RSS feeds, and watchlist tracking.

Features

Auto-connects to DXFun.com (port 8000) with fallback to F5LEN.

Interactive world map (Leaflet.js).

Real-time spot table with band/mode filters.

Watchlist (add/remove + highlight).

Traffic charts (Matplotlib).

Built-in DX-World & ClubLog RSS feeds.

“Most Wanted” block with DXCC flags.

Light modern UI, responsive layout.

Automatic DXCC database sync (dxcc_latest.json).



---

Setup

git clone https://github.com/Eric738/radio-spot-watcher.git
cd radio-spot-watcher
python3 -m venv venv && source venv/bin/activate
pip install Flask requests feedparser matplotlib
./start.sh

Access the interface:

http://127.0.0.1:8000


---

Environment Variables

Variable Description Default

PORT Web server port 8000
CLUSTER_HOST Cluster host dxfun.com
CLUSTER_PORT Cluster port 8000
CLUSTER_FALLBACK_HOST Fallback cluster f5len.dxcluster.net
CLUSTER_CALLSIGN Callsign used F1SMV
DXCC_FILE Local DXCC file dxcc_latest.json
RSS_UPDATE_INTERVAL RSS refresh 300
WANTED_UPDATE_INTERVAL Most Wanted refresh 600



---

Usage

Run the app:

python3 src/webapp.py

Useful endpoints:

/spots.json → list of DX spots

/wanted.json → “Most Wanted” list

/status.json → app & cluster status

/rss.json → RSS feeds

/stats.json → charts

/export.csv → CSV export



---

DXCC Auto-Update

At startup:

1. Loads local dxcc_latest.json.


2. Checks latest version on GitHub:
https://raw.githubusercontent.com/Eric738/radio-spot-watcher/main/dxcc_latest.json


3. Updates if newer version found.


4. Log example:

[DXCC] Updated successfully (340 entities)




---

Troubleshooting

No spots displayed:

ping dxfun.com
telnet dxfun.com 8000

DXCC missing:

touch src/dxcc_latest.json

Port busy:

export PORT=8080



---

Project Structure

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

Changelog — v2.87

Added: Automatic DXCC sync from GitHub

Improved: Spot rendering, UI responsiveness

Fixed: RSS refresh & spot persistence

Prepared: User color palette (10 tones)



---

🧭 Licence / License

Projet / Project : Radio Spot Watcher
Auteur / Author : F1SMV (Eric738)
Assistance technique : ChatGPT-5 (OpenAI)
Licence / License : MIT

Libre pour usage personnel et éducatif.
Free for personal and educational use.

---

✅ Copie **l’intégralité** de ce bloc (de `# 📡 Radio Spot Watcher…` jusqu’à la fin). 
✅ Colle-le dans GitHub sous le nom : `README.md`. 
✅ Commit : `Add bilingual README for v2.87`.