📡 Radio Spot Watcher — v2.7.1 stable
============================================================
Suivi temps réel des spots DX cluster + carte DXCC + statistiques
============================================================

⚙️ Fonctionnalités principales
------------------------------
- Connexion automatique au cluster F5LEN (dxcluster.f5len.org:7373)
- Carte mondiale interactive (Leaflet) avec repérage des spots récents
  🔴 Rouge clignotant = Most Wanted ou Watchlist
  🟢 Vert = spot standard
- Watchlist personnalisable (ajout / suppression directe depuis l’interface)
- Liens QRZ.com cliquables depuis le tableau des spots
- Graphiques colorés : répartition par bande et par mode (Chart.js)
- Flux RSS : DX-World + OnAllBands / ARRL
- Mise à jour DXCC automatique (fichier CTY CSV)
- Statistiques de cluster (compteur de spots, connexion, dernière MAJ)
- Mode simulation intégrée (spots aléatoires si cluster hors ligne)

🧩 Installation
------------------------------
À placer dans /home/eric/radio-spot-watcher/src/

1. Assure-toi que Flask et les dépendances sont installées :
   pip install flask requests feedparser chartjs

2. Rends le script exécutable :
   chmod +x webapp.py start.sh

3. Démarre le programme :
   ./start.sh

4. Ouvre ton navigateur sur :
   http://localhost:8000

🖥️ Interface Web
------------------------------
- Barre supérieure :
  état cluster, compteur spots, dernière MAJ, indices solaires
- Zone gauche : carte mondiale + graphiques
- Zone droite : tableau temps réel des spots + flux RSS + Most Wanted
- Watchlist : ajout/suppression directe via le web

🔧 Maintenance
------------------------------
- Nettoyage automatique des spots de plus de 15 minutes
- Mise à jour DXCC via bouton “Mettre à jour DXCC”
- Flux RSS & Most Wanted mis à jour automatiquement
- Compteur console toutes les 5 minutes

🗺️ À venir (v2.7.2 / 2.8)
------------------------------
- Drapeaux DXCC à côté des Most Wanted
- Affichage dynamique des indices solaires (SFI / Kp / Sunspots)
- Alertes sonores Watchlist / Most Wanted
- Export CSV ou base SQLite

👤 Auteur
------------------------------
Projet : Radio Spot Watcher v2.5 → v2.7.1 stable
Adaptation et maintenance : Eric (F1SMV)
Assistance : ChatGPT-GPT-5
Dernière mise à jour : 2025-10-10
