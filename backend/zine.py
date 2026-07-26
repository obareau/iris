"""Zine 8 pages — un objet promo tenant sur UNE feuille pliée.

Le principe (mini-zine « fringearts ») : une feuille paysage, pliée trois fois,
une seule coupe au pli central, et on obtient un livret de 8 pages. Pas de
reliure, pas de minimum de commande, pas d'imprimeur — une feuille = un zine.

La difficulté est l'IMPOSITION : pour que le livret plié se lise dans l'ordre,
les pages doivent être disposées dans un ordre précis sur la feuille, et la
rangée du haut imprimée à l'envers. La table ci-dessous est reprise de
~/DEV/Recta/src/zine-gen.ts, où elle tourne chaque semaine depuis des mois.

    Rangée haut (180°) :  p7  p6  p5  p4
    Rangée bas   (0°)  :  p8  p1  p2  p3
                          dos couv

On produit UNE page HTML contenant la feuille entière, avec la rangée du haut
retournée en CSS. Pas de post-traitement du PDF : ce que Chromium rend est déjà
la feuille à imprimer.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

import segno
from PIL import Image

import dither as dither_module

# Feuilles en pixels ENTIERS (96 dpi) : un arrondi sub-pixel crée une page
# fantôme à l'impression — piège déjà rencontré sur l'artbook.
SHEETS = {
    "A4": {"w": 1123, "h": 794, "label": "A4 paysage · 297 × 210 mm", "page": "74 × 105 mm"},
    "A3": {"w": 1587, "h": 1123, "label": "A3 paysage · 420 × 297 mm", "page": "105 × 148 mm"},
}

# (page logique 1-8, retournée à 180°) pour chaque cellule, de gauche à droite
IMPOSITION = [
    [(7, True), (6, True), (5, True), (4, True)],     # rangée du haut
    [(8, False), (1, False), (2, False), (3, False)],  # rangée du bas
]


def qr_svg(data: str, scale: int = 3) -> str:
    """QR en SVG inline — vectoriel, donc net à n'importe quelle taille
    d'impression, contrairement à un PNG qui pixelliserait."""
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="svg", scale=scale, border=0,
                                     dark="#000", light=None, xmldecl=False, svgns=True)
    return buf.getvalue().decode("utf-8")


