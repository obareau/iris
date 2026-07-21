# 🌈 Iris

Application web locale de **tri, classement et renommage automatique d'images** par contenu, pensée pour traiter de gros volumes rapidement sur GPU.

Interface façon Lightroom (3 panneaux, thème clair), calcul déporté sur une machine GPU, affichage dans n'importe quel navigateur du réseau.

## Pipeline

L'analyse se fait en 3 passes cumulatives et indépendantes :

1. **Analyse (passe 1)** — classement par catégorie
   - **YOLOv8n** : pré-filtre rapide, résout instantanément les images à objet dominant (personne, animal, objet).
   - **CLIP** (zero-shot) : prend le relais pour les images ambiguës (typiquement les paysages).
   - Détection **couleur** (N&B / Couleur) et **format** (Paysage / Portrait) déterministe, sans IA.
2. **Détails (passe 2)** — mots-clés descriptifs par image via le VLM **Qwen2-VL-2B** (cheveux/tatouages, architecture, type de machine…), intégrés au nom de fichier.
3. **Affiner (passe 3)** — attributs structurés par catégorie (JSON) affichés dans l'inspecteur.

Les embeddings sont mis en cache (SQLite) : une image déjà analysée n'est jamais recalculée.

## Rangement

Les fichiers sont déplacés et renommés dans une arborescence :

```
Destination/Categorie/Couleur/Format/categorie_###_mots-cles.jpg
```

Chaque application écrit un journal permettant l'**annulation** (undo).

## Catégories par défaut

Personnes · Paysages · Animaux · Objets/documents/schémas · Autre (fallback).
Modifiables directement dans l'interface.

## Installation (Linux + GPU NVIDIA)

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```

## Lancement

```bash
./run.sh          # uvicorn sur 0.0.0.0:8800
```

Puis ouvrir `http://<ip-machine>:8800` depuis n'importe quel navigateur du réseau.

Un fichier `iris.service` (systemd) est fourni pour un démarrage automatique.

## Pile technique

FastAPI · PyTorch (CUDA) · open_clip · Ultralytics YOLO · Transformers (Qwen2-VL) · SQLite · HTML/CSS/JS vanilla.
