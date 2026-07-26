#!/usr/bin/env bash
# Installe Iris sur une machine neuve : binaires système, venv, PyTorch adapté
# au GPU présent, dépendances Python.
#
#   ./setup.sh              # détecte le GPU tout seul
#   ./setup.sh --cpu        # force le mode processeur
#   ./setup.sh --rocm       # force AMD (si la détection se trompe)
#   ./setup.sh --cuda
set -euo pipefail
cd "$(dirname "$0")"

FORCE="${1:-}"
PY="${PYTHON:-python3.12}"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# ── Python ──────────────────────────────────────────────────────────────────
command -v "$PY" >/dev/null || {
  echo "✗ $PY introuvable. Installe-le (les roues ROCm officielles exigent 3.12)," >&2
  echo "  ou lance : PYTHON=python3 ./setup.sh" >&2
  exit 1
}

# ── Binaires système ────────────────────────────────────────────────────────
# Iris s'en sert pour l'export des livres et des zines. Sans eux le tri marche,
# mais l'impression casse au moment où on en a besoin — donc on prévient avant.
say "→ Binaires système"
MISSING=()
command -v gs       >/dev/null || MISSING+=("ghostscript — séparation CMJN")
command -v pdfinfo  >/dev/null || MISSING+=("poppler-utils — contrôle des PDF")
command -v google-chrome >/dev/null || command -v chromium >/dev/null || \
  command -v chromium-browser >/dev/null || command -v brave-browser >/dev/null || \
  MISSING+=("chromium — rendu PDF des livres")
[ -f /usr/share/color/icc/colord/FOGRA39L_coated.icc ] || \
  MISSING+=("colord-data — profil ICC Fogra 39")

if [ ${#MISSING[@]} -gt 0 ]; then
  printf '    · %s\n' "${MISSING[@]}"
  echo
  echo "  Sur Debian/Ubuntu :"
  echo "    sudo apt install ghostscript poppler-utils chromium-browser colord-data"
  echo
  read -rp "  Continuer sans ? (le tri marchera, pas l'export) [o/N] " a
  [ "$a" = "o" ] || exit 1
else
  echo "  ✓ tous présents"
fi

# ── Détection du GPU ────────────────────────────────────────────────────────
say "→ GPU"
case "$FORCE" in
  --cpu)  KIND=cpu ;;
  --rocm) KIND=rocm ;;
  --cuda) KIND=cuda ;;
  *)
    if command -v nvidia-smi >/dev/null && nvidia-smi -L 2>/dev/null | grep -q GPU; then
      KIND=cuda
    elif command -v rocminfo >/dev/null 2>&1 || [ -e /dev/kfd ]; then
      KIND=rocm
    else
      KIND=cpu
    fi ;;
esac

case "$KIND" in
  cuda) INDEX="https://download.pytorch.org/whl/cu124"
        echo "  NVIDIA détecté → PyTorch CUDA 12.4" ;;
  rocm) INDEX="https://repo.amd.com/rocm/whl-multi-arch/"
        echo "  AMD détecté → PyTorch ROCm (roues AMD, Python 3.12 requis)" ;;
  cpu)  INDEX="https://download.pytorch.org/whl/cpu"
        echo "  Aucun GPU détecté → PyTorch CPU (fonctionnel mais lent)" ;;
esac

# ── Environnement Python ────────────────────────────────────────────────────
say "→ Environnement virtuel"
[ -d venv ] || "$PY" -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip

say "→ PyTorch ($KIND)"
pip install torch torchvision --index-url "$INDEX"

say "→ Dépendances Iris"
pip install -r requirements.txt

# ── Vérification ────────────────────────────────────────────────────────────
say "→ Vérification"
python - <<'EOF'
import torch
gpu = torch.cuda.is_available()      # vrai aussi sur ROCm : l'API reste "cuda"
print(f"  torch {torch.__version__}")
print(f"  GPU utilisable : {gpu}" + (f" — {torch.cuda.get_device_name(0)}" if gpu else ""))
if not gpu:
    print("  (Iris fonctionnera sur processeur : correct, mais lent.)")
EOF

say "✓ Installation terminée"
cat <<'EOF'
  Lancer                  :  ./run.sh     puis http://<ip>:8800
  Installer en service    :  adapter iris.service puis le copier dans /etc/systemd/system/
  Mise à jour automatique :  ./install-autoupdate.sh

  Les modèles (~10 Go : CLIP, Qwen2-VL, YOLO) se téléchargent au premier usage.
EOF
