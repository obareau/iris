# Iris — image CPU.
#
# Pourquoi CPU et pas GPU : une image ne peut pas embarquer les trois roues
# PyTorch (CUDA, ROCm, CPU) — il faudrait trois images de 6 à 10 Go. Or qui a un
# GPU a une machine équipée, et ./setup.sh gère déjà les trois cas. Cette image
# sert le besoin réel : essayer Iris sans rien installer.
#
#   docker run -p 8800:8800 \
#     -v ~/Photos:/photos \
#     -v iris-data:/app/data \
#     -v iris-models:/root/.cache/huggingface \
#     ghcr.io/obareau/iris
#
# ⚠️ Les modèles (~10 Go) se téléchargent au premier usage. Monter un volume sur
# le cache HuggingFace évite de tout re-télécharger à chaque conteneur.

FROM python:3.12-slim

# Binaires système : ghostscript et poppler pour la chaîne prépresse, chromium
# pour rendre les livres en PDF, colord-data pour le profil Fogra 39. Sans eux
# le tri marche mais l'export casse — autant les avoir dans l'image.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ghostscript \
      poppler-utils \
      chromium \
      colord-data \
      libgl1 \
      libglib2.0-0 \
      git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# PyTorch CPU d'abord, dans sa propre couche : c'est le plus gros morceau et il
# ne bouge presque jamais, donc il reste en cache quand le code change.
COPY requirements.txt .
RUN pip install --no-cache-dir torch torchvision \
      --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

# Chromium s'appelle « chromium » sur Debian ; le code cherche aussi
# google-chrome. On lui donne le nom qu'il attend.
RUN ln -sf /usr/bin/chromium /usr/local/bin/chromium-browser

# Sans .git dans l'image, la version affichée n'aurait aucun build à montrer :
# on grave le sha au moment de la construction.
ARG IRIS_BUILD=docker
ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/root/.cache/huggingface \
    IRIS_BUILD=${IRIS_BUILD}

EXPOSE 8800
VOLUME ["/app/data", "/app/exports", "/root/.cache/huggingface"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8800/api/version',timeout=4)" || exit 1

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8800"]
