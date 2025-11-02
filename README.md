# 📡 Radio Spot Watcher v2.91 – Stable (2025-11-02)

### 🛰️ Description
**Radio Spot Watcher** est une application web Flask pour visualiser en temps réel les **spots DX** des clusters radioamateurs (ex: `dxfun.com`). 
Interface moderne, responsive, et 100% compatible Raspberry Pi / Debian 12.

---

### ⚙️ Fonctionnalités principales
- Connexion automatique à **dxfun.com:8000**
- Affichage temps réel des **spots DX**
- **DXCC local** depuis `cty.csv` → conversion automatique vers `dxcc_latest.json`
- Interface claire (mode clair, couleurs personnalisables)
- Carte interactive, horloges UTC/local, export CSV
- Watchlist dynamique + gestion des “Most Wanted DXCC”
- Journalisation (`rspot.log`) des préfixes inconnus
- Aucune dépendance réseau externe (DXCC offline)

---

### 🚀 Installation rapide
```bash
git clone https://github.com/Eric738/radio-spot-watcher.git
cd radio-spot-watcher
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
./start.sh

Serveur disponible sur :
👉 http://127.0.0.1:8000


---

📁 Arborescence

radio-spot-watcher/
│
├── data/
│   ├── spots_cache.json
│   └── dxcc_latest.json
│
├── src/
│   ├── webapp.py
│   ├── cty.csv
│   └── static/
│
├── logs/rspot.log
├── start.sh
└── requirements.txt


---

📘 Fichier DXCC local

Le fichier src/cty.csv contient les préfixes DXCC :

Prefix,Country,Continent,Latitude,Longitude
F,France,EU,48.0,2.4
EA,Spain,EU,40.4,-3.7
9J,Zambia,AF,-15.4,28.3

🔄 Converti automatiquement en data/dxcc_latest.json au démarrage.
Tu peux enrichir ou corriger le CSV à tout moment.


---

🧩 Dépannage rapide

Problème Cause Solution

DXCC: Unknown Préfixe absent du CSV Ajouter le préfixe
MAJ en ligne échouée Fichier GitHub désactivé Normal depuis 2.89
Port 8000 occupé Processus déjà actif sudo fuser -k 8000/tcp



---

🧾 Versions

Version Date Points clés

2.87 2025-10-31 Nouvelles couleurs
2.89 2025-11-02 DXCC via cty.csv
2.90 2025-11-02 Conversion CSV→JSON
2.91 2025-11-02 288 entrées DXCC, version stable



---

🇬🇧 English Summary

Radio Spot Watcher v2.91 – A lightweight Flask-based DX Cluster monitor for radio amateurs.

288 DXCC entries (local cty.csv)

Automatic CSV → JSON conversion

Offline DXCC resolution

Clean web interface


Run:

./start.sh

Visit: http://127.0.0.1:8000


---

📍 Author: pensé par F1SMV réalisé par chatgpt5
📅 2025 – License: MIT