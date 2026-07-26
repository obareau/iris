# Faire tourner Iris ailleurs

Cible visée : **PC récent, GPU AMD, Ubuntu**. Relevé du 2026-07-26.

---

## La bonne nouvelle : le code n'a pas à changer

Iris ne touche au GPU qu'à **un seul endroit** :

```python
# backend/classifier.py:7
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
```

`details.py` et `prefilter.py` réutilisent cette même variable.

Or **PyTorch compilé pour ROCm garde l'API `cuda`** : `torch.cuda.is_available()`
renvoie `True` sur une Radeon, et `.to("cuda")` route vers HIP. Il n'y a donc
**aucune ligne à modifier** — seule la *roue* PyTorch installée change.

Si aucun GPU n'est détecté, Iris bascule tout seul sur le CPU : ça marche, mais
l'analyse est lente (CLIP ViT-L/14 et Qwen2-VL sur processeur).

---

## Dépendances

### Python (`requirements.txt`)

```
fastapi · uvicorn[standard] · python-multipart · pillow · numpy
open_clip_torch · transformers · einops · accelerate · ultralytics
piexif · pikepdf
```

`torch` / `torchvision` ne sont **pas** dans le fichier : ils s'installent à part
avec l'index correspondant au GPU (voir ci-dessous).

### Binaires système

| Binaire | Paquet Ubuntu | Sert à |
|---|---|---|
| `google-chrome` ou `chromium` | `chromium-browser` | rendu PDF de l'artbook |
| `gs` | `ghostscript` | séparation CMJN |
| `pdfinfo` | `poppler-utils` | contrôle du PDF produit |
| profil ICC Fogra 39 | **`colord-data`** | `FOGRA39L_coated.icc` |
| `npx` | `nodejs` | pont vers Recta (publication Renégat) — optionnel |

```bash
sudo apt install chromium-browser ghostscript poppler-utils colord-data nodejs
```

### Poids des modèles (~10 Go)

Téléchargés à la première utilisation dans `~/.cache/huggingface` :

- `laion/CLIP-ViT-L-14-laion2B-s32B-b82K` — classement, recherche sémantique
- `laion/CLIP-ViT-B-32-laion2B-s34B-b79K`
- `Qwen/Qwen2-VL-2B-Instruct` — mots-clés, attributs, vérification de canon
- YOLOv8n (ultralytics, téléchargé à part)

Copier le cache évite de tout re-télécharger.

---

## Installation sur GPU AMD

ROCm **7.2** couvre les Radeon **RX 9000 (RDNA4)** et une partie des **RX 7000
(RDNA3)** — `gfx1200` pour RDNA4, `gfx1100/1101/1102` pour RDNA3. Vérifier que
la carte visée figure dans la liste des GPU supportés avant d'acheter.

```bash
# 1. pilote + pile ROCm (suivre la doc AMD pour la version d'Ubuntu)
#    puis se donner les droits GPU :
sudo usermod -aG render,video $USER   # déconnexion/reconnexion nécessaire

# 2. environnement Python (ROCm demande Python 3.12)
python3.12 -m venv venv && source venv/bin/activate

# 3. PyTorch ROCm — AMD recommande SES roues plutôt que celles de pytorch.org
pip install --index-url https://repo.amd.com/rocm/whl-multi-arch/ torch torchvision

# 4. le reste
pip install -r requirements.txt

# 5. vérification
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

### Pièges connus

- **Carte non listée** : forcer l'architecture avec
  `HSA_OVERRIDE_GFX_VERSION=11.0.0` (adapter à la génération). Marche souvent,
  n'est pas garanti.
- **Python 3.12** exigé par les roues ROCm officielles.
- **flash-attention** n'est pas disponible partout sur ROCm ; `transformers`
  retombe alors sur l'attention standard — plus lent, mais fonctionnel.
- **VRAM** : compter ~7 Go pour faire tourner CLIP ViT-L/14 et Qwen2-VL-2B
  confortablement (Roblab tourne sur une RTX 3060 12 Go).

---

## Service systemd

Le service actuel (`iris.service`) :

```ini
WorkingDirectory=/home/olivier/DEV/iris
ExecStart=/home/olivier/DEV/iris/venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8800
```

⚠️ **`python -m uvicorn`, pas `venv/bin/uvicorn`** : un venv n'est pas
relocatable (le shebang des scripts est en dur), donc le script casse dès que
le dossier bouge. Passer par `-m` contourne le problème.

---

## Données à emporter

| Quoi | Où | Remarque |
|---|---|---|
| Catalogue de dossiers | `data/library.json` | la bibliothèque |
| Cache d'embeddings | `data/*.db` (SQLite) | régénérable, mais long |
| Artbooks | `exports/artbook-models/*.json` | les projets de livres |
| Sidecars des photos | à côté de chaque image classée | catégorie, attributs, note |

Les sidecars vivent **avec les photos** : déplacer le dossier photos suffit à
emporter le classement.
