from pathlib import Path

import numpy as np

import classifier
import gallery as gallery_module


def build_topk_graph(items: list[dict], embeddings: dict[str, np.ndarray], top_k: float, min_similarity: float) -> dict:
    """Nœuds = items (déjà filtrés par l'appelant), arêtes = top_k voisins les
    plus proches (similarité cosinus) au-dessus de min_similarity. Factorisé
    pour être partagé entre similarité générale (whole-image) et identité
    (crop visage) — même algorithme, source d'embeddings différente."""
    ordered = [i for i in items if i["path"] in embeddings]
    paths = [i["path"] for i in ordered]
    if len(paths) < 2:
        return {"nodes": [], "edges": []}
    matrix = np.stack([embeddings[p] for p in paths])
    sims = matrix @ matrix.T

    n = len(paths)
    edge_set: dict[tuple[int, int], float] = {}
    for i in range(n):
        # argsort ascendant -> on prend les derniers (les plus proches), en
        # excluant soi-même (toujours similarité 1.0 avec soi-même).
        order = np.argsort(sims[i])[::-1]
        taken = 0
        for j in order:
            if j == i:
                continue
            score = float(sims[i, j])
            if score < min_similarity:
                break
            key = (i, j) if i < j else (j, i)
            if key not in edge_set or edge_set[key] < score:
                edge_set[key] = score
            taken += 1
            if taken >= top_k:
                break

    nodes = [{"path": ordered[i]["path"], "category_label": ordered[i]["category_label"]} for i in range(n)]
    edges = [{"source": ordered[i]["path"], "target": ordered[j]["path"], "weight": round(w, 4)} for (i, j), w in edge_set.items()]
    return {"nodes": nodes, "edges": edges}


def build_similarity_graph(
    folder: str,
    category: str | None = None,
    top_k: int = 5,
    min_similarity: float = 0.75,
    progress: dict | None = None,
) -> dict:
    """Graphe de similarité visuelle — nœuds = photos, arêtes = les top_k
    voisins les plus proches (similarité cosinus sur les embeddings CLIP,
    même cache que Doublons/passe 1) au-dessus de min_similarity. Contrairement
    à Doublons (qui ne garde que les quasi-identiques), ceci révèle des
    regroupements thématiques plus larges (même style, même personnage...)."""
    items = gallery_module.list_gallery(folder)
    if category:
        items = [i for i in items if i["category_label"] == category]
    if progress is not None:
        progress["total"] = len(items)
        progress["done"] = 0
        progress["phase"] = "embeddings"
    if len(items) < 2:
        return {"nodes": [], "edges": []}

    paths_with_stat = [(Path(i["path"]), Path(i["path"]).stat().st_mtime, Path(i["path"]).stat().st_size) for i in items]
    cancel_check = (lambda: progress.get("cancel_requested")) if progress is not None else None
    try:
        embeddings = classifier.batch_image_embeddings(paths_with_stat, cancel_check=cancel_check)
    except classifier.Cancelled:
        if progress is not None:
            progress["status"] = "cancelled"
        return {"nodes": [], "edges": []}

    if progress is not None:
        progress["done"] = len(items)
        progress["phase"] = "graph"

    return build_topk_graph(items, embeddings, top_k, min_similarity)


def similar_images(path: str, top_k: int = 5, min_similarity: float = 0.5) -> list[dict]:
    """Voisins les plus proches d'UNE photo précise, dans son propre dossier
    _classees (déduit du chemin) — utilisé par le MCP (iris_similar_images)
    pour répondre à "trouve-moi des images qui ressemblent à celle-ci"."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Fichier introuvable: {p}")
    # Remonte jusqu'au dossier qui contient les sous-dossiers de catégories
    # (typiquement 3 niveaux : Categorie/Couleur/Format/fichier.jpg).
    root = p.parent.parent.parent if len(p.parts) > 3 else p.parent
    items = gallery_module.list_gallery(str(root))
    paths_with_stat = [(Path(i["path"]), Path(i["path"]).stat().st_mtime, Path(i["path"]).stat().st_size) for i in items]
    embeddings = classifier.batch_image_embeddings(paths_with_stat)

    target_emb = embeddings.get(str(p))
    if target_emb is None:
        return []

    scored = []
    for i in items:
        if i["path"] == str(p):
            continue
        emb = embeddings.get(i["path"])
        if emb is None:
            continue
        score = float(np.dot(target_emb, emb))
        if score >= min_similarity:
            scored.append({**i, "score": round(score, 4)})
    scored.sort(key=lambda x: -x["score"])
    return scored[:top_k]
