
#!/bin/bash
# ===============================================================
#  🚀 Radio Spot Watcher - Script d'installation automatique
# ===============================================================

set -e  # stoppe le script en cas d’erreur

# -------------------------
# 📂 Variables principales
# -------------------------
APP_NAME="radio-spot-watcher"
APP_DIR="$HOME/$APP_NAME"
VENV_DIR="$APP_DIR/venv"
SERVICE_FILE="/etc/systemd/system/$APP_NAME.service"

# -------------------------
# 🧰 Vérifications préliminaires
# -------------------------
echo "👉 Vérification des dépendances système..."

sudo apt update -y
sudo apt install -y python3 python3-venv python3-pip git curl

# -------------------------
# 🪄 Installation du projet
# -------------------------
echo "📦 Installation dans : $APP_DIR"

if [ ! -d "$APP_DIR" ]; then
  echo "📂 Clonage du dépôt Git..."
  git clone https://github.com/Eric738/radio-spot-watcher.git "$APP_DIR"
else
  echo "🔄 Mise à jour du dépôt existant..."
  cd "$APP_DIR"
  git pull --rebase
fi

cd "$APP_DIR"

# -------------------------
# 🧬 Environnement virtuel Python
# -------------------------
echo "🐍 Création / activation de l'environnement virtuel..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "📜 Installation des dépendances Python..."
pip install --upgrade pip
pip install -r requirements.txt

# -------------------------
# ⚙️ Création du service systemd
# -------------------------
echo "⚙️ Configuration du service systemd..."

sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=Radio Spot Watcher
After=network.target

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$VENV_DIR/bin/python3 $APP_DIR/src/webapp.py
Restart=always
User=$USER
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# -------------------------
# 🚀 Activation du service
# -------------------------
echo "🔄 Activation du service $APP_NAME..."
sudo systemctl daemon-reexec
sudo systemctl daemon-reload
sudo systemctl enable $APP_NAME
sudo systemctl restart $APP_NAME

# -------------------------
# ✅ Vérification
# -------------------------
echo "✅ Installation terminée !"
echo "🌐 L'application est maintenant accessible sur : http://$(hostname -I | awk '{print $1}'):8000"
echo "🔎 Pour voir les logs : sudo journalctl -u $APP_NAME -f" 