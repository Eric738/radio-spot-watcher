#!/bin/bash
# ============================================================
#  Script : sync_force.sh
#  Auteur : Eric738
#  Objet  : Synchronisation automatique du dépôt GitHub
#  Fonction :
#     - Nettoie les fichiers inutiles
#     - Détecte la version dans webapp.py
#     - Crée une sauvegarde locale
#     - Commit et push forcé vers GitHub
# ============================================================

set -e  # Stoppe le script à la moindre erreur

# --- Nettoyage des fichiers inutiles ---
echo "🧹 Nettoyage des fichiers temporaires et logs..."
rm -f rspot.log *.bak *.tmp
find . -type d -name "__pycache__" -exec rm -rf {} +

# --- Détection automatique de la version ---
VERSION=$(grep -Eo 'v[0-9]+\.[0-9]+' webapp.py | tail -1)

if [ -z "$VERSION" ]; then
    echo "⚠️  Version introuvable dans webapp.py. Utilisation de 'vX.Y'."
    VERSION="vX.Y"
else
    echo "📦 Version détectée : $VERSION"
fi

# --- Création d’une branche de sauvegarde ---
BRANCH_NAME="backup-avant-push-$(date +%Y%m%d-%H%M%S)"
echo "🔹 Création de la sauvegarde locale : $BRANCH_NAME"
git branch "$BRANCH_NAME"

# --- Indexation des fichiers ---
echo "🔹 Ajout des fichiers modifiés..."
git add .

# --- Commit automatique ---
echo "🔹 Création du commit local : $VERSION auto-sync"
git commit -m "$VERSION auto-sync" || echo "ℹ️ Aucun changement à valider."

# --- Récupération du dépôt distant ---
echo "🔹 Synchronisation avec le dépôt distant..."
git fetch origin

# --- Push forcé vers GitHub ---
echo "🚀 Envoi de la version $VERSION vers GitHub..."
git push origin main --force

# --- Vérification du succès ---
if [ $? -eq 0 ]; then
    echo "✅ Synchronisation réussie !"
    echo "🔗 Version $VERSION disponible sur :"
    echo "   https://github.com/Eric738/radio-spot-watcher"
else
    echo "❌ Échec de la synchronisation. Vérifie ton dépôt distant."
fi 