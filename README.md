# 🌈 Iris

Application web locale de **tri, documentation et recherche d'images** par
contenu, pensée pour traiter de gros volumes rapidement sur GPU. Interface
façon Lightroom (plusieurs panneaux, thème clair), calcul déporté sur une
machine GPU, affichage dans n'importe quel navigateur du réseau.

Iris est la **documentaliste** : tri, recherche, attributs. Elle ne publie
rien elle-même — [Recta](https://github.com/obareau/Recta) est le Posteur.

## Onglets

- **Tri** — import d'un dossier source, pipeline en 3 passes cumulatives
  (voir ci-dessous), application (déplace + renomme), undo.
- **Bibliothèque** — catalogue de dossiers déjà classés (à la Lightroom) :
  plusieurs sources vues comme une seule collection, sans avoir à retaper un
  chemin dans chaque onglet. Affiche la santé de chaque dossier (accessible,
  nombre de photos, ce qui manque encore).
- **Galerie** — parcourt toute la bibliothèque : filtre par catégorie/
  attribut, recherche sémantique (CLIP texte→image), sélection en masse
  (notation, suppression, réaffinage, score esthétique, vérification de
  canon), lightbox, publication vers Recta (aperçu → confirmation).
- **Doublons** — regroupe les photos quasi-identiques (union-find + similarité
  cosinus sur les embeddings CLIP déjà en cache), écarte vers une corbeille
  réversible.
- **Graphe** — nœuds = photos, arêtes = similarité visuelle (mode
  *similarité*) ou même personnage récurrent détecté par crop de visage (mode
  *identité*).
- **Recta** — timeline des photos déjà publiées (lu depuis le sidecar).
- **Taxonomie** — nuage de mots des attributs de passe 3, clic → filtre la
  Galerie.

## Pipeline (onglet Tri)

L'analyse se fait en 3 passes cumulatives et indépendantes :

1. **Analyse (passe 1)** — classement par catégorie
   - **YOLOv8n** : pré-filtre rapide, résout instantanément les images à objet dominant (personne, animal, objet).
   - **CLIP ViT-L/14** (zero-shot) : prend le relais pour les images ambiguës (typiquement les paysages).
   - Détection **couleur** (N&B / Couleur) et **format** (Paysage / Portrait) déterministe, sans IA.
2. **Détails (passe 2)** — mots-clés descriptifs par image via le VLM **Qwen2-VL-2B** (cheveux/tatouages, architecture, type de machine…), intégrés au nom de fichier.
3. **Affiner (passe 3)** — attributs structurés par catégorie (JSON) affichés dans l'inspecteur.

Les embeddings sont mis en cache (SQLite) : une image déjà analysée n'est
jamais recalculée. Un bouton "Tout faire d'un coup" enchaîne les 3 passes +
l'application sans repasser par chaque étape.

## Au-delà du tri (sur des photos déjà classées)

- **Score esthétique (IA)** — MLP entraîné sur des embeddings CLIP
  (christophschuhmann/improved-aesthetic-predictor), score ~1-10 façon AVA.
- **Vérification de canon** — devine la faction Robotariis d'un personnage
  (CLIP zero-shot sur les fiches du vault [robotariis-writing](https://github.com/obareau/robotariis-writing)),
  puis Qwen2-VL lit l'image + le lore pour un verdict conforme/douteux/
  hors-canon + justification. Premier tri consultatif, pas un jugement
  définitif (voir `ROADMAP.md`).
- **EXIF write-back** — catégorie/détails/attributs/note/score/canon écrits
  dans le JPEG lui-même (`XPComment`/`XPKeywords`), best-effort.
- **Job cancellation** — les jobs longs (analyse, détails, attributs,
  dédoublonnage, rétro-remplissage, graphe, score esthétique, canon) ont un
  bouton Annuler.

## Rangement

Les fichiers sont déplacés et renommés dans une arborescence :

```
Destination/Categorie/Couleur/Format/categorie_###_mots-cles.jpg
```

Chaque application écrit un journal permettant l'**annulation** (undo).

## Catégories par défaut

Personnes · Paysages · Animaux · Objets/documents/schémas · Autre (fallback).
Modifiables directement dans l'interface.

## MCP `iris`

Serveur MCP en lecture seule (`iris_mcp.py`, stdio) pour qu'un agent puisse
interroger la bibliothèque sans passer par l'UI : `iris_search` (recherche
sémantique ou filtre catégorie/note), `iris_categories`, `iris_image_details`,
`iris_similar_images`, `iris_library_folders`. Aucune écriture exposée —
notation/suppression/publication/gestion de la bibliothèque restent réservées
à l'UI (aperçu + confirmation humaine).

```bash
claude mcp add iris -s user -- uv run --with mcp ~/DEV/iris/iris_mcp.py
```

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

FastAPI · PyTorch (CUDA) · open_clip (ViT-L/14) · Ultralytics YOLO ·
Transformers (Qwen2-VL-2B) · SQLite · piexif · HTML/CSS/JS vanilla.

Voir `ROADMAP.md` pour ce qui reste à faire.
