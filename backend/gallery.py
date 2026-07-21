import json
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


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
        })
    return items
