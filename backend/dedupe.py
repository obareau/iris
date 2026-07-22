import shutil
import time
from pathlib import Path

import numpy as np

import classifier

TRASH_DIR = Path.home() / ".iris-trash"


def _union_find_groups(n: int, pairs: list[tuple[int, int]]) -> list[list[int]]:
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b in pairs:
        union(a, b)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return [g for g in groups.values() if len(g) > 1]


def find_duplicate_groups(files: list[Path], threshold: float = 0.92, progress: dict | None = None) -> list[dict]:
    """Regroupe les images quasi-identiques ou très similaires (parmi `files`)
    via similarité cosinus sur les embeddings CLIP qu'Iris calcule déjà en
    passe 1 — même cache SQLite (data/embeddings.sqlite3), donc une image
    déjà analysée ne recoûte rien. `files` est déjà résolu par l'appelant
    (main.py), filtré par catégorie si besoin via gallery.list_gallery.
    O(n²) sur la similarité : correct jusqu'à quelques milliers d'images,
    pas pensé au-delà."""
    if progress is not None:
        progress["total"] = len(files)
        progress["done"] = 0
        progress["phase"] = "embeddings"

    paths_with_stat = [(p, p.stat().st_mtime, p.stat().st_size) for p in files]
    cancel_check = (lambda: progress.get("cancel_requested")) if progress is not None else None
    try:
        embeddings = classifier.batch_image_embeddings(paths_with_stat, cancel_check=cancel_check)
    except classifier.Cancelled:
        if progress is not None:
            progress["status"] = "cancelled"
        return []

    if progress is not None:
        progress["done"] = len(files)
        progress["phase"] = "similarity"

    ordered_paths = [str(p) for p, _, _ in paths_with_stat if str(p) in embeddings]
    if len(ordered_paths) < 2:
        return []

    matrix = np.stack([embeddings[p] for p in ordered_paths])
    sims = matrix @ matrix.T  # embeddings déjà normalisés L2 -> produit scalaire = cosinus

    n = len(ordered_paths)
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n) if sims[i, j] >= threshold]
    index_groups = _union_find_groups(n, pairs)

    groups = []
    for idxs in index_groups:
        group_paths = [ordered_paths[i] for i in idxs]
        max_sim = max(sims[i, j] for a, i in enumerate(idxs) for j in idxs[a + 1:])
        groups.append({"images": group_paths, "max_similarity": round(float(max_sim), 4)})
    groups.sort(key=lambda g: -g["max_similarity"])
    return groups


def discard(path: str) -> str:
    """Déplace la photo (+ son sidecar éventuel) vers une corbeille locale
    plutôt que de la supprimer — réversible si le regroupement se trompe."""
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"Fichier introuvable: {src}")
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = TRASH_DIR / f"{stamp}_{src.name}"
    shutil.move(str(src), str(dest))
    sidecar = src.with_suffix(".json")
    if sidecar.is_file():
        shutil.move(str(sidecar), str(TRASH_DIR / f"{stamp}_{sidecar.name}"))
    return str(dest)
