#!/usr/bin/env bash
# Déploiement sur la machine GPU : récupère la dernière version et redémarre le service.
# À lancer sur Roblab :  ./deploy.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "→ git pull"
git pull --ff-only

# Réinstalle les dépendances si requirements.txt a changé dans ce pull.
if git diff --name-only HEAD@{1} HEAD 2>/dev/null | grep -q '^requirements.txt$'; then
  echo "→ requirements.txt modifié : mise à jour des dépendances"
  source venv/bin/activate
  TMPDIR=/mnt/tmp-large/pip-tmp pip install -r requirements.txt
fi

echo "→ redémarrage du service iris"
sudo systemctl restart iris
sleep 2
systemctl is-active iris
echo "✓ déployé"
