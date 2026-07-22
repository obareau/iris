#!/usr/bin/env python3
"""Serveur MCP « iris » — wrapper LECTURE SEULE sur l'API HTTP d'Iris.

Iris est la documentaliste de l'écosystème Robotariis (tri/recherche/attributs
de photos) ; Recta est le Posteur. Ce MCP existe pour qu'un agent qui doit
nourrir Recta (ou toute autre consommatrice) en images puisse demander à Iris
"une photo qui correspond à X" plutôt que de fouiller le système de fichiers
ou de deviner un chemin.

Aucune écriture : ni notation, ni suppression, ni publication Renegat — ces
actions restent réservées à l'UI Galerie d'Iris (aperçu/confirmation humaine).
Le service FastAPI d'Iris doit tourner (localhost:8800 par défaut). Transport
stdio — enregistrement :

    claude mcp add iris -- uv run --with mcp iris_mcp.py

Config : IRIS_URL (défaut http://localhost:8800).
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from mcp.server.fastmcp import FastMCP

IRIS_URL = os.environ.get("IRIS_URL", "http://localhost:8800").rstrip("/")

mcp = FastMCP("iris")


def _get(path: str, params: dict | None = None):
    url = f"{IRIS_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"Iris {e.code} sur {path} : {body[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Iris injoignable à {IRIS_URL} ({e.reason}). Le service tourne-t-il ? "
            "(systemctl status iris)"
        )


def _post(path: str, body: dict):
    url = f"{IRIS_URL}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"Iris {e.code} sur {path} : {err_body[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Iris injoignable à {IRIS_URL} ({e.reason}).")


# Champs essentiels : on jette les attributs bruts (déjà résumés dans
# `details`) pour ne pas faire déborder la réponse MCP sur une recherche
# à beaucoup de résultats.
_LEAN_KEYS = ("path", "category_label", "details", "rating", "renegat_posted")


def _lean(item: dict) -> dict:
    out = {k: item.get(k) for k in _LEAN_KEYS}
    if "score" in item:
        out["score"] = item["score"]
    return out


@mcp.tool()
def iris_search(
    folder: str,
    query: str | None = None,
    category: str | None = None,
    min_rating: int = 0,
    top_k: int = 10,
) -> list[dict]:
    """Cherche des photos déjà classées par Iris dans `folder` (typiquement
    .../_classees).

    Si `query` est fourni, recherche SÉMANTIQUE (CLIP texte→image — "une
    photo qui ressemble à X", pas une sous-chaîne exacte) ; les résultats
    portent alors un `score` de similarité (plus haut = plus proche).
    Sans `query`, renvoie toutes les photos correspondant aux filtres,
    triées par note décroissante (les mieux notées d'abord).

    `category` filtre sur le libellé exact (voir iris_categories pour la
    liste). `min_rating` (0-5) exclut les photos en dessous de ce seuil.
    Renvoie une liste de {path, category_label, details, rating,
    renegat_posted, score?} — utiliser `path` tel quel pour tout usage
    downstream (ex: --image=<path> de renegat-cli.ts côté Recta)."""
    if query:
        data = _post("/api/gallery/search", {
            "folder": folder, "query": query, "category": category,
            "min_rating": min_rating, "top_k": top_k,
        })
        return [_lean(i) for i in data["items"]]

    data = _get("/api/gallery", {"folder": folder})
    items = data["items"]
    if category:
        items = [i for i in items if i.get("category_label") == category]
    if min_rating:
        items = [i for i in items if (i.get("rating") or 0) >= min_rating]
    items.sort(key=lambda i: -(i.get("rating") or 0))
    return [_lean(i) for i in items[:top_k]]


@mcp.tool()
def iris_categories(folder: str) -> list[str]:
    """Liste les catégories présentes dans `folder` (ex: Personnes, Animaux,
    Paysages, Objets_documents_schemas) — à consulter avant iris_search si le
    libellé exact n'est pas connu d'avance."""
    data = _get("/api/gallery", {"folder": folder})
    return sorted({i["category_label"] for i in data["items"] if i.get("category_label")})


@mcp.tool()
def iris_image_details(path: str) -> dict:
    """Fiche complète d'une photo précise (catégorie, détails, attributs
    structurés, note, marqueur de publication Renegat si déjà postée)."""
    return _get("/api/gallery/item", {"path": path})


@mcp.tool()
def iris_similar_images(path: str, top_k: int = 5, min_similarity: float = 0.5) -> list[dict]:
    """Voisins visuels d'UNE photo précise (similarité CLIP sur l'embedding
    image, pas de texte) — répond à "trouve-moi d'autres photos qui
    ressemblent à celle-ci" plutôt qu'à une description en langage naturel
    (voir iris_search pour ça). Cherche dans le même dossier _classees que
    `path`. Renvoie {path, category_label, details, rating, score}."""
    data = _get("/api/gallery/similar", {"path": path, "top_k": top_k, "min_similarity": min_similarity})
    return [_lean(i) for i in data["items"]]


if __name__ == "__main__":
    mcp.run(transport="stdio")
