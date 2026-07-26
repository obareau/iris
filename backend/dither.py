"""Tramage 1 bit — porté de MONO° (~/DEV/mono, obareau).

Pourquoi c'est nécessaire et pas décoratif : un zine se photocopie, et une
photocopieuse comme une laser ne savent poser QUE du noir ou rien. Envoyer une
photo en niveaux de gris, c'est laisser le pilote décider — il applique une
trame quelconque, souvent grossière, et les demi-teintes partent en bouillie.
En tramant nous-mêmes, on choisit la structure du point et on garde la main.

Quatre algorithmes, chacun pour un usage :

  clustered-dot   Trame AM, les points s'agglomèrent en amas croissants comme
                  sur une presse. **Le bon choix pour la photocopie** : un amas
                  survit à la reproduction là où des pixels isolés se bouchent
                  ou disparaissent.
  atkinson        Ne diffuse que 6/8 de l'erreur → très contrasté, blancs
                  francs. Le rendu MacPaint 1984. Photocopie bien.
  floyd-steinberg Diffusion d'erreur classique, détail maximal — mais son bruit
                  fin se bouche à la photocopie. À réserver au tirage laser
                  direct ou au risographe.
  threshold       Seuil brut, aucun tramage. Pour le trait, le logo, le texte.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

# Trame clustered-dot 8×8 d'Ulichney, 0..63, deux points par tuile.
# Reprise telle quelle de mono°/src/filters/clusteredDot.ts.
_M8 = np.array([
    [24, 10, 12, 26, 35, 47, 49, 37],
    [8,   0,  2, 14, 45, 59, 61, 51],
    [22,  6,  4, 16, 43, 57, 63, 53],
    [30, 20, 18, 28, 33, 41, 55, 39],
    [34, 46, 48, 38, 25, 11, 13, 27],
    [44, 58, 60, 50,  9,  1,  3, 15],
    [42, 56, 62, 52, 23,  7,  5, 17],
    [32, 40, 54, 36, 31, 21, 19, 29],
], dtype=np.float32)

# Noyaux de diffusion d'erreur : (dx, dy, poids). mono°/src/filters/floydSteinberg.ts
_KERNELS = {
    "floyd-steinberg": [(1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16)],
    "atkinson": [(1, 0, 1 / 8), (2, 0, 1 / 8), (-1, 1, 1 / 8),
                 (0, 1, 1 / 8), (1, 1, 1 / 8), (0, 2, 1 / 8)],
}

ALGOS = ("clustered-dot", "atkinson", "floyd-steinberg", "threshold")


def _to_gray(img: Image.Image) -> np.ndarray:
    """Niveaux de gris linéaires 0..1, dans l'orientation d'affichage."""
    return np.asarray(img.convert("L"), dtype=np.float32) / 255.0


def _clustered_dot(g: np.ndarray, scale: int, bias: float) -> np.ndarray:
    h, w = g.shape
    scale = max(1, int(scale))
    ys = (np.arange(h) // scale) & 7
    xs = (np.arange(w) // scale) & 7
    thr = (_M8[np.ix_(ys, xs)] + 0.5) / 64.0 + bias
    return (g >= thr).astype(np.uint8)


def _error_diffusion(g: np.ndarray, kernel, level: float, serpentine: bool) -> np.ndarray:
    """Boucle pixel par pixel : l'erreur d'un point dépend de celle du précédent,
    ça ne se vectorise pas. Sur les vignettes d'un zine (≤ 1600 px) c'est
    instantané ; ne pas l'appliquer à une image pleine résolution sans raison."""
    g = g.copy()
    h, w = g.shape
    out = np.zeros((h, w), dtype=np.uint8)
    for y in range(h):
        ltr = (not serpentine) or (y % 2 == 0)
        rng = range(w) if ltr else range(w - 1, -1, -1)
        for x in rng:
            old = g[y, x]
            new = 1.0 if old >= level else 0.0
            out[y, x] = int(new)
            err = old - new
            for dx, dy, wgt in kernel:
                nx = x + (dx if ltr else -dx)   # noyau miroir sur les lignes inverses
                ny = y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    g[ny, nx] += err * wgt
    return out


def dither(img: Image.Image, algo: str = "clustered-dot", *, scale: int = 1,
           bias: float = 0.0, level: float = 0.5, serpentine: bool = True,
           contrast: float = 1.0) -> Image.Image:
    """Rend une image en 1 bit (mode PIL « 1 »), prête pour la photocopie.

    contrast : appliqué AVANT le tramage. Une photo un peu terne donne une
    trame molle ; remonter le contraste avant est plus efficace que de corriger
    après, où il n'y a plus que du noir et du blanc à corriger.
    """
    if algo not in ALGOS:
        raise ValueError(f"Trame inconnue : {algo} (attendu : {', '.join(ALGOS)})")
    g = _to_gray(img)
    if contrast != 1.0:
        g = np.clip((g - 0.5) * contrast + 0.5, 0.0, 1.0)

    if algo == "threshold":
        bits = (g >= level).astype(np.uint8)
    elif algo == "clustered-dot":
        bits = _clustered_dot(g, scale, bias)
    else:
        bits = _error_diffusion(g, _KERNELS[algo], level, serpentine)

    return Image.fromarray((bits * 255).astype(np.uint8), mode="L").convert("1")
