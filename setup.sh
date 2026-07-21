#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt

echo "Installation terminée. Lance ensuite ./run.sh"
