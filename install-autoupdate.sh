#!/usr/bin/env bash
# Installe la mise à jour automatique d'Iris (timer systemd, chaque nuit).
#
#   ./install-autoupdate.sh            # installe et active
#   ./install-autoupdate.sh --remove   # désinstalle
#
# ⚠️ À réserver aux machines où PERSONNE ne modifie le code sur place. Sur une
# machine de développement, un pull automatique en pleine session écraserait du
# travail — c'est exactement ce que cette automatisation ne doit pas faire.
set -euo pipefail
cd "$(dirname "$0")"
DIR="$(pwd)"
USER_NAME="$(id -un)"
SERVICE="${IRIS_SERVICE:-iris}"
UNIT_DIR=/etc/systemd/system

if [ "${1:-}" = "--remove" ]; then
  sudo systemctl disable --now iris-autoupdate.timer 2>/dev/null || true
  sudo rm -f "$UNIT_DIR/iris-autoupdate.timer" "$UNIT_DIR/iris-autoupdate.service"
  sudo systemctl daemon-reload
  echo "✓ mise à jour automatique désinstallée"
  exit 0
fi

# ── Garde-fous : mieux vaut refuser que d'installer quelque chose de cassé ──
[ -d .git ] || { echo "✗ $DIR n'est pas un dépôt git." >&2; exit 1; }
[ -x deploy.sh ] || chmod +x deploy.sh

if [ -n "$(git status --porcelain)" ]; then
  echo "✗ Des modifications locales traînent dans $DIR." >&2
  echo "  Une mise à jour automatique refuserait de s'appliquer chaque nuit." >&2
  echo "  Nettoie d'abord (git status), ou n'installe pas ce timer ici." >&2
  exit 1
fi

if ! sudo -n true 2>/dev/null; then
  echo "⚠ sudo demande un mot de passe."
  echo "  Le timer tourne sans personne devant l'écran : il ne pourra pas"
  echo "  redémarrer le service. Autorise ce seul redémarrage :"
  echo
  echo "    echo \"$USER_NAME ALL=(root) NOPASSWD: /usr/bin/systemctl restart $SERVICE\" | sudo tee /etc/sudoers.d/iris-restart"
  echo
  read -rp "  Continuer quand même ? [o/N] " a
  [ "$a" = "o" ] || exit 1
fi

# ── Installation ────────────────────────────────────────────────────────────
sed -e "s|__USER__|$USER_NAME|g" -e "s|__DIR__|$DIR|g" \
    iris-autoupdate.service | sudo tee "$UNIT_DIR/iris-autoupdate.service" >/dev/null
sudo cp iris-autoupdate.timer "$UNIT_DIR/iris-autoupdate.timer"
sudo systemctl daemon-reload
sudo systemctl enable --now iris-autoupdate.timer

echo "✓ mise à jour automatique installée pour $USER_NAME dans $DIR"
echo
systemctl list-timers iris-autoupdate.timer --no-pager | head -3
echo
echo "  Forcer une mise à jour maintenant :  sudo systemctl start iris-autoupdate"
echo "  Voir ce qui s'est passé            :  journalctl -u iris-autoupdate -n 30"
echo "  Désinstaller                       :  ./install-autoupdate.sh --remove"
