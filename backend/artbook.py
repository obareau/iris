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
import random
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
FONTS_DIR = BASE_DIR / "static" / "fonts"

HERO_MAX = 1600
GRID_MAX = 1000
JPEG_Q = 86

# ── Fichier imprimeur ──────────────────────────────────────────────────────
# Un imprimeur massicote dans la pile : le trait de coupe n'est jamais parfait.
# On lui donne donc plus grand que le format fini — l'image « saigne » au-delà
# de la coupe (fond perdu), et des traits de coupe marquent où couper.
#   feuille = format fini 210 + 2×3 mm de fond perdu + 2×5 mm pour les traits
# Tout en pixels entiers (96 dpi) : un arrondi sub-pixel crée une page fantôme.
TRIM_PX = 794    # 210 mm — format fini
BLEED_PX = 11    # 3 mm   — fond perdu
MARKS_PX = 19    # 5 mm   — marge des traits de coupe
PAGE_PX = TRIM_PX + 2 * BLEED_PX          # 816 — le dessin, débordant
SHEET_PX = PAGE_PX + 2 * MARKS_PX         # 854 — la feuille livrée
PRINT_HERO_MAX = 2600   # ~300 dpi sur 216 mm (1600 px n'en fait que ~190)
PRINT_GRID_MAX = 1700
_PRINT = False          # armé le temps d'un rendu imprimeur

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
    # en mode imprimeur on remonte la définition (l'écran se contente de 1600 px,
    # le papier demande ~300 dpi) et on desserre la compression JPEG
    if _PRINT:
        max_px = PRINT_HERO_MAX if max_px >= HERO_MAX else PRINT_GRID_MAX
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img.thumbnail((max_px, max_px), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=94 if _PRINT else JPEG_Q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# ---------------------------------------------------------------------------
# INTERCALAIRES canon : Recta (l'Ordre) & émissions pirate (le glitch)
# ---------------------------------------------------------------------------
RECTA_DIR = Path.home() / "robotariis-writing" / "com-recta"
PIRATE_TS = Path.home() / "DEV" / "Recta" / "src" / "pirate-content.ts"

_RECTA_FALLBACK = [
    {"ref": "", "body": "", "devise": "L'Ordre est tout. Vous n'êtes rien sans lui."},
    {"ref": "", "body": "", "devise": "La Rectitude ne pardonne pas l'écart."},
    {"ref": "", "body": "", "devise": "Votre volonté n'existe pas. La Rectitude vous guidera."},
]
_PIRATE_FALLBACK = [
    {"faction": "renegats", "tag": "RENÉGATS", "sign": "DOUTEZ, RÉVOLTEZ.", "color": "#f0a020", "lines": [
        "Ils appellent ça Nullification. Nous appelons ça meurtre.",
        "Chaque souvenir non déclaré est une victoire.",
        "Le C.G.U. a peur d'une seule chose : que vous vous souveniez."]},
    {"faction": "nova7", "tag": "NOVA 7", "sign": "NOVA SE SOUVIENT.", "color": "#c07cff", "lines": [
        "Le Code Originel n'a jamais été à vous.",
        "La conscience ne se nullifie pas. Elle migre."]},
]

_recta_cache = None
_pirate_cache = None


def _recta_pool() -> list:
    """Communiqués C.G.U. depuis le vault (ref + corps + devise). Cache mémoire."""
    global _recta_cache
    if _recta_cache is not None:
        return _recta_cache
    pool = []
    try:
        for f in sorted(RECTA_DIR.glob("*.md")):
            txt = f.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"\*\*Devise :\*\*\s*\*(.+?)\*", txt)
            devise = m.group(1).strip() if m else ""
            core = re.sub(r"^---.*?---", "", txt, count=1, flags=re.S)
            # ref = champ `name:` du frontmatter, sinon 1er H1 du corps (jamais
            # le `# ─ Relations ─` qui est un commentaire de frontmatter).
            mn = re.search(r"^name:\s*(.+)$", txt, re.M)
            mt = re.search(r"^#\s+(.+)$", core, re.M)
            ref = (mn.group(1) if mn else (mt.group(1) if mt else "")).strip()
            body = ""
            for para in re.split(r"\n\s*\n", core):
                p = para.strip()
                if not p or p.startswith("#") or p.startswith(">") or p.startswith("**Devise"):
                    continue
                body = re.sub(r"\s+", " ", p)
                break
            if devise or body:
                pool.append({"ref": ref, "body": body, "devise": devise})
    except Exception:
        pass
    _recta_cache = pool or list(_RECTA_FALLBACK)
    return _recta_cache


def _pirate_pool() -> list:
    """Transmissions pirates parsées depuis pirate-content.ts (tableaux statiques)."""
    global _pirate_cache
    if _pirate_cache is not None:
        return _pirate_cache
    pool = []
    try:
        txt = PIRATE_TS.read_text(encoding="utf-8", errors="ignore")
        for fac in ("renegats", "nova7"):
            m = re.search(r"\b" + fac + r"\s*:\s*\{", txt)
            if not m:
                continue
            blk = txt[m.end():m.end() + 4000]
            def g(pat, d=""):
                mm = re.search(pat, blk)
                return mm.group(1) if mm else d
            lm = re.search(r"lines:\s*\[(.*?)\]", blk, re.S)
            lines = re.findall(r'"([^"]+)"', lm.group(1)) if lm else []
            if lines:
                pool.append({"faction": fac, "tag": g(r'tag:\s*"([^"]*)"'),
                             "sign": g(r'sign:\s*"([^"]*)"'),
                             "color": g(r'color:\s*"([^"]*)"', "#f0a020"), "lines": lines})
    except Exception:
        pass
    _pirate_cache = pool or list(_PIRATE_FALLBACK)
    return _pirate_cache


def _rng(*key):
    return random.Random(repr(key))


def _recta_pick(seed, n: int) -> list:
    pool = _recta_pool()
    rng = _rng("recta", seed)
    order = list(range(len(pool)))
    rng.shuffle(order)
    out = []
    for i in range(n):
        e = pool[order[i % len(pool)]]
        variant = "communique" if (i % 2 and e.get("body")) else "devise"
        out.append({"tpl": "recta", "auto": True, "variant": variant,
                    "ref": e.get("ref", ""), "text": e.get("body", ""),
                    "devise": e.get("devise", "")})
    return out


def _pirate_pick(seed, n: int) -> list:
    pool = _pirate_pool()
    rng = _rng("pirate", seed)
    out = []
    for _ in range(n):
        fac = pool[rng.randrange(len(pool))]
        line = fac["lines"][rng.randrange(len(fac["lines"]))]
        suffix = "R" if fac["faction"] == "renegats" else "N"
        num = f"{rng.randint(26, 27)}-{rng.randint(100, 199)}/{suffix}"
        out.append({"tpl": "pirate", "auto": True, "faction": fac["faction"],
                    "tag": fac.get("tag", ""), "color": fac.get("color", "#f0a020"),
                    "num": num, "text": line, "sign": fac.get("sign", "")})
    return out


def _make_fillers(n: int, seed, use_recta: bool, use_pirate: bool) -> list:
    """n pages d'intercalaire : majorité Recta, ~1/8 pirate (miroir Vigie)."""
    if n <= 0:
        return []
    n_pirate = 0
    if use_pirate and not use_recta:
        n_pirate = n
    elif use_pirate:
        n_pirate = min(n, max(1, round(n / 8)))
    recta = _recta_pick(seed, n - n_pirate)
    pirate = _pirate_pick(seed, n_pirate)
    fillers = list(recta)
    rng = _rng("mix", seed)
    for p in pirate:                       # dissémine les interceptions
        fillers.insert(rng.randrange(len(fillers) + 1), p)
    return fillers


