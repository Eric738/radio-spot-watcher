# 📡 Radio Spot Watcher

Radio Spot Watcher est une application **Flask** qui se connecte à un **DX Cluster** (via Telnet) et affiche en temps réel les spots radio amateurs sous forme de tableau interactif et de graphiques.

Pensée pour tourner sur **Raspberry Pi** ou serveur Linux, elle permet aux radioamateurs de suivre l’activité DX mondiale, d’appliquer des filtres et de personnaliser leur expérience.

---

## 🚀 Fonctionnalités principales

- 🔌 **Connexion DX Cluster** via Telnet (cluster principal + backup).
- 📰 **Deux flux RSS DX** affichés dans la colonne de droite (DX-World & HamRadioDeals par défaut).
- 📊 **Graphiques temps réel** des bandes actives :
  - Histogramme (bar chart).
  - Camembert (pie chart).
- 🔍 **Watchlist** : ajout/suppression d’indicatifs à surveiller.
- 🎨 **Design moderne** : tableau zébré, mode sombre/clair, couleurs par bande.
- 📈 **Statistiques en direct** :
  - Total de spots reçus.
  - Uptime en minutes.
  - Top 5 pays DXCC les plus entendus.
- ⏱️ **Reset automatique des spots** (toutes les 3h par défaut, configurable).
- 🔄 **Mise à jour automatique de cty.csv** (tous les 7 jours par défaut).
- 🖥️ **Interface responsive** : utilisable sur PC comme sur mobile.

---

## 📦 Installation

### 1. Cloner le dépôt
```bash
git clone https://github.com/<ton_user>/radio-spot-watcher.git
cd radio-spot-watcher

créer un environnement virtuel Python
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

et lancer l'application en manuel dans le repertoire radio/spot/watcher
python3 src/webapp.py

avec systemd

sudo systemctl start radio-spot-watcher
sudo systemctl enable radio-spot-watcher

configuration config/settings.json
remplacer "NOCALL" par votre call











