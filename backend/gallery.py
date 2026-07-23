import json
from pathlib import Path

import numpy as np

import aesthetic
import canon
import classifier
import details as details_module
import exif_writer
import factions
import library

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


def _root_for(path: Path, roots: list[Path]) -> Path | None:
    """Trouve, parmi les dossiers de la bibliothèque, celui qui contient
    réellement `path` — nécessaire dès qu'on a plusieurs racines : le nom du
    premier sous-dossier relatif (catégorie de repli) dépend de la bonne
    racine, pas de n'importe laquelle."""
    for root in roots:
        try:
            path.relative_to(root)
            return root
        except ValueError:
            continue
    return None


def list_gallery() -> list[dict]:
    """Parcourt récursivement tous les dossiers de la bibliothèque (voir
    library.py — plusieurs racines possibles, comme un catalogue Lightroom)
    et renvoie une entrée par image, enrichie du sidecar écrit par
    organizer.apply_moves quand il existe (catégorie, détails, attributs,
    marqueur renegat_posted). Sans sidecar (photo déposée manuellement, ou
    classée avant ce système), on retombe sur le nom du premier sous-dossier
    comme catégorie. Chaque item porte aussi `source_folder`, pour que l'UI
    puisse indiquer de quelle racine vient une photo."""
    items = []
    for folder in library.list_folders():
        root = Path(folder)
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in IMAGE_EXTS:
                continue
            sidecar = _read_sidecar(p)
            rel_parts = p.relative_to(root).parts
            fallback_category = rel_parts[0] if len(rel_parts) > 1 else None
            items.append({
                "path": str(p),
                "source_folder": str(root),
                "category_label": sidecar.get("category_label") or fallback_category or "?",
                "category_slug": sidecar.get("category_slug"),
                "details": sidecar.get("details"),
                "attributes": sidecar.get("attributes", []),
                "applied_at": sidecar.get("applied_at"),
                "renegat_posted": sidecar.get("renegat_posted"),
                "has_sidecar": bool(sidecar),
                "rating": sidecar.get("rating", 0),
                "aesthetic_score": sidecar.get("aesthetic_score"),
                "canon_faction": sidecar.get("canon_faction"),
                "canon_verdict": sidecar.get("canon_verdict"),
                "canon_reason": sidecar.get("canon_reason"),
                "canon_clip_confidence": sidecar.get("canon_clip_confidence"),
                "character_name": sidecar.get("character_name"),
            })
    return items


def _write_sidecar(image_path: Path, data: dict) -> None:
    image_path.with_suffix(".json").write_text(json.dumps(data, ensure_ascii=False, indent=2))


def library_health() -> list[dict]:
    """Un coup d'œil par dossier de la bibliothèque — accessible ou non (utile
    pour un dossier réseau démonté, qui sinon disparaît silencieusement de
    list_gallery), et ce qui reste à faire dessus (sidecar/score/canon
    manquants). Un seul passage sur list_gallery(), pas un scan par dossier."""
    items = list_gallery()
    by_folder: dict[str, list[dict]] = {}
    for item in items:
        by_folder.setdefault(item["source_folder"], []).append(item)

    result = []
    for folder in library.list_folders():
        accessible = Path(folder).is_dir()
        folder_items = by_folder.get(folder, [])
        result.append({
            "path": folder,
            "accessible": accessible,
            "total": len(folder_items),
            "no_sidecar": sum(1 for i in folder_items if not i["has_sidecar"]),
            "no_aesthetic": sum(1 for i in folder_items if i.get("aesthetic_score") is None),
            "no_canon": sum(1 for i in folder_items if i.get("canon_verdict") is None),
        })
    return result


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
    source_root = _root_for(p, [Path(f) for f in library.list_folders()])
    return {
        "path": str(p),
        "source_folder": str(source_root) if source_root else None,
        "category_label": sidecar.get("category_label") or fallback_category,
        "category_slug": sidecar.get("category_slug"),
        "details": sidecar.get("details"),
        "attributes": sidecar.get("attributes", []),
        "rating": sidecar.get("rating", 0),
        "aesthetic_score": sidecar.get("aesthetic_score"),
        "canon_faction": sidecar.get("canon_faction"),
        "canon_verdict": sidecar.get("canon_verdict"),
        "canon_reason": sidecar.get("canon_reason"),
        "canon_clip_confidence": sidecar.get("canon_clip_confidence"),
        "character_name": sidecar.get("character_name"),
        "renegat_posted": sidecar.get("renegat_posted"),
        "has_sidecar": bool(sidecar),
    }


def semantic_search(
    query: str,
    category: str | None = None,
    min_rating: int = 0,
    top_k: int = 10,
) -> list[dict]:
    """Recherche par similarité CLIP texte→image — répond à "une photo qui
    ressemble à X" plutôt qu'à une sous-chaîne exacte dans les attributs.
    Réutilise les mêmes embeddings mis en cache par la passe 1 / Doublons
    (data/embeddings.sqlite3) : une image déjà vue ne recoûte rien."""
    items = list_gallery()
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
    exif_writer.write_exif(path, existing)


