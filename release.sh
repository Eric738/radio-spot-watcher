#!/bin/bash
# ===========================================================
# Script : release.sh
# Objet  : Créer, taguer et pousser une nouvelle version du projet Radio Spot Watcher
# Auteur : Eric738 (automatisé par ChatGPT)
# ===========================================================

# Vérifie la présence d’un numéro de version
if [ -z "$1" ]; then
  echo "❌  Usage : ./release.sh <version>"
  echo "Exemple : ./release.sh 2.87"
  exit 1
fi

VERSION="$1"
BRANCH="main"
MESSAGE="Stable release v$VERSION ($(date +%Y-%m-%d))"

echo "------------------------------------------------------------"
echo "📦  Préparation de la version $VERSION"
echo "------------------------------------------------------------"

# S'assure d'être dans le bon dossier
cd "$(dirname "$0")" || exit 1

# Vérifie qu'on est sur la bonne branche
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
  echo "🔁  Passage sur la branche $BRANCH"
  git checkout "$BRANCH"
fi

# Synchronisation avec GitHub
echo "⬇️  Synchronisation avec la version distante..."
git pull origin "$BRANCH" --rebase

# Commit automatique
echo "📝  Validation du code..."
git add .
git commit -m "$MESSAGE"

# Tagging
echo "🏷️  Création du tag v$VERSION..."
git tag -a "v$VERSION" -m "$MESSAGE"

# Push du code + du tag
echo "🚀  Envoi vers GitHub..."
git push origin "$BRANCH"
git push origin "v$VERSION"

echo "✅  Version $VERSION publiée avec succès !"
echo "💡  Vérifie sur : https://github.com/Eric738/radio-spot-watcher/releases" 