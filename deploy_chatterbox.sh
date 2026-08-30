#!/bin/bash
set -e

HOST="root@chatterbox"
TARGET_DIR="/opt/gustav"

echo "====================================================================="
echo "  🚀 Déploiement de Gustav sur chatterbox ($HOST)"
echo "====================================================================="
echo

echo "[1/4] Création du dossier cible sur chatterbox..."
ssh "$HOST" "mkdir -p $TARGET_DIR/data $TARGET_DIR/static $TARGET_DIR/extension"

echo "[2/4] Copie des fichiers d'application et de données..."
scp -r app.py tube_calculator.py medical_dictionary.py requisition_filler.py label_generator.py profiles_manager.py clinics_manager.py requirements.txt gustav.service "$HOST:$TARGET_DIR/"
scp -r data/* "$HOST:$TARGET_DIR/data/"
scp -r static/* "$HOST:$TARGET_DIR/static/"
scp -r extension/* "$HOST:$TARGET_DIR/extension/"

echo "[3/4] Configuration de l'environnement Python et des dépendances..."
ssh "$HOST" "
    if [ ! -d '$TARGET_DIR/venv' ]; then
        python3 -m venv '$TARGET_DIR/venv'
    fi
    $TARGET_DIR/venv/bin/pip install --upgrade pip
    $TARGET_DIR/venv/bin/pip install -r $TARGET_DIR/requirements.txt
"

echo "[4/4] Installation et démarrage du service daemon systemd..."
ssh "$HOST" "
    cp $TARGET_DIR/gustav.service /etc/systemd/system/gustav.service
    systemctl daemon-reload
    systemctl enable gustav.service
    systemctl restart gustav.service
    systemctl status gustav.service --no-pager
"

echo
echo "====================================================================="
echo "  ✅ Déploiement terminé avec succès !"
echo "  🌐 L'application est active sur : http://chatterbox:8000"
echo "====================================================================="
