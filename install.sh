#!/bin/bash
# Installation et configuration de Radio Spot Watcher

APP_DIR="/home/eric/radio-spot-watcher"
VENV_DIR="$APP_DIR/venv"

echo "Mise à jour du système"
sudo apt update && sudo apt install -y python3-venv python3-pip telnet net-tools unzip

echo "Création de l'environnement virtuel"
python3 -m venv $VENV_DIR

echo "Activation du venv et installation des dépendances"
source $VENV_DIR/bin/activate
pip install --upgrade pip
pip install --force-reinstall -r $APP_DIR/requirements.txt

echo "Copie du service systemd"
sudo cp $APP_DIR/radio-spot-watcher.service /etc/systemd/system/

echo "Reload systemd"
sudo systemctl daemon-reload
sudo systemctl enable radio-spot-watcher

echo "Installation terminée"
echo "Démarrer avec: sudo systemctl start radio-spot-watcher"
echo "Voir les logs avec: journalctl -u radio-spot-watcher -f"