def dithered_data_uri(path: Path, algo: str, max_px: int = 900,
                      scale: int = 1, contrast: float = 1.15) -> str:
    """Image tramée en 1 bit, encodée en PNG (le PNG garde le noir et blanc
    franc ; un JPEG réintroduirait du gris autour de chaque point)."""
    img = Image.open(path)
    img.thumbnail((max_px, max_px), Image.LANCZOS)
    bw = dither_module.dither(img, algo, scale=scale, contrast=contrast)
    out = io.BytesIO()
    bw.save(out, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode("ascii")


CSS = """
@page{{size:{w}px {h}px;margin:0;}}
*{{box-sizing:border-box;}}
html,body{{margin:0;padding:0;background:#fff;}}
body{{font-family:'Helvetica','Helvetica Neue',Arial,sans-serif;color:#000;}}
.sheet{{width:{w}px;height:{h}px;display:grid;
  grid-template-columns:repeat(4,1fr);grid-template-rows:repeat(2,1fr);
  background:#fff;overflow:hidden;}}
/* La rangée du haut part à l'envers : c'est ce qui rend le pliage lisible. */
.cell{{position:relative;overflow:hidden;padding:7mm 6mm;display:flex;
  flex-direction:column;border:.4px dashed #bbb;}}
.cell.flip{{transform:rotate(180deg);}}
@media print{{.cell{{border:none;}}}}
/* repère de coupe : seul le pli central se coupe */
.cut{{position:absolute;left:50%;top:0;bottom:0;width:0;border-left:.6px dashed #999;
  z-index:5;pointer-events:none;}}
@media print{{.cut{{border-left:.4px dashed #666;}}}}

.pg-num{{position:absolute;bottom:2.5mm;left:0;right:0;text-align:center;
  font-size:7px;color:#999;font-family:'IBM Plex Mono',monospace;}}

/* — Couverture — */
.cover{{justify-content:center;align-items:center;text-align:center;background:#000;color:#fff;}}
.cover .c-logo{{font-size:26px;font-weight:800;letter-spacing:-.03em;line-height:1;}}
.cover .c-sub{{margin-top:4mm;font-size:8.5px;letter-spacing:.24em;text-transform:uppercase;opacity:.85;}}
.cover .c-rule{{width:14mm;height:2px;background:#fff;margin:5mm 0;}}

/* — Œuvre : image tramée + cartel — */
.art{{padding:0;}}
.art img{{width:100%;height:62%;object-fit:cover;display:block;image-rendering:pixelated;}}
.art .a-txt{{padding:3.5mm 5mm;}}
.a-title{{font-size:10px;font-weight:700;line-height:1.15;}}
.a-year{{font-weight:400;font-style:italic;color:#555;}}
.a-cartel{{font-size:7.5px;font-style:italic;color:#555;line-height:1.4;margin-top:1mm;}}

/* — Page texte (lore, description ou citation) — */
.text{{justify-content:center;}}
.t-kicker{{font-family:'IBM Plex Mono',monospace;font-size:7px;letter-spacing:.22em;
  text-transform:uppercase;color:#666;margin-bottom:3mm;}}
.t-body{{font-size:9px;line-height:1.55;}}
.t-quote{{font-size:12.5px;font-weight:700;line-height:1.3;}}
.t-quote::before{{content:"« ";}} .t-quote::after{{content:" »";}}
.t-sign{{margin-top:3mm;font-family:'IBM Plex Mono',monospace;font-size:7px;
  letter-spacing:.14em;text-transform:uppercase;color:#666;}}

/* — Dos : contact + QR — */
.back{{justify-content:flex-end;}}
.b-qr{{width:26mm;height:26mm;margin-bottom:3.5mm;}}
.b-qr svg{{width:100%;height:100%;display:block;}}
.b-name{{font-size:11px;font-weight:800;letter-spacing:-.02em;}}
.b-line{{font-family:'IBM Plex Mono',monospace;font-size:7.5px;color:#333;margin-top:1.2mm;word-break:break-all;}}
.b-rule{{width:100%;height:1px;background:#000;margin:3mm 0;}}
.b-colophon{{font-size:6.5px;color:#777;line-height:1.45;margin-top:3mm;}}
"""

FOLD_NOTE = ("Plier en deux dans la largeur, puis en deux, puis en deux. "
             "Déplier une fois, couper le pli central sur la moitié de la longueur, "
             "replier : le livret de 8 pages est formé.")


def _esc(t: str) -> str:
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _cell_cover(p: dict) -> str:
    return (f'<div class="c-logo">{_esc(p.get("title",""))}</div>'
            f'<div class="c-rule"></div>'
            f'<div class="c-sub">{_esc(p.get("subtitle",""))}</div>')


def _cell_art(p: dict) -> str:
    year = f'<span class="a-year">, {_esc(p["year"])}</span>' if p.get("year") else ""
    title = f'<div class="a-title">{_esc(p.get("title",""))}{year}</div>' if p.get("title") else ""
    cartel = "".join(f'<div class="a-cartel">{_esc(l)}</div>' for l in (p.get("cartel") or []) if l)
    return f'<img src="{p["img"]}" alt="" /><div class="a-txt">{title}{cartel}</div>'


def _cell_text(p: dict) -> str:
    kicker = f'<div class="t-kicker">{_esc(p["kicker"])}</div>' if p.get("kicker") else ""
    sign = f'<div class="t-sign">{_esc(p["sign"])}</div>' if p.get("sign") else ""
    cls = "t-quote" if p.get("variant") == "quote" else "t-body"
    return f'{kicker}<div class="{cls}">{_esc(p.get("body",""))}</div>{sign}'


def _cell_back(p: dict) -> str:
    qr = f'<div class="b-qr">{p["qr"]}</div>' if p.get("qr") else ""
    lines = "".join(f'<div class="b-line">{_esc(l)}</div>' for l in (p.get("lines") or []) if l)
    colo = f'<div class="b-colophon">{_esc(p.get("colophon",""))}</div>' if p.get("colophon") else ""
    return (f'{qr}<div class="b-name">{_esc(p.get("name",""))}</div>{lines}'
            f'<div class="b-rule"></div>{colo}')


_RENDERERS = {"cover": _cell_cover, "art": _cell_art, "text": _cell_text, "back": _cell_back}


def render_sheet(pages: list[dict], sheet: str = "A4", title: str = "Zine",
                 show_guides: bool = True) -> str:
    """`pages` : exactement 8 entrées, dans l'ordre de LECTURE du livret.
    Chacune porte un `kind` (cover / art / text / back) et ses champs."""
    if len(pages) != 8:
        raise ValueError(f"Un zine fait exactement 8 pages (reçu : {len(pages)})")
    dims = SHEETS.get(sheet) or SHEETS["A4"]

    cells = []
    for row in IMPOSITION:
        for logical, flipped in row:
            p = pages[logical - 1]
            kind = p.get("kind", "text")
            inner = _RENDERERS.get(kind, _cell_text)(p)
            num = f'<div class="pg-num">{logical}</div>' if show_guides else ""
            cells.append(f'<div class="cell {kind} {"flip" if flipped else ""}">{inner}{num}</div>')

    cut = '<div class="cut"></div>' if show_guides else ""
    import artbook as A
    css = CSS.format(w=dims["w"], h=dims["h"])
    fonts = A._embed_fonts("editorial") + A._embed_fonts("brutalist")
    return (f'<!doctype html><html lang="fr"><head><meta charset="utf-8" />'
            f'<title>{_esc(title)}</title><style>{fonts}{css}</style></head>'
            f'<body><div class="sheet">{"".join(cells)}{cut}</div></body></html>')


# ---------------------------------------------------------------------------
# Composition : d'une sélection de photos aux 8 pages
# ---------------------------------------------------------------------------
def compose_zine(paths, *, title="ROBOTARIIS", subtitle="", sheet="A4",
                 text_mode="lore", n_text=2, url="", email="",
                 algo="clustered-dot", dot_scale=1, contrast=1.15,
                 colophon="", seed=None) -> list[dict]:
    """Six emplacements entre la couverture et le dos, remplis d'œuvres et de
    pages de texte. `text_mode` : lore (canon Recta/pirate) · description
    (les détails extraits par Iris) · quote (citations) · none (que des images).
    """
    import artbook as A   # import tardif : évite une dépendance circulaire

    meta = A._meta_index()
    photos = [p for p in paths if Path(p).is_file()]
    if not photos:
        raise ValueError("Aucune photo lisible dans la sélection")

    n_text = max(0, min(int(n_text), 6)) if text_mode != "none" else 0
    n_art = 6 - n_text
    photos = photos[:max(1, n_art)]

    # --- pages « œuvre » : image tramée + cartel -------------------------
    arts = []
    for p in photos:
        it = meta.get(p, {})
        c = A._cartel(it)
        arts.append({
            "kind": "art",
            "img": dithered_data_uri(Path(p), algo, scale=dot_scale, contrast=contrast),
            "title": c["title"] or it.get("character_name") or it.get("category_label") or "",
            "year": A._attr(it, "Année") or "",
            "cartel": [c["line2"], c["line3"]],
        })

    # --- pages « texte » -------------------------------------------------
    texts = []
    if n_text:
        if text_mode == "lore":
            for e in A._make_fillers(n_text, seed, True, True):
                if e["tpl"] == "pirate":
                    texts.append({"kind": "text", "variant": "quote",
                                  "kicker": f'⚡ {e.get("tag","")}',
                                  "body": e.get("text", ""), "sign": e.get("sign", "")})
                else:
                    texts.append({"kind": "text", "variant": "quote" if e.get("variant") == "devise" else "body",
                                  "kicker": "Rectitude",
                                  "body": e.get("devise") if e.get("variant") == "devise" else e.get("text", ""),
                                  "sign": "— L'Oraculum · C.G.U."})
        elif text_mode == "description":
            for p in photos[:n_text]:
                it = meta.get(p, {})
                texts.append({"kind": "text", "variant": "body",
                              "kicker": A._cartel(it)["title"] or "Notice",
                              "body": it.get("details") or "—"})
        elif text_mode == "quote":
            for e in A._recta_pick(seed, n_text):
                texts.append({"kind": "text", "variant": "quote",
                              "body": e.get("devise") or e.get("text", ""),
                              "sign": "— L'Oraculum · C.G.U."})

    # --- assemblage : on alterne pour que le texte respire entre les images
    middle, ai, ti = [], 0, 0
    while len(middle) < 6:
        if ai < len(arts) and (len(middle) % 2 == 0 or ti >= len(texts)):
            middle.append(arts[ai]); ai += 1
        elif ti < len(texts):
            middle.append(texts[ti]); ti += 1
        elif ai < len(arts):
            middle.append(arts[ai]); ai += 1
        else:
            middle.append({"kind": "text", "variant": "body", "body": ""})

    lines = [x for x in (url, email) if x]
    return [
        {"kind": "cover", "title": title, "subtitle": subtitle},
        *middle,
        {"kind": "back", "name": title, "lines": lines,
         "qr": qr_svg(url or email or title),
         "colophon": colophon or FOLD_NOTE},
    ]
