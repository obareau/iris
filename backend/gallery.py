import json
from pathlib import Path

import numpy as np

import classifier
import details as details_module

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# Les photos classées existent souvent sans sidecar (triées avant l'ajout du
# sidecar, ou déposées à la main) — on ne connaît alors que le nom du dossier
# (le label), pas le slug attendu par details.QUESTIONS/ATTRIBUTE_SCHEMAS.
# Reconstruit au mieux depuis les catégories par défaut ; un label inconnu
# retombe sur le schéma "autre" (comportement déjà celui de details.py).
_LABEL_TO_SLUG = {c["label"]: c["slug"] for c in classifier.DEFAULT_CATEGORIES}
_LABEL_TO_SLUG[classifier.FALLBACK_CATEGORY["label"]] = classifier.FALLBACK_CATEGORY["slug"]


def _read_sidecar(image_path: Path) -> dict:
    sidecar = image_path.with_suffix(".json")
    if not sidecar.is_file():
        return {}
    try:
        return json.loads(sidecar.read_text())
    except Exception:
        return {}


def list_gallery(folder: str) -> list[dict]:
    """Parcourt récursivement `folder` (typiquement _classees) et renvoie une
    entrée par image, enrichie du sidecar écrit par organizer.apply_moves
    quand il existe (catégorie, détails, attributs, marqueur renegat_posted).
    Sans sidecar (photo déposée manuellement, ou classée avant ce système),
    on retombe sur le nom du premier sous-dossier comme catégorie."""
    root = Path(folder)
    if not root.is_dir():
        return []

    items = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in IMAGE_EXTS:
            continue
        sidecar = _read_sidecar(p)
        rel_parts = p.relative_to(root).parts
        fallback_category = rel_parts[0] if len(rel_parts) > 1 else None
        items.append({
            "path": str(p),
            "category_label": sidecar.get("category_label") or fallback_category or "?",
            "category_slug": sidecar.get("category_slug"),
            "details": sidecar.get("details"),
            "attributes": sidecar.get("attributes", []),
            "applied_at": sidecar.get("applied_at"),
            "renegat_posted": sidecar.get("renegat_posted"),
            "has_sidecar": bool(sidecar),
            "rating": sidecar.get("rating", 0),
        })
    return items


def _write_sidecar(image_path: Path, data: dict) -> None:
    image_path.with_suffix(".json").write_text(json.dumps(data, ensure_ascii=False, indent=2))


def get_item(path: str) -> dict:
    """Fiche d'une seule photo, sans avoir besoin de reparcourir tout le
    dossier — utilisé par le MCP (iris_image_details) et par tout appelant
    qui connaît déjà le chemin exact."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Fichier introuvable: {p}")
    sidecar = _read_sidecar(p)
    # Sans root connu ici, le seul repli possible est le nom du dossier direct
    # (moins fiable que list_gallery's rel_parts[0], mais get_item ne sert
    # qu'aux photos déjà documentées — le cas sans sidecar y est marginal).
    fallback_category = p.parent.parent.parent.name if len(p.parts) > 3 else p.parent.name
    return {
        "path": str(p),
        "category_label": sidecar.get("category_label") or fallback_category,
        "category_slug": sidecar.get("category_slug"),
        "details": sidecar.get("details"),
        "attributes": sidecar.get("attributes", []),
        "rating": sidecar.get("rating", 0),
        "renegat_posted": sidecar.get("renegat_posted"),
        "has_sidecar": bool(sidecar),
    }


def semantic_search(
    folder: str,
    query: str,
    category: str | None = None,
    min_rating: int = 0,
    top_k: int = 10,
) -> list[dict]:
    """Recherche par similarité CLIP texte→image — répond à "une photo qui
    ressemble à X" plutôt qu'à une sous-chaîne exacte dans les attributs.
    Réutilise les mêmes embeddings mis en cache par la passe 1 / Doublons
    (data/embeddings.sqlite3) : une image déjà vue ne recoûte rien."""
    items = list_gallery(folder)
    if category:
        items = [i for i in items if i["category_label"] == category]
    if min_rating:
        items = [i for i in items if (i.get("rating") or 0) >= min_rating]
    if not items:
        return []

    paths_with_stat = [(Path(i["path"]), Path(i["path"]).stat().st_mtime, Path(i["path"]).stat().st_size) for i in items]
    embeddings = classifier.batch_image_embeddings(paths_with_stat)

    text_feat = classifier.text_embeddings([{"prompt": query}])[0].detach().cpu().numpy()

    scored = []
    for item in items:
        emb = embeddings.get(item["path"])
        if emb is None:
            continue
        scored.append({**item, "score": round(float(np.dot(emb, text_feat)), 4)})
    scored.sort(key=lambda x: -x["score"])
    return scored[:top_k]


def set_rating(image_path: str, rating: int) -> None:
    """Note 0-5 stockée dans le sidecar — c'est ce que Recta lit (même
    fichier, même dossier _classees) pour préférer les photos les mieux
    notées plutôt qu'un tirage purement aléatoire."""
    if not 0 <= rating <= 5:
        raise ValueError("La note doit être entre 0 et 5")
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Fichier introuvable: {path}")
    existing = _read_sidecar(path)
    existing["rating"] = rating
    _write_sidecar(path, existing)


def backfill_details(folder: str, paths: list[str], progress: dict | None = None) -> None:
    """Extrait détails (passe 2) + attributs (passe 3) pour des photos déjà
    classées qui n'ont pas de sidecar (ou qui en ont un incomplet) — comble
    le manque pour les images triées avant ce système, sans repasser par
    tout le pipeline scan/analyze/apply (le fichier est déjà à sa place)."""
    root = Path(folder)
    if progress is not None:
        progress["total"] = len(paths)
        progress["done"] = 0

    for path_str in paths:
        path = Path(path_str)
        if progress is not None:
            progress["current"] = path_str
        try:
            existing = json.loads(path.with_suffix(".json").read_text()) if path.with_suffix(".json").is_file() else {}
            rel_parts = path.relative_to(root).parts
            fallback_category = rel_parts[0] if len(rel_parts) > 1 else "?"
            rel_category = existing.get("category_label") or fallback_category
            category_slug = existing.get("category_slug") or _LABEL_TO_SLUG.get(rel_category, "autre")

            detail = details_module.extract_detail(path, category_slug)
            attributes = details_module.refine_attributes(path, category_slug)

            existing.update({
                "category_slug": category_slug,
                "category_label": existing.get("category_label") or rel_category,
                "details": detail["text"],
                "attributes": attributes,
            })
            _write_sidecar(path, existing)
        except Exception as e:
            if progress is not None:
                progress.setdefault("errors", []).append({"path": path_str, "error": str(e)})
        if progress is not None:
            progress["done"] += 1
    if progress is not None:
        progress["current"] = None
