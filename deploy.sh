#!/usr/bin/env bash
# Met à jour Iris : récupère la dernière version, réinstalle ce qui a bougé,
# redémarre le service. Utilisable sur n'importe quelle machine — c'est aussi ce
# que lance le bouton de mise à jour de l'interface.
#
#   ./deploy.sh
set -euo pipefail
cd "$(dirname "$0")"

SERVICE="${IRIS_SERVICE:-iris}"

echo "→ git pull"
git pull --ff-only

# Réinstalle les dépendances seulement si requirements.txt a changé dans ce pull.
if git diff --name-only HEAD@{1} HEAD 2>/dev/null | grep -q '^requirements.txt$'; then
  echo "→ requirements.txt modifié : mise à jour des dépendances"
  source venv/bin/activate
  # Un gros disque dédié au temporaire s'il existe (pip décompresse torch, qui
  # pèse plusieurs Go) — sinon on laisse le système décider. Ce chemin est
  # propre à Roblab : le forcer ailleurs faisait échouer l'installation.
  if [ -d /mnt/tmp-large/pip-tmp ]; then
    TMPDIR=/mnt/tmp-large/pip-tmp pip install -r requirements.txt
  else
    pip install -r requirements.txt
  fi
fi

# Le redémarrage demande les droits. En interactif on peut taper son mot de
# passe ; lancé depuis l'interface (donc sans terminal), il FAUT que sudo passe
# sans mot de passe — sinon le script resterait bloqué sans que personne le voie.
echo "→ redémarrage du service $SERVICE"
if sudo -n true 2>/dev/null; then
  sudo systemctl restart "$SERVICE"
elif [ -t 0 ]; then
  sudo systemctl restart "$SERVICE"
else
  echo "✗ sudo demande un mot de passe et personne ne peut le taper." >&2
  echo "  Le code est à jour, mais le service tourne encore sur l'ancienne version." >&2
  echo "  Redémarre-le à la main :  sudo systemctl restart $SERVICE" >&2
  echo "  Ou autorise ce seul redémarrage sans mot de passe :" >&2
  echo "    echo \"\$USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart $SERVICE\" | sudo tee /etc/sudoers.d/iris-restart" >&2
  exit 1
fi

sleep 2
systemctl is-active "$SERVICE"
echo "✓ déployé"