def set_character_name(image_path: str, name: str) -> None:
    """Nom du personnage récurrent (rempli depuis le Graphe en mode identité,
    ou directement dans la Galerie) — chaîne vide pour effacer. Ce n'est pas
    un regroupement géré par Iris (le Graphe ne connaît que des similarités,
    pas des identités nommées) : c'est l'humain qui décide qu'un cluster
    détecté correspond à tel personnage, et l'applique."""
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Fichier introuvable: {path}")
    existing = _read_sidecar(path)
    existing["character_name"] = name.strip() or None
    _write_sidecar(path, existing)
    exif_writer.write_exif(path, existing)


def backfill_details(paths: list[str], progress: dict | None = None) -> None:
    """Extrait détails (passe 2) + attributs (passe 3) pour des photos déjà
    classées qui n'ont pas de sidecar (ou qui en ont un incomplet) — comble
    le manque pour les images triées avant ce système, sans repasser par
    tout le pipeline scan/analyze/apply (le fichier est déjà à sa place)."""
    roots = [Path(f) for f in library.list_folders()]
    if progress is not None:
        progress["total"] = len(paths)
        progress["done"] = 0

    for path_str in paths:
        if progress is not None and progress.get("cancel_requested"):
            progress["status"] = "cancelled"
            progress["current"] = None
            return
        path = Path(path_str)
        if progress is not None:
            progress["current"] = path_str
        try:
            existing = json.loads(path.with_suffix(".json").read_text()) if path.with_suffix(".json").is_file() else {}
            root = _root_for(path, roots)
            rel_parts = path.relative_to(root).parts if root else ()
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
            exif_writer.write_exif(path, existing)
        except Exception as e:
            if progress is not None:
                progress.setdefault("errors", []).append({"path": path_str, "error": str(e)})
        if progress is not None:
            progress["done"] += 1
    if progress is not None:
        progress["current"] = None


def refine_attributes_for(paths: list[str], progress: dict | None = None) -> None:
    """Force une repasse de passe 3 (attributs) sur des photos DÉJÀ classées
    et déjà documentées — utile quand ATTRIBUTE_SCHEMAS gagne une clé (ex:
    Pose/posture) après coup : backfill_details() saute les photos qui ont
    déjà des attributs, celle-ci les réaffine quand même et écrase le champ."""
    roots = [Path(f) for f in library.list_folders()]
    if progress is not None:
        progress["total"] = len(paths)
        progress["done"] = 0

    for path_str in paths:
        if progress is not None and progress.get("cancel_requested"):
            progress["status"] = "cancelled"
            progress["current"] = None
            return
        path = Path(path_str)
        if progress is not None:
            progress["current"] = path_str
        try:
            existing = json.loads(path.with_suffix(".json").read_text()) if path.with_suffix(".json").is_file() else {}
            root = _root_for(path, roots)
            rel_parts = path.relative_to(root).parts if root else ()
            fallback_category = rel_parts[0] if len(rel_parts) > 1 else "?"
            category_slug = existing.get("category_slug") or _LABEL_TO_SLUG.get(
                existing.get("category_label") or fallback_category, "autre"
            )
            existing["attributes"] = details_module.refine_attributes(path, category_slug)
            _write_sidecar(path, existing)
            exif_writer.write_exif(path, existing)
        except Exception as e:
            if progress is not None:
                progress.setdefault("errors", []).append({"path": path_str, "error": str(e)})
        if progress is not None:
            progress["done"] += 1
    if progress is not None:
        progress["current"] = None


def _label_value_pairs(item: dict) -> list[tuple[str, str]]:
    """Toutes les paires (label, valeur) d'un item — pseudo-attributs
    (Catégorie, Faction devinée, Verdict canon, Personnage) + attributs
    structurés de la passe 3. Partagé entre taxonomy() (nuage de mots) et
    taxonomy_cross() (croisement de deux attributs) pour ne pas dupliquer
    la liste des pseudo-attributs entre les deux."""
    pairs = []
    if item.get("category_label"):
        pairs.append(("Catégorie", item["category_label"]))
    if item.get("canon_faction"):
        pairs.append(("Faction devinée", item["canon_faction"]))
    if item.get("canon_verdict"):
        pairs.append(("Verdict canon", item["canon_verdict"]))
    if item.get("character_name"):
        pairs.append(("Personnage", item["character_name"]))
    for a in item.get("attributes") or []:
        label, value = a.get("label"), a.get("value")
        if label and value:
            pairs.append((label, value))
    return pairs


