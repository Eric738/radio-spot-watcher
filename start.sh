#!/bin/bash
# Lancement manuel de Radio Spot Watcher

APP_DIR="$HOME/radio-spot-watcher"
cd "$APP_DIR" || exit 1

echo "👉 Activation de l'environnement virtuel"
source venv/bin/activate

echo "👉 Vérification si le port 8000 est occupé..."
PID=$(lsof -ti:8000)
if [ -n "$PID" ]; then
  echo "⚠️  Port 8000 occupé par PID=$PID, on arrête le process..."
  kill -9 $PID
fi

echo "🚀 Démarrage de Radio Spot Watcher..."
python3 src/webapp.py
