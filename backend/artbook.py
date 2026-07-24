"""ARTBOOK — moteur de composition + rendu d'un livre photo soigné.

Deux étages, volontairement séparés pour permettre l'ÉDITION :

  1. compose_model(paths, ...) -> MODÈLE (dict JSON : liste de pages)
     Auto-curation : exploite les données d'Iris (score esthétique, catégorie,
     note, attributs) pour choisir les hero shots, regrouper en chapitres et
     alterner les gabarits. Ne contient QUE des chemins + du texte — léger,
     éditable, sérialisable.

  2. render_model(model) -> fichier HTML print-quality
     Encode les images en base64 au moment du rendu (@page, fond perdu, doubles
     pages), y compris les nouveaux gabarits TEXTE (page éditoriale, pull-quote).

Un artbook est ainsi un PROJET sauvegardable (models/<id>.json) : on le génère,
on ajuste le placement (gabarit d'une page, ordre/recadrage des photos), on
insère des pages de texte, puis on re-rend.
"""

import base64
import io
import json
import re
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

import gallery as gallery_module

BASE_DIR = Path(__file__).parent.parent
EXPORTS_DIR = BASE_DIR / "exports"
MODELS_DIR = BASE_DIR / "exports" / "artbook-models"

HERO_MAX = 1600
GRID_MAX = 1000
JPEG_Q = 86

# Gabarits image et nombre de photos consommées.
SLOTS = {"full": 1, "duo": 2, "trio": 3, "quad": 4}
IMAGE_TPLS = set(SLOTS)
TEXT_TPLS = {"text", "quote"}


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "artbook"


def _escape(t: str) -> str:
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _nl2br(t: str) -> str:
    return _escape(t).replace("\n\n", "</p><p>").replace("\n", "<br/>")


# ---------------------------------------------------------------------------
# Métadonnées / helpers image
# ---------------------------------------------------------------------------
def _meta_index() -> dict:
    return {i["path"]: i for i in gallery_module.list_gallery()}


def _orientation(path: Path) -> str:
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            w, h = im.size
        if w >= h * 1.15:
            return "land"
        if h >= w * 1.15:
            return "port"
        return "square"
    except Exception:
        return "land"


def _score(item: dict) -> float:
    s = item.get("aesthetic_score")
    return float(s) if s is not None else (item.get("rating") or 0) * 1.6


def _caption(item: dict) -> str:
    bits = []
    if item.get("character_name"):
        bits.append(item["character_name"])
    elif item.get("category_label") and item["category_label"] != "?":
        bits.append(item["category_label"])
    attrs = item.get("attributes") or []
    if attrs and isinstance(attrs[0], dict) and attrs[0].get("value"):
        bits.append(str(attrs[0]["value"]))
    return " · ".join(b for b in bits if b)


