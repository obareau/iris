"""Génère une planche contact HTML autonome (images encodées en base64,
aucune dépendance externe, aucun serveur requis pour la relire) à partir
d'une sélection de photos de la Galerie — pour partager une sélection hors
d'Iris (revue, référence externe) sans dépendre de l'appli elle-même."""

import base64
import io
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from PIL import Image

import gallery as gallery_module

EXPORTS_DIR = Path(__file__).parent.parent / "exports"
THUMB_SIZE = (480, 480)  # assez grand pour une planche contact, raisonnable en taille de fichier


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text or "export"


def _thumb_data_uri(path: Path) -> str:
    img = Image.open(path).convert("RGB")
    img.thumbnail(THUMB_SIZE)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_contact_sheet(paths: list[str], title: str = "Sélection Iris") -> Path:
    """Écrit un fichier HTML autonome dans exports/ et renvoie son chemin.
    Les photos illisibles (déplacées/supprimées entre-temps) sont ignorées
    plutôt que de faire échouer tout l'export."""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    items_by_path = {i["path"]: i for i in gallery_module.list_gallery()}
    cards = []
    for p in paths:
        path = Path(p)
        if not path.is_file():
            continue
        item = items_by_path.get(p, {})
        rating = item.get("rating") or 0
        stars = "★" * rating + "☆" * (5 - rating)
        caption_bits = [item.get("category_label") or "", item.get("character_name") or ""]
        caption = " · ".join(b for b in caption_bits if b)
        try:
            img_src = _thumb_data_uri(path)
        except Exception:
            continue
        cards.append(f"""
        <figure>
          <img src="{img_src}" alt="{_escape(path.name)}" loading="lazy" />
          <figcaption>
            <div class="name">{_escape(path.name)}</div>
            <div class="meta">{_escape(caption)}</div>
            <div class="stars">{stars}</div>
          </figcaption>
        </figure>""")

    html = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<title>{_escape(title)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #16171b; color: #e7e9ee; margin: 0; padding: 24px; }}
  h1 {{ font-size: 20px; font-weight: 600; margin-bottom: 4px; }}
  .sub {{ color: #9096a0; font-size: 13px; margin-bottom: 24px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }}
  figure {{ margin: 0; background: #1e2025; border: 1px solid #2a2d33; border-radius: 8px; overflow: hidden; }}
  img {{ width: 100%; height: 220px; object-fit: cover; display: block; }}
  figcaption {{ padding: 10px 12px; }}
  .name {{ font-size: 12px; word-break: break-all; }}
  .meta {{ font-size: 11px; color: #9096a0; margin-top: 4px; }}
  .stars {{ font-size: 12px; color: #d8a83f; margin-top: 4px; }}
</style>
</head>
<body>
  <h1>{_escape(title)}</h1>
  <div class="sub">{len(cards)} photo(s) — généré par Iris le {datetime.now().strftime("%d/%m/%Y à %H:%M")}</div>
  <div class="grid">{"".join(cards)}</div>
</body>
</html>"""

    filename = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{_slugify(title)}.html"
    out_path = EXPORTS_DIR / filename
    out_path.write_text(html, encoding="utf-8")
    return out_path
