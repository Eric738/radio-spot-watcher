# 📡 Radio Spot Watcher  

**Radio Spot Watcher** est une application web moderne de suivi des spots DX radioamateurs en temps réel.  
Elle se connecte à un cluster DX, affiche les spots sous forme de tableau dynamique et de graphiques,  
et inclut des outils d’analyse DXCC, propagation, et activité mondiale.

---

## 🚀 Fonctionnalités principales  

| Catégorie | Description |
|------------|--------------|
| 🔗 **Connexion DXCluster** | Connexion automatique à `dxcluster.f5len.org` (ou serveur de secours). |
| 📊 **Tableau de bord dynamique** | Graphiques (bande / mode) mis à jour en direct avec Chart.js. |
| 🧭 **Filtres interactifs** | Filtrage simultané par **bande** et **mode**. |
| 👀 **Watchlist personnelle** | Ajout / suppression d’indicatifs suivis, surbrillance automatique dans la liste. |
| 🌍 **DXCC intégrés** | Fichier `cty.csv` téléchargé et mis à jour automatiquement (avec pastille d’état). |
| ☀️ **Conditions de propagation** | Indices SFI, Kp et Sunspots via API HamQSL. |
| 💡 **Most Wanted DXCC** | Liste ClubLog Top 50 + pavé “Most Wanted entendus (3 h)” à effet néon rétro. |
| 📰 **Flux RSS DX** | DX-World et OnAllBands (fallback ARRL). |
| 📈 **Statistiques DXCC** | DXCC chargés, latence cluster, entités entendues aujourd’hui. |
| 🧠 **Détection intelligente de mode** | Analyse du texte et de la fréquence pour déterminer le mode (FT8, CW, SSB…). |
| 🔄 **Mise à jour DXCC** | Téléchargement automatique depuis country-files.com avec contrôle de validité. |

---

## 🧰 Installation (Linux / Raspberry Pi)

### 1️⃣ Cloner et installer
```bash
cd ~
git clone https://github.com/Eric738/radio-spot-watcher.git
cd radio-spot-watcher
chmod +x install.sh
./install.sh
```

Le script :
- crée un environnement virtuel Python (`venv`),  
- installe les dépendances (`requirements.txt`),  
- configure un service `systemd`,  
- et démarre automatiquement l’application sur le port **8000**.

---

## 🌐 Accès à l’application
Ouvre ton navigateur à l’adresse :
```
http://<adresse_IP_locale>:8000
```
> Exemple : http://192.168.1.50:8000

---

## ⚙️ Commandes utiles

| Action | Commande |
|--------|-----------|
| 🔄 Redémarrer le service | `sudo systemctl restart radio-spot-watcher` |
| 📋 État du service | `sudo systemctl status radio-spot-watcher` |
| 📜 Logs en direct | `sudo journalctl -u radio-spot-watcher -f` |
| ⏹️ Stopper l’application | `sudo systemctl stop radio-spot-watcher` |

---

## 🗂️ Structure du projet

```
radio-spot-watcher/
│
├── src/
│   ├── webapp.py          # Application Flask principale
│   ├── update_cty.py      # Mise à jour automatique du fichier DXCC
│   ├── cluster_client.py  # Module réseau (héritage)
│   ├── notifier.py        # Notifications futures
│   ├── config.py          # Paramètres du cluster et API
│   └── cty.csv            # Base DXCC locale (auto-téléchargée)
│
├── install.sh             # Script d’installation automatisée
├── requirements.txt       # Dépendances Python
├── README.md              # Documentation (ce fichier)
└── LICENSE
```

---

## 📡 Fonctionnement du cluster
- Connexion directe au **DXCluster F5LEN**, avec bascule automatique en cas d’échec.  
- Spots reçus traités et conservés 5 minutes.  
- Les entités DXCC rares (Most Wanted) sont identifiées et affichées séparément.

---

## ☀️ Données de propagation
Les indices **SFI**, **Kp-index** et **Sunspots** sont actualisés toutes les 3 heures via l’API HamQSL.  
En cas d’échec, les champs affichent “—” et une tentative de mise à jour ultérieure est effectuée.

---

## 🧩 Personnalisation
Tu peux modifier :
- le **cluster** dans `webapp.py` (`DEFAULT_CLUSTER`),  
- ton **indicatif radio** (remplace `"F1SMV"`),  
- les **flux RSS** (`RSS_URL1`, `RSS_URL2`),  
- la **durée de conservation des spots** (5 min par défaut).

---

## 🧠 Roadmap à venir
- 🌐 Carte mondiale des spots (heatmap interactive).  
- ☀️ Pavé propagation enrichi (fallback NOAA + couleurs dynamiques).  
- 🧭 Filtrage DXCC + bande combiné.  
- 📬 Notifications en temps réel (WebSocket).  
- 📊 Historique et export CSV.

---

## 👤 Crédits
Développé par **F1SMV (Eric)**  
Interface et améliorations inspirées des tableaux de bord DX modernes (ClubLog, DXHeat).  
Design responsive et clair pour une utilisation sur PC, tablette ou mobile.
