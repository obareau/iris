"""Clustering d'identité — regroupe les photos où le MÊME personnage
récurrent apparaît, à la différence de graph.py qui ne regroupe que par
similarité visuelle générale (style, ambiance, scène). Approche : détecter
la boîte "person" la plus grande (YOLO, déjà utilisé en passe 1), recadrer
dessus, et n'embedder QUE ce recadrage avec CLIP — retire le bruit du décor/
de la pose/des vêtements qui dilue l'embedding pleine-image, et rapproche
donc mieux deux apparitions du même perso que graph.py ne peut le faire."""

from pathlib import Path

from PIL import Image

import cache
import classifier
import gallery as gallery_module
import graph as graph_module
import prefilter

# Suffixe de clé de cache distinct de l'embedding pleine-image (même fichier
# SQLite que classifier.image_embedding, juste un autre "chemin" logique).
_FACE_CACHE_SUFFIX = "::face"


def _crop_largest_person(path: Path) -> Image.Image | None:
    dets = prefilter.detect(path)
    person_dets = [d for d in dets if d["name"] == "person"]
    if not person_dets:
        return None
    best = max(person_dets, key=lambda d: d["area"])
    img = Image.open(path).convert("RGB")
    w, h = img.size
    x1, y1, x2, y2 = best["box"]
    pad_x, pad_y = (x2 - x1) * 0.08, (y2 - y1) * 0.08
    x1, y1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
    x2, y2 = min(w, x2 + pad_x), min(h, y2 + pad_y)
    return img.crop((x1, y1, x2, y2))


def _face_embedding(path: Path):
    st = path.stat()
    cache_key = str(path) + _FACE_CACHE_SUFFIX
    cached = cache.get_embedding(cache_key, st.st_mtime, st.st_size)
    if cached is not None:
        return cached
    crop = _crop_largest_person(path)
    if crop is None:
        return None
    emb = classifier.embed_image_raw(crop)
    cache.set_embedding(cache_key, st.st_mtime, st.st_size, emb)
    return emb


def build_identity_graph(
    top_k: int = 5,
    min_similarity: float = 0.85,
    progress: dict | None = None,
) -> dict:
    """Sur toute la bibliothèque (plusieurs dossiers possibles, voir
    library.py). Limité à la catégorie Personnes — l'identité récurrente n'a
    de sens que pour des personnages, pas des paysages/objets."""
    items = gallery_module.list_gallery()
    items = [i for i in items if i["category_label"] == "Personnes"]
    if progress is not None:
        progress["total"] = len(items)
        progress["done"] = 0
        progress["phase"] = "faces"
    if len(items) < 2:
        return {"nodes": [], "edges": []}

    embeddings: dict[str, object] = {}
    for i in items:
        if progress is not None:
            if progress.get("cancel_requested"):
                progress["status"] = "cancelled"
                return {"nodes": [], "edges": []}
            progress["current"] = i["path"]
        emb = _face_embedding(Path(i["path"]))
        if emb is not None:
            embeddings[i["path"]] = emb
        if progress is not None:
            progress["done"] += 1

    if progress is not None:
        progress["phase"] = "graph"
        progress["current"] = None

    return graph_module.build_topk_graph(items, embeddings, top_k, min_similarity)