def _data_uri(path: Path, max_px: int) -> str:
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img.thumbnail((max_px, max_px), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_Q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# ---------------------------------------------------------------------------
# 1) COMPOSITION → modèle
# ---------------------------------------------------------------------------
def compose_model(paths, title="Iris Artbook", subtitle="", chapter_by="category") -> dict:
    meta = _meta_index()
    items = []
    for p in paths:
        if not Path(p).is_file():
            continue
        it = dict(meta.get(p, {}))
        it["path"] = p
        it["_score"] = _score(it)
        items.append(it)
    if not items:
        raise ValueError("Aucune photo lisible dans la sélection")

    if chapter_by == "category":
        groups = {}
        for it in items:
            groups.setdefault(it.get("category_label") or "Sans catégorie", []).append(it)
    else:
        groups = {"": items}

    chapters = []
    for t, its in groups.items():
        its.sort(key=lambda x: x["_score"], reverse=True)
        chapters.append((t, its, sum(x["_score"] for x in its) / len(its)))
    chapters.sort(key=lambda c: c[2], reverse=True)

    multi = chapter_by == "category" and len(chapters) > 1
    hero = chapters[0][1][0]["path"]

    pages = [{"tpl": "cover", "hero": hero, "title": title,
              "subtitle": subtitle or datetime.now().strftime("%d %B %Y")}]

    cycle = ["quad", "full", "duo", "trio", "full", "quad", "duo"]
    for ci, (ctitle, its, _) in enumerate(chapters):
        if multi and ctitle:
            pages.append({"tpl": "chapter", "title": ctitle, "num": ci + 1, "count": len(its)})
        paths_c = [x["path"] for x in its]
        i, n, k = 0, len(paths_c), 0
        if n:
            pages.append({"tpl": "full", "items": [paths_c[0]]})
            i = 1
        while i < n:
            tpl = cycle[k % len(cycle)]; k += 1
            need = SLOTS[tpl]
            if n - i < need:
                need = n - i
                tpl = {1: "full", 2: "duo", 3: "trio"}.get(need, "quad")
            pages.append({"tpl": tpl, "items": paths_c[i:i + need]})
            i += need

    return {
        "id": uuid.uuid4().hex[:12],
        "title": title,
        "subtitle": subtitle or datetime.now().strftime("%d %B %Y"),
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "pages": pages,
    }


# ---------------------------------------------------------------------------
# Persistance du modèle
# ---------------------------------------------------------------------------
def save_model(model: dict) -> str:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    mid = model.get("id") or uuid.uuid4().hex[:12]
    model["id"] = mid
    (MODELS_DIR / f"{mid}.json").write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    return mid


def load_model(mid: str) -> dict | None:
    f = MODELS_DIR / f"{mid}.json"
    if not f.is_file():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def list_models() -> list[dict]:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for f in sorted(MODELS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
            out.append({"id": m.get("id"), "title": m.get("title"),
                        "pages": len(m.get("pages", [])), "createdAt": m.get("createdAt")})
        except Exception:
            continue
    return out


# ---------------------------------------------------------------------------
# 2) RENDU du modèle → HTML
# ---------------------------------------------------------------------------
def _fig(path, tpl, fits, meta, with_caption=True):
    it = meta.get(path, {})
    fit = fits.get(path, "cover")
    src = _data_uri(Path(path), HERO_MAX if tpl == "full" else GRID_MAX)
    orient = _orientation(Path(path))
    cap = _caption(it)
    cap_html = f'<figcaption>{_escape(cap)}</figcaption>' if (with_caption and cap) else ""
    return f'<figure class="o-{orient} fit-{fit}"><img src="{src}" alt="" />{cap_html}</figure>'


def _render_page(pg: dict, meta: dict) -> str:
    tpl = pg["tpl"]

    if tpl == "cover":
        bg = f'<img class="cover-bg" src="{_data_uri(Path(pg["hero"]), HERO_MAX)}" alt="" />' if pg.get("hero") else ""
        return (f'<section class="page page-cover">{bg}<div class="cover-scrim"></div>'
                f'<div class="cover-text"><div class="cover-kicker">ARTBOOK</div>'
                f'<h1 class="cover-title">{_escape(pg["title"])}</h1>'
                f'<div class="cover-sub">{_escape(pg.get("subtitle",""))}</div></div></section>')

    if tpl == "chapter":
        return (f'<section class="page page-chapter"><div class="ch-num">{pg.get("num",1):02d}</div>'
                f'<h2 class="ch-title">{_escape(pg["title"])}</h2><div class="ch-rule"></div>'
                f'<div class="ch-count">{pg.get("count","")} images</div></section>')

    if tpl == "text":
        heading = f'<h3 class="tx-heading">{_escape(pg.get("heading",""))}</h3>' if pg.get("heading") else ""
        kicker = f'<div class="tx-kicker">{_escape(pg["kicker"])}</div>' if pg.get("kicker") else ""
        body = f'<div class="tx-body"><p>{_nl2br(pg.get("body",""))}</p></div>'
        return f'<section class="page page-text">{kicker}{heading}{body}</section>'

    if tpl == "quote":
        attr = f'<div class="q-attr">{_escape(pg["attribution"])}</div>' if pg.get("attribution") else ""
        return (f'<section class="page page-quote"><blockquote class="q-text">'
                f'{_escape(pg.get("quote",""))}</blockquote>{attr}</section>')

    # gabarits image
    fits = pg.get("fits") or {}
    items = pg.get("items", [])
    if tpl == "full":
        return f'<section class="page page-full">{_fig(items[0], tpl, fits, meta, True)}</section>'
    grid = {"duo": "g-duo", "trio": "g-trio", "quad": "g-quad"}.get(tpl, "g-quad")
    figs = "".join(_fig(p, tpl, fits, meta) for p in items)
    return f'<section class="page page-grid {grid}">{figs}</section>'


CSS = """
:root { --page:210mm; --ink:#1a1a1a; --paper:#faf8f4; --muted:#8a8479; --accent:#b8863b; }
*{box-sizing:border-box;} html,body{margin:0;padding:0;background:#3a3a3a;}
body{font-family:'Iowan Old Style','Palatino Linotype',Palatino,Georgia,'Times New Roman',serif;color:var(--ink);}
@page{size:210mm 210mm;margin:0;}
.page{width:var(--page);height:var(--page);position:relative;overflow:hidden;background:var(--paper);
  page-break-after:always;break-after:page;margin:10mm auto;box-shadow:0 6px 30px rgba(0,0,0,.4);}
@media print{.page{margin:0;box-shadow:none;}}
.page-cover{background:#111;} .cover-bg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;filter:saturate(.92) contrast(1.03);}
.cover-scrim{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.15),rgba(0,0,0,.05) 45%,rgba(0,0,0,.72));}
.cover-text{position:absolute;left:16mm;right:16mm;bottom:18mm;color:#fff;}
.cover-kicker{font-size:11px;letter-spacing:.42em;font-weight:600;opacity:.85;margin-bottom:6mm;}
.cover-title{font-size:46px;line-height:1.03;font-weight:600;margin:0;letter-spacing:.01em;}
.cover-sub{margin-top:5mm;font-size:14px;letter-spacing:.05em;opacity:.82;}
.page-chapter{display:flex;flex-direction:column;justify-content:center;padding:24mm;}
.ch-num{font-size:13px;letter-spacing:.4em;color:var(--accent);font-weight:600;}
.ch-title{font-size:40px;font-weight:600;margin:6mm 0 0;line-height:1.05;} .ch-rule{width:28mm;height:2px;background:var(--ink);margin:8mm 0;}
.ch-count{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);}
/* Pages TEXTE éditoriales (façon beau livre) */
.page-text{display:flex;flex-direction:column;justify-content:center;padding:30mm 34mm;}
.tx-kicker{font-size:11px;letter-spacing:.36em;text-transform:uppercase;color:var(--accent);font-weight:600;margin-bottom:7mm;}
.tx-heading{font-size:30px;font-weight:600;line-height:1.12;margin:0 0 9mm;}
.tx-body{font-size:14.5px;line-height:1.72;color:#33312c;}
.tx-body p{margin:0 0 4.5mm;} .tx-body p:first-letter{}
.page-quote{display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;padding:28mm;}
.q-text{font-size:30px;line-height:1.32;font-style:italic;font-weight:500;margin:0;max-width:150mm;position:relative;}
.q-text::before{content:'\\201C';position:absolute;left:-12mm;top:-8mm;font-size:70px;color:var(--accent);opacity:.5;}
.q-attr{margin-top:10mm;font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:var(--muted);}
/* Gabarits image */
.page-full{display:flex;} .page-full figure{margin:0;width:100%;height:100%;position:relative;}
.page-full img{width:100%;height:100%;display:block;}
.page-full figcaption,.page-grid figcaption{position:absolute;left:0;bottom:0;color:#fff;
  background:linear-gradient(180deg,rgba(0,0,0,0),rgba(0,0,0,.6));}
.page-full figcaption{right:0;padding:6mm 8mm;font-size:12px;letter-spacing:.06em;}
.page-grid{padding:14mm;display:grid;gap:8mm;}
.g-duo{grid-template-columns:1fr;grid-template-rows:1fr 1fr;} .g-trio{grid-template-columns:1fr 1fr;}
.g-trio figure:first-child{grid-column:1 / -1;} .g-quad{grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;}
.page-grid figure{margin:0;position:relative;overflow:hidden;min-height:0;} .page-grid img{width:100%;height:100%;display:block;}
.page-grid figcaption{padding:3mm 4mm;font-size:9.5px;letter-spacing:.05em;}
/* Recadrage par image : cover (remplit, rogne) vs contain (entier, marges) */
figure.fit-cover img{object-fit:cover;} figure.fit-contain img{object-fit:contain;background:#efece6;}
"""


def render_model(model: dict) -> tuple[Path, dict]:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    meta = _meta_index()
    pages = model.get("pages", [])
    body = "".join(_render_page(pg, meta) for pg in pages)
    html = (f'<!doctype html><html lang="fr"><head><meta charset="utf-8" />'
            f'<title>{_escape(model.get("title","Artbook"))}</title><style>{CSS}</style></head>'
            f'<body>{body}</body></html>')
    out = EXPORTS_DIR / f"artbook-{_slugify(model.get('title','artbook'))}-{datetime.now():%Y%m%d-%H%M%S}.html"
    out.write_text(html, encoding="utf-8")
    n_photos = sum(len(p.get("items", [])) for p in pages if p.get("tpl") in IMAGE_TPLS)
    return out, {"pages": len(pages), "photos": n_photos}


# Compat : génère + rend en une passe (ancien point d'entrée).
def build_artbook(paths, title="Iris Artbook", subtitle="", chapter_by="category"):
    model = compose_model(paths, title, subtitle, chapter_by)
    save_model(model)
    return render_model(model)
