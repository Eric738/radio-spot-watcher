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