def taxonomy(category: str | None = None) -> dict:
    """Fréquence des valeurs d'attributs (passe 3) sur toute la bibliothèque —
    lecture pure des sidecars, aucun calcul de modèle, instantané même sur
    un gros lot. Regroupé par label (ex: "Tenue" -> {"jacket": 12, ...}) pour
    alimenter un nuage de mots par attribut plutôt qu'un fourre-tout unique."""
    items = list_gallery()
    if category:
        items = [i for i in items if i["category_label"] == category]

    by_label: dict[str, dict[str, int]] = {}
    for i in items:
        for label, value in _label_value_pairs(i):
            bucket = by_label.setdefault(label, {})
            bucket[value] = bucket.get(value, 0) + 1

    # Trie chaque groupe par fréquence décroissante — le nuage doit pouvoir
    # afficher les N plus fréquents sans avoir à retrier côté client.
    return {
        label: sorted(({"value": v, "count": c} for v, c in values.items()), key=lambda x: -x["count"])
        for label, values in by_label.items()
    }


def taxonomy_labels() -> list[str]:
    """Labels disponibles pour l'analyse croisée — mêmes clés que taxonomy()."""
    return sorted(taxonomy().keys())


def taxonomy_cross(label_a: str, label_b: str) -> dict:
    """Croise deux attributs (ou pseudo-attributs, ex: Faction devinée ×
    Verdict canon) — utile pour repérer des incohérences en masse plutôt
    qu'attribut par attribut. Une photo sans valeur pour l'un des deux labels
    est simplement ignorée pour ce croisement."""
    items = list_gallery()
    counts: dict[tuple[str, str], int] = {}
    for item in items:
        values = dict(_label_value_pairs(item))
        va, vb = values.get(label_a), values.get(label_b)
        if not va or not vb:
            continue
        key = (va, vb)
        counts[key] = counts.get(key, 0) + 1

    rows = sorted({va for va, vb in counts})
    cols = sorted({vb for va, vb in counts})
    cells = [{"a": va, "b": vb, "count": c} for (va, vb), c in counts.items()]
    cells.sort(key=lambda x: -x["count"])
    return {"label_a": label_a, "label_b": label_b, "rows": rows, "cols": cols, "cells": cells}


def score_aesthetic_for(paths: list[str], progress: dict | None = None) -> None:
    """Calcule le score esthétique (aesthetic.py) pour des photos déjà
    classées — retombe sur les embeddings CLIP déjà en cache (passe 1),
    donc rapide même sur un gros lot déjà analysé."""
    if progress is not None:
        progress["total"] = len(paths)
        progress["done"] = 0

    for path_str in paths:
        if progress is not None and progress.get("cancel_requested"):
            progress["status"] = "cancelled"
            progress["current"] = None
            return
        path = Path(path_str)
        if progress is not None:
            progress["current"] = path_str
        try:
            existing = _read_sidecar(path)
            existing["aesthetic_score"] = aesthetic.score_path(path)
            _write_sidecar(path, existing)
            exif_writer.write_exif(path, existing)
        except Exception as e:
            if progress is not None:
                progress.setdefault("errors", []).append({"path": path_str, "error": str(e)})
        if progress is not None:
            progress["done"] += 1
    if progress is not None:
        progress["current"] = None


def check_canon_for(paths: list[str], faction_id: str | None = None, progress: dict | None = None) -> None:
    """Sans `faction_id` : devine la faction par CLIP zero-shot
    (canon.guess_faction). Avec `faction_id` : force la vérification contre
    cette faction précise, sans deviner — utile quand le guess se trompe ou
    pour tester délibérément une hypothèse. Dans les deux cas, Qwen2-VL lit
    l'image + le lore de la faction pour un verdict (canon.check_canon),
    écrit dans le sidecar + EXIF comme score_aesthetic_for pour le score
    esthétique."""
    forced_faction = None
    if faction_id:
        fac = factions.get_faction(faction_id)
        if fac is None:
            raise ValueError(f"Faction inconnue : {faction_id}")
        forced_faction = {"id": fac["id"], "label": fac["label"]}

    if progress is not None:
        progress["total"] = len(paths)
        progress["done"] = 0

    for path_str in paths:
        if progress is not None and progress.get("cancel_requested"):
            progress["status"] = "cancelled"
            progress["current"] = None
            return
        path = Path(path_str)
        if progress is not None:
            progress["current"] = path_str
        try:
            existing = _read_sidecar(path)
            faction = forced_faction or canon.guess_faction(path)
            if faction is None:
                existing["canon_faction"] = None
                existing["canon_verdict"] = None
                existing["canon_reason"] = "Aucune faction reconnaissable avec assez de confiance."
                existing["canon_clip_confidence"] = None
            else:
                result = canon.check_canon(path, faction)
                existing["canon_faction"] = faction["label"]
                existing["canon_verdict"] = result["verdict_label"]
                existing["canon_reason"] = result["reason"]
                existing["canon_clip_confidence"] = result["clip_confidence"]
            _write_sidecar(path, existing)
            exif_writer.write_exif(path, existing)
        except Exception as e:
            if progress is not None:
                progress.setdefault("errors", []).append({"path": path_str, "error": str(e)})
        if progress is not None:
            progress["done"] += 1
    if progress is not None:
        progress["current"] = None