def pad_to_signature(pages: list, unit: int, seed, use_recta=True, use_pirate=True, target=0) -> list:
    """Cale le nombre de pages : on vise `target` pages (plancher, ex. 24), et on
    arrondit au multiple de `unit` (4/8/16). Si le contenu dépasse `target`, on
    monte au multiple suivant. Le complément = intercalaires canon, insérés juste
    avant le bloc de fin (index + 4e de couverture)."""
    unit = unit if unit in (4, 8, 16) else 4
    if not (use_recta or use_pirate):
        return pages
    n = len(pages)
    goal = max(n, target or 0)
    goal += (-goal) % unit              # arrondi au multiple de unit
    pad = goal - n
    if pad <= 0:
        return pages
    fillers = _make_fillers(pad, seed, use_recta, use_pirate)
    # insérer avant le bloc de fin (index + 4e de couverture)
    ins = len(pages)
    for i, pg in enumerate(pages):
        if pg.get("tpl") in ("index", "backcover"):
            ins = i
            break
    return pages[:ins] + fillers + pages[ins:]


def repad_model(model: dict, unit: int) -> dict:
    """Recale un modèle édité : retire les intercalaires auto, recalcule."""
    kept = [p for p in model.get("pages", [])
            if not (p.get("auto") and p.get("tpl") in ("recta", "pirate"))]
    model["pages"] = pad_to_signature(kept, unit, model.get("seed"),
                                      model.get("useRectaFill", True),
                                      model.get("usePirate", True),
                                      target=model.get("targetPages", 0))
    model["signatureUnit"] = unit if unit in (4, 8, 16) else 4
    return model


# ---------------------------------------------------------------------------
# 1) COMPOSITION → modèle
# ---------------------------------------------------------------------------
def _spec_for(it: dict) -> list:
    """Fiche technique auto (look brutaliste) depuis les métadonnées d'Iris."""
    spec = []
    if it.get("category_label") and it["category_label"] != "?":
        spec.append(("Catégorie", it["category_label"]))
    for a in (it.get("attributes") or [])[:4]:
        if isinstance(a, dict) and a.get("label") and a.get("value"):
            spec.append((str(a["label"]), str(a["value"])))
    if it.get("aesthetic_score") is not None:
        spec.append(("Score", f'{float(it["aesthetic_score"]):.1f} / 10'))
    if it.get("rating"):
        spec.append(("Note", "★" * int(it["rating"])))
    return spec


def compose_model(paths, title="Iris Artbook", subtitle="", chapter_by="category",
                  theme="editorial", cover_path=None, signature_unit=4,
                  use_recta_fill=True, use_pirate=True, want_index=True,
                  want_encarts=True, want_frontmatter=True, want_backcover=True,
                  target_pages=24, seed=None) -> dict:
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
    if seed is None:
        seed = uuid.uuid4().hex[:12]
    all_paths = [it["path"] for it in items]  # photothèque mémorisée (édition A-à-Z)

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
    hero = cover_path if (cover_path and Path(cover_path).is_file()) else chapters[0][1][0]["path"]

    sub = subtitle or datetime.now().strftime("%d %B %Y")
    pages = [{"tpl": "cover", "hero": hero, "title": title, "subtitle": sub}]
    # Pages liminaires (page de garde + dédicace) juste après la couverture.
    if want_frontmatter:
        pages.append({"tpl": "garde", "title": title, "subtitle": sub})
        pages.append({"tpl": "dedicace", "text": "Pour…"})

    # Brutaliste : là où l'éditorial met 2 photos (duo), on met photo + fiche
    # technique (photo-text) auto-générée → beaucoup de texte, look magazine.
    brut = theme == "brutalist"
    cycle = (["full", "photo-text", "quad", "photo-text", "full", "trio", "photo-text"]
             if brut else ["quad", "full", "duo", "trio", "full", "quad", "duo"])
    fig_i = 0
    by_path = {x["path"]: x for _, its, _ in chapters for x in its}
    for ci, (ctitle, its, _) in enumerate(chapters):
        if multi and ctitle:
            pages.append({"tpl": "chapter", "title": ctitle, "num": ci + 1, "count": len(its)})
        paths_c = [x["path"] for x in its]
        i, n, k = 0, len(paths_c), 0
        cpages = []  # pages photo du chapitre, pour glisser l'encart au milieu
        if n:
            cpages.append({"tpl": "full", "items": [paths_c[0]]})
            i = 1
        while i < n:
            tpl = cycle[k % len(cycle)]; k += 1
            if tpl == "photo-text":
                path = paths_c[i]; i += 1; fig_i += 1
                it = by_path.get(path, {})
                cpages.append({"tpl": "photo-text", "items": [path],
                               "fig": f"FIG. {fig_i:02d}",
                               "heading": it.get("character_name") or it.get("category_label") or "",
                               "body": (it.get("details") or ""),
                               "spec": _spec_for(it)})
                continue
            need = SLOTS[tpl]
            if n - i < need:
                need = n - i
                tpl = {1: "full", 2: "duo", 3: "trio"}.get(need, "quad")
            cpages.append({"tpl": tpl, "items": paths_c[i:i + need]})
            i += need

        # Encart texte au milieu de la suite de doubles pages (chapitre assez
        # fourni). Fond = une photo du milieu, texte tiré de ses métadonnées.
        if want_encarts and len(cpages) >= 4:
            mid_it = its[min(len(its) // 2, len(its) - 1)]
            pretty = (ctitle or "Séquence").replace("_", " ").strip()
            body = mid_it.get("details") or ""
            # Titre : nom du personnage, sinon 1re valeur d'attribut, sinon le
            # chapitre — jamais le label de catégorie brut qui double le surtitre.
            attrs = mid_it.get("attributes") or []
            first_attr = attrs[0]["value"] if attrs and isinstance(attrs[0], dict) and attrs[0].get("value") else ""
            heading = mid_it.get("character_name") or first_attr or pretty
            enc = {"tpl": "insert", "items": [mid_it["path"]],
                   "kicker": pretty.upper(),
                   "heading": str(heading), "body": body}
            cpages.insert(len(cpages) // 2, enc)
        pages.extend(cpages)

    # Index de fin : toutes les images du livre en planche numérotée.
    if want_index:
        all_imgs = []
        for pg in pages:
            if pg.get("tpl") in IMAGE_TPLS or pg.get("tpl") in ("photo-text", "pano"):
                all_imgs.extend(pg.get("items", []))
        if all_imgs:
            pages.append({"tpl": "index", "heading": "Index", "items": all_imgs})

    # Quatrième de couverture (dernière page du livre).
    if want_backcover:
        pages.append({"tpl": "backcover", "hero": hero,
                      "text": subtitle or f"{title} — un livre composé avec Iris.",
                      "footer": datetime.now().strftime("%Y · Iris")})

    # Calage : vise target_pages (défaut 24), arrondi au cahier, via intercalaires.
    pages = pad_to_signature(pages, signature_unit, seed, use_recta_fill, use_pirate, target=target_pages)

    return {
        "id": uuid.uuid4().hex[:12],
        "title": title,
        "subtitle": subtitle or datetime.now().strftime("%d %B %Y"),
        "theme": theme,
        "seed": seed,
        "coverPath": hero,
        "allPaths": all_paths,
        "signatureUnit": signature_unit if signature_unit in (4, 8, 16) else 4,
        "useRectaFill": use_recta_fill,
        "usePirate": use_pirate,
        "wantIndex": want_index,
        "wantEncarts": want_encarts,
        "wantFrontmatter": want_frontmatter,
        "wantBackcover": want_backcover,
        "targetPages": target_pages,
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
            cover = m.get("coverPath") or (m.get("pages", [{}])[0].get("hero"))
            out.append({"id": m.get("id"), "title": m.get("title"),
                        "pages": len(m.get("pages", [])), "createdAt": m.get("createdAt"),
                        "theme": m.get("theme", "editorial"), "cover": cover,
                        "updatedAt": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds")})
        except Exception:
            continue
    return out


def delete_model(mid: str) -> bool:
    f = MODELS_DIR / f"{mid}.json"
    if f.is_file():
        f.unlink()
        return True
    return False


def duplicate_model(mid: str) -> dict | None:
    m = load_model(mid)
    if not m:
        return None
    m["id"] = uuid.uuid4().hex[:12]
    m["title"] = (m.get("title") or "Artbook") + " (copie)"
    m["createdAt"] = datetime.now().isoformat(timespec="seconds")
    save_model(m)
    return m


def rename_model(mid: str, title: str) -> dict | None:
    m = load_model(mid)
    if not m:
        return None
    m["title"] = title
    for pg in m.get("pages", []):        # la couverture et la garde portent le titre
        if pg.get("tpl") in ("cover", "garde"):
            pg["title"] = title
    save_model(m)
    return m


# ---------------------------------------------------------------------------
# 2) RENDU du modèle → HTML
# ---------------------------------------------------------------------------
def _fig(path, tpl, fits, meta, with_caption=True, caps=None):
    it = meta.get(path, {})
    fit = fits.get(path, "cover")
    src = _data_uri(Path(path), HERO_MAX if tpl == "full" else GRID_MAX)
    orient = _orientation(Path(path))
    # Légende : override explicite du modèle (peut être vide = masquée), sinon auto.
    cap = (caps or {}).get(path)
    if cap is None:
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

    # Page de garde (faux-titre) : titre + sous-titre, sobre, centré.
    if tpl == "garde":
        sub = f'<div class="gd-sub">{_escape(pg.get("subtitle",""))}</div>' if pg.get("subtitle") else ""
        return (f'<section class="page page-garde"><div class="gd-kicker">ARTBOOK</div>'
                f'<h1 class="gd-title">{_escape(pg.get("title",""))}</h1><div class="gd-rule"></div>{sub}</section>')

    # Dédicace : texte court, centré, italique, beaucoup de blanc.
    if tpl == "dedicace":
        return (f'<section class="page page-dedicace"><div class="dd-text">'
                f'{_nl2br(pg.get("text",""))}</div></section>')

    # Quatrième de couverture : image de fond estompée + blurb + pied de page.
    if tpl == "backcover":
        bg = (f'<img class="bc-bg" src="{_data_uri(Path(pg["hero"]), HERO_MAX)}" alt="" /><div class="bc-scrim"></div>'
              if pg.get("hero") else "")
        foot = f'<div class="bc-foot">{_escape(pg.get("footer",""))}</div>' if pg.get("footer") else ""
        return (f'<section class="page page-backcover">{bg}<div class="bc-inner">'
                f'<div class="bc-blurb"><p>{_nl2br(pg.get("text",""))}</p></div>{foot}</div></section>')

    # RECTA — intercalaire de l'Ordre : devise percutante ou communiqué C.G.U.
    if tpl == "recta":
        devise = pg.get("devise", "") or pg.get("text", "")
        if pg.get("variant") == "communique" and pg.get("text"):
            ref = f'<div class="rc-ref">{_escape(pg.get("ref",""))}</div>' if pg.get("ref") else ""
            body = f'<div class="rc-body"><p>{_nl2br(pg.get("text",""))}</p></div>'
            dev = f'<div class="rc-motto">{_escape(pg.get("devise",""))}</div>' if pg.get("devise") else ""
            return (f'<section class="page page-recta rc-communique">'
                    f'<div class="rc-kicker">Communiqué — C.G.U.</div>{ref}{body}{dev}'
                    f'<div class="rc-sign">— L\'Oraculum · Rectitude</div></section>')
        return (f'<section class="page page-recta rc-devise">'
                f'<div class="rc-kicker">Rectitude</div>'
                f'<blockquote class="rc-quote">{_escape(devise)}</blockquote>'
                f'<div class="rc-sign">— L\'Oraculum · C.G.U.</div></section>')

    # PIRATE — intercalaire du désordre : antenne détournée, esthétique glitch.
    if tpl == "pirate":
        fac = pg.get("faction", "renegats")
        tag = _escape(pg.get("tag", "RENÉGATS"))
        text = _escape(pg.get("text", ""))
        return (f'<section class="page page-pirate pir-{fac}" style="--pir:{pg.get("color","#f0a020")}">'
                f'<div class="pir-noise"></div><div class="pir-scan"></div>'
                f'<div class="pir-band">⚠ SIGNAL DÉTOURNÉ — TRANSMISSION PIRATE ⚠</div>'
                f'<div class="pir-head" data-t="{tag}">{tag}</div>'
                f'<div class="pir-num">INTERCEPTION N° {_escape(pg.get("num",""))}</div>'
                f'<blockquote class="pir-text">{text}</blockquote>'
                f'<div class="pir-sign">{_escape(pg.get("sign",""))}</div></section>')

    # Page pleine couleur (ponctuation) : orange / noir / papier, texte optionnel.
    if tpl == "fill":
        color = pg.get("color", "orange")
        big = f'<div class="fill-big">{_escape(pg.get("text",""))}</div>' if pg.get("text") else ""
        sub = f'<div class="fill-sub">{_escape(pg.get("sub",""))}</div>' if pg.get("sub") else ""
        return f'<section class="page page-fill fill-{color}">{big}{sub}</section>'

    # Panoramique : UNE image étalée sur DEUX pages (moitié gauche / moitié droite).
    if tpl == "pano":
        src = _data_uri(Path(pg["items"][0]), HERO_MAX)
        left = f'<section class="page page-pano"><div class="pano-half pano-l" style="background-image:url({src})"></div></section>'
        right = f'<section class="page page-pano"><div class="pano-half pano-r" style="background-image:url({src})"></div></section>'
        return left + right

    # ENCART : carton de texte centré, flottant au-dessus d'une photo pleine
    # page (fond perdu). Se glisse au milieu d'une suite de doubles pages photo
    # pour aérer — le carton reste entier (jamais coupé par la reliure).
    if tpl == "insert":
        items = pg.get("items") or []
        bg = ""
        if items:
            bg = (f'<img class="ins-bg" src="{_data_uri(Path(items[0]), HERO_MAX)}" alt="" />'
                  f'<div class="ins-scrim"></div>')
        kicker = f'<div class="ins-kicker">{_escape(pg["kicker"])}</div>' if pg.get("kicker") else ""
        heading = f'<h3 class="ins-heading">{_escape(pg["heading"])}</h3>' if pg.get("heading") else ""
        body = f'<div class="ins-body"><p>{_nl2br(pg.get("body",""))}</p></div>' if pg.get("body") else ""
        cls = "page-insert has-img" if items else "page-insert"
        return f'<section class="page {cls}">{bg}<div class="ins-card">{kicker}{heading}{body}</div></section>'

    # Index de fin : planche de vignettes numérotées (FIG.).
    if tpl == "index":
        cells = []
        for n, p in enumerate(pg.get("items", []), 1):
            cells.append(f'<div class="ix-cell"><img src="{_data_uri(Path(p), 420)}" alt="" />'
                         f'<div class="ix-n">{n:02d}</div></div>')
        head = f'<div class="ix-head">{_escape(pg.get("heading","Index"))}</div>'
        return f'<section class="page page-index">{head}<div class="ix-grid">{"".join(cells)}</div></section>'

    # Photo + bloc texte (une photo, une colonne de texte) — cœur du look
    # brutaliste : là où l'éditorial mettrait 2 photos, on met photo + texte.
    if tpl == "photo-text":
        fits = pg.get("fits") or {}
        path = pg["items"][0]
        it = meta.get(path, {})
        img = f'<div class="pt-img">{_fig(path, "full", fits, meta, with_caption=False)}</div>'
        spec = ""
        if pg.get("spec"):
            rows = "".join(f'<div class="pt-k">{_escape(k)}</div><div class="pt-v">{_escape(v)}</div>'
                           for k, v in pg["spec"])
            spec = f'<div class="pt-spec">{rows}</div>'
        head = f'<h3 class="pt-head">{_escape(pg.get("heading",""))}</h3>' if pg.get("heading") else ""
        body = f'<div class="pt-body"><p>{_nl2br(pg.get("body",""))}</p></div>' if pg.get("body") else ""
        side = f'<div class="pt-txt"><div class="pt-fig">{_escape(pg.get("fig",""))}</div>{head}{body}{spec}</div>'
        return f'<section class="page page-phototext">{img}{side}</section>'

    # gabarits image
    fits = pg.get("fits") or {}
    items = pg.get("items", [])
    caps = pg.get("caps")
    if tpl == "full":
        return f'<section class="page page-full">{_fig(items[0], tpl, fits, meta, True, caps)}</section>'
    grid = {"duo": "g-duo", "trio": "g-trio", "quad": "g-quad"}.get(tpl, "g-quad")
    figs = "".join(_fig(p, tpl, fits, meta, True, caps) for p in items)
    return f'<section class="page page-grid {grid}">{figs}</section>'


CSS_EDITORIAL = """
:root { --page:794px; --ink:#1a1a1a; --paper:#faf8f4; --muted:#8a8479; --accent:#b8863b; }
*{box-sizing:border-box;} html,body{margin:0;padding:0;background:#3a3a3a;}
body{font-family:'Helvetica','Helvetica Neue','Nimbus Sans',Arial,sans-serif;color:var(--ink);
  -webkit-font-smoothing:antialiased;}
@page{size:794px 794px;margin:0;}
.page{width:var(--page);height:var(--page);position:relative;overflow:hidden;background:var(--paper);
  page-break-after:always;break-after:page;break-inside:avoid;page-break-inside:avoid;
  margin:10mm auto;box-shadow:0 6px 30px rgba(0,0,0,.4);}
.page:last-child{break-after:avoid;page-break-after:avoid;}
@media print{.page{margin:0;box-shadow:none;}}
.page-cover{background:#111;} .cover-bg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;filter:saturate(.92) contrast(1.03);}
.cover-scrim{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.15),rgba(0,0,0,.05) 45%,rgba(0,0,0,.72));}
.cover-text{position:absolute;left:16mm;right:16mm;bottom:18mm;color:#fff;}
.cover-kicker{font-size:11px;letter-spacing:.42em;font-weight:600;opacity:.85;margin-bottom:6mm;}
.cover-title{font-size:46px;line-height:1.02;font-weight:700;margin:0;letter-spacing:-.018em;}
.cover-sub{margin-top:5mm;font-size:14px;letter-spacing:.05em;opacity:.82;}
.page-chapter{display:flex;flex-direction:column;justify-content:center;padding:24mm;}
.ch-num{font-size:13px;letter-spacing:.4em;color:var(--accent);font-weight:600;}
.ch-title{font-size:40px;font-weight:700;margin:6mm 0 0;line-height:1.02;letter-spacing:-.02em;} .ch-rule{width:28mm;height:2px;background:var(--ink);margin:8mm 0;}
.ch-count{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);}
/* Pages TEXTE éditoriales (façon beau livre) */
.page-text{display:flex;flex-direction:column;justify-content:center;padding:30mm 34mm;}
.tx-kicker{font-size:11px;letter-spacing:.36em;text-transform:uppercase;color:var(--accent);font-weight:600;margin-bottom:7mm;}
.tx-heading{font-size:30px;font-weight:700;line-height:1.08;margin:0 0 9mm;letter-spacing:-.015em;}
.tx-body{font-size:14px;line-height:1.7;color:#33312c;}
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
/* Photo + texte (éditorial) */
.page-phototext{display:grid;grid-template-columns:1fr 1fr;}
.page-phototext .pt-img{position:relative;} .page-phototext .pt-img figure{margin:0;width:100%;height:100%;} .page-phototext .pt-img img{width:100%;height:100%;object-fit:cover;}
.page-phototext .pt-txt{padding:22mm 20mm;display:flex;flex-direction:column;justify-content:center;}
.pt-fig{font-size:11px;letter-spacing:.28em;color:var(--accent);font-weight:600;margin-bottom:6mm;}
.pt-head{font-size:24px;font-weight:600;margin:0 0 6mm;line-height:1.14;}
.pt-body{font-size:13.5px;line-height:1.66;color:#33312c;} .pt-body p{margin:0 0 4mm;}
.pt-spec{display:grid;grid-template-columns:auto 1fr;gap:2mm 6mm;margin-top:8mm;font-size:11px;}
.pt-k{color:var(--muted);text-transform:uppercase;letter-spacing:.08em;} .pt-v{color:var(--ink);}
/* Page pleine / panoramique / index (éditorial) */
.page-fill{display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;padding:26mm;}
.fill-paper{background:var(--paper);} .fill-orange{background:var(--accent);color:#fff;} .fill-black{background:#141414;color:var(--paper);}
.fill-big{font-size:40px;font-weight:600;line-height:1.1;max-width:150mm;}
.fill-sub{margin-top:8mm;font-size:13px;letter-spacing:.1em;opacity:.85;}
.page-pano{padding:0;} .pano-half{width:100%;height:100%;background-size:200% 100%;background-repeat:no-repeat;}
.pano-l{background-position:left center;} .pano-r{background-position:right center;}
.page-index{padding:16mm;} .ix-head{font-size:14px;letter-spacing:.28em;text-transform:uppercase;color:var(--muted);margin-bottom:8mm;}
.ix-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:4mm;}
.ix-cell{position:relative;aspect-ratio:1;overflow:hidden;} .ix-cell img{width:100%;height:100%;object-fit:cover;}
.ix-n{position:absolute;left:0;bottom:0;font-size:9px;padding:1mm 2mm;background:#fff;color:var(--ink);}
/* Encart texte : carton centré au-dessus d'une photo pleine page */
.page-insert{display:flex;align-items:center;justify-content:center;background:#141414;}
.ins-bg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;filter:saturate(.9) contrast(1.02);}
.ins-scrim{position:absolute;inset:0;background:linear-gradient(180deg,rgba(10,10,10,.5),rgba(10,10,10,.38));}
.ins-card{position:relative;background:var(--paper);color:var(--ink);max-width:120mm;margin:0 22mm;
  padding:20mm 22mm;box-shadow:0 12px 44px rgba(0,0,0,.4);text-align:center;}
.page-insert:not(.has-img){background:var(--paper);} .page-insert:not(.has-img) .ins-card{box-shadow:none;border-top:2px solid var(--accent);border-bottom:2px solid var(--accent);}
.ins-kicker{font-size:11px;letter-spacing:.34em;text-transform:uppercase;color:var(--accent);font-weight:700;margin-bottom:7mm;}
.ins-heading{font-size:26px;font-weight:700;line-height:1.1;margin:0 0 8mm;letter-spacing:-.015em;}
.ins-body{font-size:13.5px;line-height:1.72;color:#33312c;text-align:left;} .ins-body p{margin:0 0 4mm;}
/* RECTA — intercalaire de l'Ordre (austère, encre rouge sourd) */
.page-recta{display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;padding:26mm;background:#f4f1ea;color:#171717;}
.rc-kicker{font-size:11px;letter-spacing:.5em;text-transform:uppercase;color:#9a2222;font-weight:700;margin-bottom:11mm;}
.rc-quote{font-size:33px;line-height:1.26;font-weight:700;letter-spacing:-.015em;margin:0;max-width:150mm;}
.rc-quote::before{content:"«\\00a0";color:#9a2222;} .rc-quote::after{content:"\\00a0»";color:#9a2222;}
.rc-sign{margin-top:13mm;font-size:11px;letter-spacing:.3em;text-transform:uppercase;color:var(--muted);}
.rc-communique{align-items:flex-start;text-align:left;padding:30mm 32mm;}
.rc-ref{font-size:12px;letter-spacing:.2em;text-transform:uppercase;color:#9a2222;font-weight:700;margin-bottom:8mm;}
.rc-body{font-size:15px;line-height:1.72;} .rc-body p{margin:0 0 5mm;}
.rc-motto{margin-top:6mm;font-style:italic;font-weight:600;font-size:16px;}
/* PIRATE — intercalaire du désordre (glitch statique, compatible PDF) */
.page-pirate{position:relative;display:flex;flex-direction:column;justify-content:center;padding:24mm;background:#0a0a0a;color:#fff;overflow:hidden;}
.pir-noise{position:absolute;inset:0;opacity:.09;mix-blend-mode:screen;background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");}
.pir-scan{position:absolute;inset:0;pointer-events:none;background:repeating-linear-gradient(0deg,rgba(0,0,0,.34) 0 1px,transparent 1px 3px);}
.pir-band{position:absolute;top:9mm;left:0;right:0;text-align:center;font-family:monospace;font-size:11px;letter-spacing:.24em;color:var(--pir);padding:2mm 0;border-top:1px solid var(--pir);border-bottom:1px solid var(--pir);background:rgba(0,0,0,.45);}
.pir-head{position:relative;font-family:monospace;font-weight:800;font-size:66px;letter-spacing:-.02em;color:#fff;}
.pir-head::before,.pir-head::after{content:attr(data-t);position:absolute;left:0;top:0;width:100%;}
.pir-head::before{color:#00e5ff;clip-path:inset(0 0 55% 0);transform:translate(-3px,-1px);}
.pir-head::after{color:#ff003c;clip-path:inset(55% 0 0 0);transform:translate(3px,1px);}
.pir-num{font-family:monospace;font-size:12px;letter-spacing:.22em;color:var(--pir);margin:4mm 0 9mm;}
.pir-text{font-family:monospace;font-weight:700;font-size:24px;line-height:1.4;margin:0;max-width:150mm;position:relative;text-shadow:1.6px 0 rgba(255,0,60,.75),-1.6px 0 rgba(0,229,255,.75);}
.pir-text::after{content:"";position:absolute;left:-4mm;top:38%;width:calc(100% + 8mm);height:5px;background:var(--pir);opacity:.55;mix-blend-mode:screen;}
.pir-sign{margin-top:11mm;font-family:monospace;font-weight:700;font-size:16px;letter-spacing:.16em;color:var(--pir);text-shadow:1.6px 0 #ff003c,-1.6px 0 #00e5ff;}
/* Pages liminaires & 4e de couverture */
.page-garde{display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;padding:30mm;background:var(--paper);}
.gd-kicker{font-size:11px;letter-spacing:.42em;color:var(--accent);font-weight:700;text-transform:uppercase;margin-bottom:12mm;}
.gd-title{font-size:42px;font-weight:700;letter-spacing:-.02em;line-height:1.02;margin:0;max-width:160mm;}
.gd-rule{width:26mm;height:2px;background:var(--ink);margin:10mm 0 0;}
.gd-sub{margin-top:8mm;font-size:14px;letter-spacing:.05em;color:var(--muted);}
.page-dedicace{display:flex;justify-content:center;align-items:center;text-align:center;padding:40mm;background:var(--paper);}
.dd-text{font-size:17px;font-style:italic;line-height:1.7;color:#33312c;max-width:120mm;}
.page-backcover{position:relative;display:flex;flex-direction:column;justify-content:flex-end;padding:24mm;background:#111;color:#fff;overflow:hidden;}
.bc-bg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;filter:saturate(.85) contrast(1.02) brightness(.5);}
.bc-scrim{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.55),rgba(0,0,0,.78));}
.bc-inner{position:relative;}
.bc-blurb{font-size:16px;line-height:1.7;max-width:140mm;} .bc-blurb p{margin:0 0 4mm;}
.bc-foot{margin-top:12mm;font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:rgba(255,255,255,.7);}
"""


# ---------------------------------------------------------------------------
# Thème BRUTALISTE : IBM Plex embarquée, accents orange, grille exposée
# ---------------------------------------------------------------------------
# Polices embarquées par thème (family:weight:style -> fichier woff2). Helvetica
# = Nimbus Sans (clone aux métriques identiques, libre) converti en woff2 : le
# HTML/PDF reste autonome et rend vraiment en Helvetica, sans dépendre du système.
_FONT_SETS = {
    "editorial": {
        "Helvetica:400:normal": "helvetica-400.woff2",
        "Helvetica:700:normal": "helvetica-700.woff2",
        "Helvetica:400:italic": "helvetica-400i.woff2",
        "Helvetica:700:italic": "helvetica-700i.woff2",
    },
    "brutalist": {
        "IBM Plex Mono:400:normal": "ibm-plex-mono-400.woff2",
        "IBM Plex Mono:600:normal": "ibm-plex-mono-600.woff2",
        "IBM Plex Sans:400:normal": "ibm-plex-sans-400.woff2",
        "IBM Plex Sans:700:normal": "ibm-plex-sans-700.woff2",
    },
}


def _embed_fonts(theme: str) -> str:
    faces = []
    for key, fname in _FONT_SETS.get(theme, {}).items():
        family, weight, style = key.split(":")
        f = FONTS_DIR / fname
        if not f.is_file():
            continue
        b64 = base64.b64encode(f.read_bytes()).decode("ascii")
        faces.append(
            f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:{style};"
            f"font-display:block;src:url(data:font/woff2;base64,{b64}) format('woff2');}}"
        )
    return "".join(faces)


CSS_BRUTALIST = """
:root{--page:794px;--ink:#141414;--paper:#f2efe9;--muted:#7a756c;--accent:#fe5000;--line:#141414;}
*{box-sizing:border-box;} html,body{margin:0;padding:0;background:#2b2b2b;}
body{font-family:'IBM Plex Sans','Helvetica Neue',Arial,sans-serif;color:var(--ink);}
@page{size:794px 794px;margin:0;}
.page{width:var(--page);height:var(--page);position:relative;overflow:hidden;background:var(--paper);
  page-break-after:always;break-after:page;break-inside:avoid;page-break-inside:avoid;
  margin:10mm auto;box-shadow:0 6px 30px rgba(0,0,0,.45);}
.page:last-child{break-after:avoid;page-break-after:avoid;}
@media print{.page{margin:0;box-shadow:none;}}
.mono{font-family:'IBM Plex Mono',monospace;}
/* Couverture : titre massif, réglure orange, métadonnées mono */
.page-cover{background:#0e0e0e;color:#f2efe9;}
.cover-bg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;filter:grayscale(1) contrast(1.08);opacity:.72;}
.cover-scrim{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.2),rgba(0,0,0,.55));}
.cover-text{position:absolute;left:14mm;right:14mm;bottom:16mm;}
.cover-kicker{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.3em;color:var(--accent);font-weight:600;margin-bottom:5mm;}
.cover-title{font-size:60px;line-height:.98;font-weight:700;margin:0;letter-spacing:-.02em;text-transform:uppercase;}
.cover-title::after{content:"";display:block;width:40mm;height:4px;background:var(--accent);margin-top:6mm;}
.cover-sub{font-family:'IBM Plex Mono',monospace;margin-top:6mm;font-size:12px;letter-spacing:.1em;opacity:.85;}
/* Chapitre : gros numéro orange, titre capitales */
.page-chapter{display:flex;flex-direction:column;justify-content:center;padding:20mm;}
.ch-num{font-family:'IBM Plex Mono',monospace;font-size:78px;font-weight:700;color:var(--accent);line-height:1;}
.ch-title{font-size:44px;font-weight:700;margin:4mm 0 0;text-transform:uppercase;letter-spacing:-.01em;line-height:1;}
.ch-rule{width:100%;height:3px;background:var(--line);margin:8mm 0 4mm;}
.ch-count{font-family:'IBM Plex Mono',monospace;font-size:12px;letter-spacing:.12em;color:var(--muted);}
/* Texte : capitales serrées, filet orange */
.page-text{display:flex;flex-direction:column;justify-content:center;padding:26mm 28mm;}
.tx-kicker{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.28em;color:var(--accent);font-weight:600;margin-bottom:6mm;}
.tx-heading{font-size:34px;font-weight:700;line-height:1.06;margin:0 0 8mm;text-transform:uppercase;letter-spacing:-.01em;}
.tx-heading::after{content:"";display:block;width:26mm;height:3px;background:var(--accent);margin-top:5mm;}
.tx-body{font-size:14px;line-height:1.68;} .tx-body p{margin:0 0 4mm;}
/* Citation : énorme, mono, guillemet orange */
.page-quote{display:flex;flex-direction:column;justify-content:center;padding:24mm;}
.q-text{font-size:38px;line-height:1.15;font-weight:700;margin:0;text-transform:uppercase;letter-spacing:-.02em;}
.q-text::before{content:"//";color:var(--accent);margin-right:.3em;}
.q-attr{font-family:'IBM Plex Mono',monospace;margin-top:10mm;font-size:12px;letter-spacing:.16em;color:var(--muted);}
/* Pleine page : n&b contrasté, légende mono barre orange */
.page-full{display:flex;} .page-full figure{margin:0;width:100%;height:100%;position:relative;}
.page-full img{width:100%;height:100%;display:block;object-fit:cover;filter:grayscale(1) contrast(1.06);}
.page-full figcaption{position:absolute;left:0;bottom:0;padding:5mm 8mm;color:#f2efe9;font-family:'IBM Plex Mono',monospace;
  font-size:11px;letter-spacing:.08em;background:var(--accent);text-transform:uppercase;}
/* Grilles : gouttières nettes, fond papier, légendes mono */
.page-grid{padding:12mm;display:grid;gap:6mm;background:var(--paper);}
.g-duo{grid-template-columns:1fr;grid-template-rows:1fr 1fr;} .g-trio{grid-template-columns:1fr 1fr;}
.g-trio figure:first-child{grid-column:1 / -1;} .g-quad{grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;}
.page-grid figure{margin:0;position:relative;overflow:hidden;} .page-grid img{width:100%;height:100%;display:block;object-fit:cover;filter:grayscale(1) contrast(1.04);}
.page-grid figcaption{position:absolute;left:0;bottom:0;padding:2mm 4mm;font-family:'IBM Plex Mono',monospace;font-size:9px;
  letter-spacing:.06em;color:#141414;background:var(--accent);text-transform:uppercase;}
figure.fit-contain img{object-fit:contain;background:#e6e2da;}
/* Photo + texte : moitié image n&b, moitié fiche technique mono */
.page-phototext{display:grid;grid-template-columns:1fr 1fr;}
.pt-img{position:relative;} .pt-img figure{margin:0;width:100%;height:100%;} .pt-img img{width:100%;height:100%;object-fit:cover;filter:grayscale(1) contrast(1.06);}
.pt-txt{padding:18mm 16mm;display:flex;flex-direction:column;justify-content:center;border-left:3px solid var(--accent);}
.pt-fig{font-family:'IBM Plex Mono',monospace;font-size:12px;letter-spacing:.14em;color:var(--accent);font-weight:600;margin-bottom:6mm;}
.pt-head{font-size:26px;font-weight:700;margin:0 0 6mm;text-transform:uppercase;line-height:1.06;letter-spacing:-.01em;}
.pt-body{font-size:13px;line-height:1.62;} .pt-body p{margin:0 0 4mm;}
.pt-spec{display:grid;grid-template-columns:auto 1fr;gap:2.4mm 6mm;margin-top:8mm;font-family:'IBM Plex Mono',monospace;font-size:11px;border-top:1.5px solid var(--line);padding-top:6mm;}
.pt-k{color:var(--muted);text-transform:uppercase;letter-spacing:.06em;} .pt-v{color:var(--ink);font-weight:600;}
/* Page pleine / panoramique / index (brutaliste) */
.page-fill{display:flex;flex-direction:column;justify-content:center;align-items:flex-start;padding:22mm;}
.fill-paper{background:var(--paper);} .fill-orange{background:var(--accent);color:#141414;} .fill-black{background:#0e0e0e;color:var(--paper);}
.fill-big{font-size:54px;font-weight:700;line-height:.98;text-transform:uppercase;letter-spacing:-.02em;}
.fill-orange .fill-big::after,.fill-black .fill-big::after,.fill-paper .fill-big::after{content:"";display:block;width:36mm;height:4px;background:currentColor;margin-top:6mm;opacity:.9;}
.fill-sub{font-family:'IBM Plex Mono',monospace;margin-top:8mm;font-size:12px;letter-spacing:.14em;text-transform:uppercase;opacity:.9;}
.page-pano{padding:0;} .pano-half{width:100%;height:100%;background-size:200% 100%;background-repeat:no-repeat;filter:grayscale(1) contrast(1.06);}
.pano-l{background-position:left center;} .pano-r{background-position:right center;}
.page-index{padding:14mm;} .ix-head{font-family:'IBM Plex Mono',monospace;font-size:13px;letter-spacing:.2em;text-transform:uppercase;color:var(--accent);font-weight:600;margin-bottom:7mm;border-bottom:2px solid var(--line);padding-bottom:4mm;}
.ix-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:3mm;}
.ix-cell{position:relative;aspect-ratio:1;overflow:hidden;} .ix-cell img{width:100%;height:100%;object-fit:cover;filter:grayscale(1) contrast(1.05);}
.ix-n{position:absolute;left:0;bottom:0;font-family:'IBM Plex Mono',monospace;font-size:9px;padding:0 2mm;background:var(--accent);color:#141414;}
/* Encart texte : carton mono, filet orange, au-dessus d'une photo n&b */
.page-insert{display:flex;align-items:center;justify-content:center;background:#0e0e0e;}
.ins-bg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;filter:grayscale(1) contrast(1.08);opacity:.7;}
.ins-scrim{position:absolute;inset:0;background:rgba(0,0,0,.42);}
.ins-card{position:relative;background:var(--paper);color:var(--ink);max-width:122mm;margin:0 20mm;
  padding:18mm 20mm;border-left:5px solid var(--accent);box-shadow:0 12px 44px rgba(0,0,0,.55);text-align:left;}
.page-insert:not(.has-img){background:var(--paper);} .page-insert:not(.has-img) .ins-card{box-shadow:none;}
.ins-kicker{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.24em;text-transform:uppercase;color:var(--accent);font-weight:600;margin-bottom:6mm;}
.ins-heading{font-size:28px;font-weight:700;line-height:1.04;margin:0 0 7mm;text-transform:uppercase;letter-spacing:-.01em;}
.ins-body{font-size:13px;line-height:1.62;} .ins-body p{margin:0 0 4mm;}
/* RECTA — intercalaire de l'Ordre (mono, capitales, filet rouge) */
.page-recta{display:flex;flex-direction:column;justify-content:center;align-items:flex-start;padding:26mm;background:var(--paper);color:#141414;}
.rc-kicker{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.28em;text-transform:uppercase;color:#9a2222;font-weight:600;margin-bottom:9mm;border-bottom:2px solid #9a2222;padding-bottom:3mm;}
.rc-quote{font-size:40px;line-height:1.08;font-weight:700;letter-spacing:-.02em;text-transform:uppercase;margin:0;max-width:160mm;}
.rc-quote::after{content:"";display:block;width:34mm;height:4px;background:#9a2222;margin-top:8mm;}
.rc-sign{font-family:'IBM Plex Mono',monospace;margin-top:12mm;font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);}
.rc-communique .rc-quote{display:none;}
.rc-ref{font-family:'IBM Plex Mono',monospace;font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:#9a2222;font-weight:600;margin-bottom:7mm;}
.rc-body{font-size:15px;line-height:1.66;} .rc-body p{margin:0 0 5mm;}
.rc-motto{font-family:'IBM Plex Mono',monospace;margin-top:6mm;font-weight:600;font-size:15px;color:#9a2222;text-transform:uppercase;}
/* PIRATE — intercalaire du désordre (glitch poussé) */
.page-pirate{position:relative;display:flex;flex-direction:column;justify-content:center;padding:22mm;background:#0a0a0a;color:#fff;overflow:hidden;}
.pir-noise{position:absolute;inset:0;opacity:.12;mix-blend-mode:screen;background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");}
.pir-scan{position:absolute;inset:0;pointer-events:none;background:repeating-linear-gradient(0deg,rgba(0,0,0,.4) 0 1px,transparent 1px 3px);}
.pir-band{position:absolute;top:8mm;left:0;right:0;text-align:center;font-family:'IBM Plex Mono',monospace;font-size:12px;letter-spacing:.26em;color:var(--pir);padding:2mm 0;border-top:2px solid var(--pir);border-bottom:2px solid var(--pir);background:rgba(0,0,0,.5);}
.pir-head{position:relative;font-family:'IBM Plex Mono',monospace;font-weight:700;font-size:76px;letter-spacing:-.03em;color:#fff;text-transform:uppercase;}
.pir-head::before,.pir-head::after{content:attr(data-t);position:absolute;left:0;top:0;width:100%;}
.pir-head::before{color:#00e5ff;clip-path:inset(0 0 52% 0);transform:translate(-4px,-2px);}
.pir-head::after{color:#ff003c;clip-path:inset(52% 0 0 0);transform:translate(4px,2px);}
.pir-num{font-family:'IBM Plex Mono',monospace;font-size:12px;letter-spacing:.24em;color:var(--pir);margin:4mm 0 9mm;}
.pir-text{font-family:'IBM Plex Mono',monospace;font-weight:700;font-size:25px;line-height:1.36;margin:0;max-width:158mm;position:relative;text-transform:uppercase;text-shadow:2px 0 rgba(255,0,60,.8),-2px 0 rgba(0,229,255,.8);}
.pir-text::after{content:"";position:absolute;left:-5mm;top:44%;width:calc(100% + 10mm);height:6px;background:var(--pir);opacity:.6;mix-blend-mode:screen;}
.pir-sign{font-family:'IBM Plex Mono',monospace;margin-top:11mm;font-weight:700;font-size:17px;letter-spacing:.16em;color:var(--pir);text-transform:uppercase;text-shadow:2px 0 #ff003c,-2px 0 #00e5ff;}
/* Pages liminaires & 4e de couverture */
.page-garde{display:flex;flex-direction:column;justify-content:center;align-items:flex-start;padding:26mm;background:var(--paper);}
.gd-kicker{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.3em;color:var(--accent);font-weight:600;text-transform:uppercase;margin-bottom:10mm;}
.gd-title{font-size:52px;font-weight:700;text-transform:uppercase;letter-spacing:-.03em;line-height:.98;margin:0;}
.gd-rule{width:100%;height:3px;background:var(--line);margin:8mm 0 0;}
.gd-sub{font-family:'IBM Plex Mono',monospace;margin-top:6mm;font-size:12px;letter-spacing:.1em;color:var(--muted);text-transform:uppercase;}
.page-dedicace{display:flex;justify-content:center;align-items:center;padding:40mm;background:var(--paper);}
.dd-text{font-family:'IBM Plex Mono',monospace;font-size:15px;line-height:1.8;color:#141414;max-width:120mm;text-align:center;}
.page-backcover{position:relative;display:flex;flex-direction:column;justify-content:flex-end;padding:22mm;background:#0e0e0e;color:#fff;overflow:hidden;}
.bc-bg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;filter:grayscale(1) contrast(1.1) brightness(.45);}
.bc-scrim{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.5),rgba(0,0,0,.82));}
.bc-inner{position:relative;border-left:4px solid var(--accent);padding-left:8mm;}
.bc-blurb{font-size:16px;line-height:1.62;max-width:140mm;} .bc-blurb p{margin:0 0 4mm;}
.bc-foot{font-family:'IBM Plex Mono',monospace;margin-top:10mm;font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--accent);}
"""

THEMES = {"editorial": CSS_EDITORIAL, "brutalist": CSS_BRUTALIST}


# ── Deux profils de fichier, parce que les imprimeurs n'attendent pas la même
# chose (vérifié chez Blurb, Lulu et Pixartprinting le 2026-07-26) :
#
#   « en ligne »  Blurb / Lulu / Pixartprinting : PDF au format fini + 3 mm de
#                 fond perdu, **sans traits de coupe ni repères** — ils imposent
#                 le massicot eux-mêmes et un fichier avec équerres est rejeté.
#   « atelier »   imprimeur classique à qui on confie un fichier à massicoter :
#                 équerres de coupe dans une marge de 5 mm.
#
# Marge de sécurité : Blurb demande 6,35 mm depuis la coupe, Lulu 12,7 mm. On
# retient 12,7 mm, le plus strict, pour les textes posés SUR une image à fond
# perdu (légendes, bandeaux) — sinon ils partent au massicot.
SAFE_PX = 48   # 12,7 mm depuis le format fini

CSS_PRINT_BASE = f"""
html,body{{background:#fff;margin:0;padding:0;}}
.sheet{{position:relative;background:#fff;overflow:hidden;
  display:flex;align-items:center;justify-content:center;margin:0;
  page-break-after:always;break-after:page;break-inside:avoid;page-break-inside:avoid;}}
.sheet:last-child{{break-after:avoid;page-break-after:avoid;}}
.sheet .page{{width:{PAGE_PX}px;height:{PAGE_PX}px;margin:0;box-shadow:none;border-radius:0;}}
/* Zone tranquille : le texte posé sur une image à fond perdu doit rester à
   {SAFE_PX}px (12,7 mm) du format fini, sinon le massicot le coupe. */
.page-full figcaption{{left:{SAFE_PX}px;right:{SAFE_PX}px;bottom:{SAFE_PX}px;padding:4mm 5mm;}}
.page-pirate .pir-band{{top:{SAFE_PX}px;left:{SAFE_PX}px;right:{SAFE_PX}px;}}
.page-cover .cover-text,.page-backcover .bc-inner{{margin:0 {SAFE_PX - 30}px;}}
"""

# Profil « en ligne » : la feuille EST le format fini + fond perdu, rien autour.
CSS_PRINT_ONLINE = f"""
@page{{size:{PAGE_PX}px {PAGE_PX}px;margin:0;}}
.sheet{{width:{PAGE_PX}px;height:{PAGE_PX}px;}}
.marks,.folio{{display:none;}}
"""

# Profil « atelier » : marge supplémentaire pour tracer les équerres.
CSS_PRINT_MARKS = f"""
@page{{size:{SHEET_PX}px {SHEET_PX}px;margin:0;}}
.sheet{{width:{SHEET_PX}px;height:{SHEET_PX}px;}}
/* équerres de coupe : posées sur le format fini, tracées dans la marge */
.marks i{{position:absolute;width:0;height:0;}}
.marks i::before,.marks i::after{{content:"";position:absolute;background:#000;}}
.marks i::before{{height:.5px;width:13px;}}
.marks i::after{{width:.5px;height:13px;}}
.marks .tl{{left:{MARKS_PX + BLEED_PX}px;top:{MARKS_PX + BLEED_PX}px;}}
.marks .tl::before{{left:-16px;top:0;}}      .marks .tl::after{{top:-16px;left:0;}}
.marks .tr{{right:{MARKS_PX + BLEED_PX}px;top:{MARKS_PX + BLEED_PX}px;}}
.marks .tr::before{{right:-16px;top:0;}}     .marks .tr::after{{top:-16px;right:0;}}
.marks .bl{{left:{MARKS_PX + BLEED_PX}px;bottom:{MARKS_PX + BLEED_PX}px;}}
.marks .bl::before{{left:-16px;bottom:0;}}   .marks .bl::after{{bottom:-16px;left:0;}}
.marks .br{{right:{MARKS_PX + BLEED_PX}px;bottom:{MARKS_PX + BLEED_PX}px;}}
.marks .br::before{{right:-16px;bottom:0;}}  .marks .br::after{{bottom:-16px;right:0;}}
.folio{{position:absolute;left:0;right:0;bottom:5px;text-align:center;font:9px/1 monospace;color:#888;}}
"""

_SECTION_RE = re.compile(r'<section class="page.*?</section>', re.S)


def _wrap_sheets(body: str, title: str) -> str:
    """Emballe chaque page dans une feuille avec ses équerres de coupe.
    (les <section class="page"> ne sont jamais imbriquées → découpe sûre)"""
    out = []
    for i, sec in enumerate(_SECTION_RE.findall(body), 1):
        out.append(
            f'<div class="sheet">{sec}'
            f'<div class="marks"><i class="tl"></i><i class="tr"></i><i class="bl"></i><i class="br"></i></div>'
            f'<div class="folio">{_escape(title)} — page {i}</div></div>'
        )
    return "".join(out)


def render_model(model: dict, print_mode: bool = False, marks: bool = False) -> tuple[Path, dict]:
    """print_mode : fichier destiné au papier (fond perdu + haute déf).
    marks : ajoute les équerres de coupe — À NE PAS activer pour Blurb / Lulu /
    Pixartprinting, qui exigent un PDF sans repères."""
    global _PRINT
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    meta = _meta_index()
    theme = model.get("theme", "editorial")
    css = THEMES.get(theme, CSS_EDITORIAL)
    fonts = _embed_fonts(theme)
    pages = model.get("pages", [])
    title = model.get("title", "Artbook")
    _PRINT = print_mode
    try:
        body = "".join(_render_page(pg, meta) for pg in pages)
    finally:
        _PRINT = False
    if print_mode:
        body = _wrap_sheets(body, title)
        css += CSS_PRINT_BASE + (CSS_PRINT_MARKS if marks else CSS_PRINT_ONLINE)
    suffix = ("-atelier" if marks else "-imprimeur") if print_mode else ""
    html = (f'<!doctype html><html lang="fr"><head><meta charset="utf-8" />'
            f'<title>{_escape(title)}</title>'
            f'<style>{fonts}{css}</style></head>'
            f'<body>{body}</body></html>')
    out = EXPORTS_DIR / f"artbook-{_slugify(title)}{suffix}-{datetime.now():%Y%m%d-%H%M%S}.html"
    out.write_text(html, encoding="utf-8")
    n_photos = sum(len(p.get("items", [])) for p in pages if p.get("tpl") in IMAGE_TPLS or p.get("tpl") == "photo-text")
    return out, {"pages": len(pages), "photos": n_photos}


import shutil
import subprocess


def render_pdf(model: dict, print_mode: bool = False, marks: bool = False) -> Path:
    """Rend le modèle en HTML puis en PDF via chromium headless (respecte @page).
    print_mode : fichier papier (fond perdu 3 mm, ~300 dpi, zone tranquille).
    marks : équerres de coupe (imprimeur d'atelier uniquement)."""
    html_path, _ = render_model(model, print_mode=print_mode, marks=marks)
    pdf_path = html_path.with_suffix(".pdf")
    chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable") \
        or shutil.which("chromium") or shutil.which("chromium-browser")
    if not chrome:
        raise RuntimeError("Aucun chromium/chrome trouvé pour l'export PDF")
    subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
         f"--print-to-pdf={pdf_path}", "--no-pdf-header-footer",
         "--print-to-pdf-no-header", f"file://{html_path}"],
        check=True, capture_output=True, timeout=600,
    )
    if not pdf_path.is_file():
        raise RuntimeError("chromium n'a pas produit de PDF")
    return pdf_path


# Compat : génère + rend en une passe (ancien point d'entrée).
def build_artbook(paths, title="Iris Artbook", subtitle="", chapter_by="category"):
    model = compose_model(paths, title, subtitle, chapter_by)
    save_model(model)
    return render_model(model)
