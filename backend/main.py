import io
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import classifier
import dedupe as dedupe_module
import graph as graph_module
import identity as identity_module
import details as details_module
import gallery as gallery_module
import library
import mounts
import organizer
import prefilter
import scanner

app = FastAPI(title="Argus")

RECTA_DIR = Path.home() / "DEV" / "Recta"

STATIC_DIR = Path(__file__).parent.parent / "static"

STATE = {
    "categories": [dict(c) for c in classifier.DEFAULT_CATEGORIES],
    "files": [],  # list[Path]
    "results": {},  # path str -> dict
    "job": {"status": "idle", "done": 0, "total": 0, "current": None, "phase": None},
    "job_lock": threading.Lock(),
    "details_job": {"status": "idle", "done": 0, "total": 0, "current": None},
    "details_job_lock": threading.Lock(),
    "refine_job": {"status": "idle", "done": 0, "total": 0, "current": None},
    "refine_job_lock": threading.Lock(),
    "dedupe_job": {"status": "idle", "done": 0, "total": 0, "phase": None},
    "dedupe_job_lock": threading.Lock(),
    "dedupe_groups": [],
    "backfill_job": {"status": "idle", "done": 0, "total": 0, "current": None},
    "backfill_job_lock": threading.Lock(),
    "refine_gallery_job": {"status": "idle", "done": 0, "total": 0, "current": None},
    "refine_gallery_job_lock": threading.Lock(),
    "aesthetic_job": {"status": "idle", "done": 0, "total": 0, "current": None},
    "aesthetic_job_lock": threading.Lock(),
    "canon_job": {"status": "idle", "done": 0, "total": 0, "current": None},
    "canon_job_lock": threading.Lock(),
    "graph_job": {"status": "idle", "done": 0, "total": 0, "phase": None},
    "graph_job_lock": threading.Lock(),
    "graph_data": {"nodes": [], "edges": []},
}


class ScanRequest(BaseModel):
    folder: str


class Category(BaseModel):
    slug: str
    label: str
    prompt: str


class AnalyzeRequest(BaseModel):
    folder: str
    categories: list[Category] | None = None


class OverrideRequest(BaseModel):
    path: str
    category_slug: str


class ApplyRequest(BaseModel):
    dest_root: str
    paths: list[str] | None = None  # if None, apply all analyzed results


class ExtractDetailsRequest(BaseModel):
    paths: list[str] | None = None  # if None, extract for all analyzed results missing details


class RenegatPreviewRequest(BaseModel):
    image_path: str
    lang: str | None = None


class RenegatPublishRequest(BaseModel):
    image_path: str
    numero: int
    lang: str


class DedupeRequest(BaseModel):
    threshold: float = 0.92
    category: str | None = None


class GraphRequest(BaseModel):
    category: str | None = None
    top_k: int = 5
    min_similarity: float = 0.75
    mode: str = "similarity"  # "similarity" (whole-image, graph.py) ou "identity" (crop visage, identity.py)


class DiscardRequest(BaseModel):
    path: str


class BackfillRequest(BaseModel):
    paths: list[str] | None = None  # si None : toutes les images de la bibliothèque sans détails


class RefineRequest(BaseModel):
    paths: list[str]


class RatingRequest(BaseModel):
    path: str
    rating: int


class SearchRequest(BaseModel):
    query: str
    category: str | None = None
    min_rating: int = 0
    top_k: int = 10


class LibraryFolderRequest(BaseModel):
    path: str


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/browse")
def browse(path: str | None = None):
    base = Path(path).expanduser().resolve() if path else Path.home()
    if not base.is_dir():
        raise HTTPException(404, f"Dossier introuvable: {base}")
    try:
        entries = [
            {"name": p.name, "path": str(p)}
            for p in sorted(base.iterdir(), key=lambda x: x.name.lower())
            if p.is_dir() and not p.name.startswith(".")
        ]
    except PermissionError:
        raise HTTPException(403, "Accès refusé à ce dossier")
    parent = str(base.parent) if base.parent != base else None
    return {"path": str(base), "parent": parent, "entries": entries}


@app.get("/api/browse/shortcuts")
def browse_shortcuts():
    return {"shortcuts": mounts.list_shortcuts()}


@app.post("/api/scan")
def scan(req: ScanRequest):
    try:
        files = scanner.scan_folder(req.folder)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    STATE["files"] = files
    return {"count": len(files)}


@app.get("/api/thumbnail")
def thumbnail(path: str):
    p = Path(path)
    if not p.is_file():
        raise HTTPException(404, "Fichier introuvable")
    img = Image.open(p).convert("RGB")
    img.thumbnail((220, 220))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/jpeg")


@app.get("/api/image")
def image_full(path: str):
    """Fichier original (pas de resize) — pour la vue en grand (double-clic)."""
    p = Path(path)
    if not p.is_file():
        raise HTTPException(404, "Fichier introuvable")
    return FileResponse(p)


def _finalize_item(key: str, p, base: dict) -> None:
    """Attach the cheap deterministic attributes (colour/orientation/size) and
    commit the item into the shared results dict."""
    try:
        base["color_mode"] = classifier.detect_color_mode(p)
        base["orientation"] = classifier.detect_orientation(p)
        with Image.open(p) as im:
            base["width"], base["height"] = im.size
        base["filesize"] = p.stat().st_size
        STATE["results"][key] = base
    except Exception as e:
        STATE["results"][key] = {"path": key, "error": str(e)}


def _run_analysis(categories: list[dict]):
    files = STATE["files"]
    STATE["job"] = {"status": "running", "done": 0, "total": len(files), "current": None, "phase": "yolo", "cancel_requested": False}
    STATE["results"] = {}

    try:
        available_slugs = {c["slug"] for c in categories}

        paths_with_stat = []
        for p in files:
            st = p.stat()
            paths_with_stat.append((p, st.st_mtime, st.st_size))

        # Pass 1: fast YOLO pre-filter. Resolves clear-cut person/animal/object
        # images instantly; anything ambiguous (typically landscapes) is left
        # for the slower CLIP zero-shot pass below. Detections are kept for every
        # image (even those handed to CLIP) so the inspector can show them.
        needs_clip = []
        detections_map: dict[str, list] = {}
        for p, mtime, size in paths_with_stat:
            if STATE["job"]["cancel_requested"]:
                STATE["job"]["status"] = "cancelled"
                STATE["job"]["current"] = None
                return
            key = str(p)
            STATE["job"]["current"] = key
            try:
                dets = prefilter.detect(p)
            except Exception:
                dets = []
            detections_map[key] = prefilter.summarize(dets)
            quick = prefilter.pick_category(dets, available_slugs)
            if quick is not None:
                slug, confidence = quick
                label = next((c["label"] for c in categories if c["slug"] == slug), classifier.FALLBACK_CATEGORY["label"])
                _finalize_item(key, p, {
                    "path": key,
                    "category_slug": slug,
                    "category_label": label,
                    "confidence": round(confidence, 3),
                    "source": "yolo",
                    "detections": detections_map[key],
                })
                STATE["job"]["done"] += 1
            else:
                needs_clip.append((p, mtime, size))

        if STATE["job"]["cancel_requested"]:
            STATE["job"]["status"] = "cancelled"
            STATE["job"]["current"] = None
            return

        # Pass 2: CLIP zero-shot for whatever YOLO couldn't resolve confidently.
        STATE["job"]["phase"] = "clip"
        text_feats = classifier.text_embeddings(categories)
        embeddings = classifier.batch_image_embeddings(needs_clip)

        for p, mtime, size in needs_clip:
            if STATE["job"]["cancel_requested"]:
                STATE["job"]["status"] = "cancelled"
                STATE["job"]["current"] = None
                return
            key = str(p)
            STATE["job"]["current"] = key
            try:
                emb = embeddings.get(key)
                if emb is None:
                    raise ValueError("embedding indisponible")
                slug, confidence = classifier.classify(emb, categories, text_feats)
                scores = classifier.classify_scores(emb, categories, text_feats)
                label = next((c["label"] for c in categories if c["slug"] == slug), classifier.FALLBACK_CATEGORY["label"])
                _finalize_item(key, p, {
                    "path": key,
                    "category_slug": slug,
                    "category_label": label,
                    "confidence": round(confidence, 3),
                    "source": "clip",
                    "detections": detections_map.get(key, []),
                    "clip_scores": scores,
                })
            except Exception as e:
                STATE["results"][key] = {"path": key, "error": str(e)}
            STATE["job"]["done"] += 1

        STATE["job"]["current"] = None
        STATE["job"]["status"] = "done"
    except Exception as e:
        # Sans ce filet, une exception hors des try par-image (ex: le batch
        # CLIP entier qui plante) laissait "status" bloqué sur "running" à
        # jamais — /api/analyze refuse alors tout nouvel import (409) sans
        # qu'aucun bouton de l'UI ne puisse s'en sortir. Vécu en réel.
        STATE["job"]["status"] = "error"
        STATE["job"]["current"] = str(e)


@app.post("/api/analyze/cancel")
def analyze_cancel():
    if STATE["job"]["status"] == "running":
        STATE["job"]["cancel_requested"] = True
    return STATE["job"]


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    with STATE["job_lock"]:
        if STATE["job"]["status"] == "running":
            raise HTTPException(409, "Une analyse est déjà en cours")
        try:
            files = scanner.scan_folder(req.folder)
        except FileNotFoundError as e:
            raise HTTPException(404, str(e))
        STATE["files"] = files
        categories = [c.model_dump() for c in req.categories] if req.categories else STATE["categories"]
        STATE["categories"] = categories

    thread = threading.Thread(target=_run_analysis, args=(categories,), daemon=True)
    thread.start()
    return {"started": True, "total": len(files)}


@app.get("/api/progress")
def progress():
    return STATE["job"]


@app.get("/api/results")
def results():
    return {"categories": STATE["categories"], "items": list(STATE["results"].values())}


@app.post("/api/override")
def override(req: OverrideRequest):
    item = STATE["results"].get(req.path)
    if item is None:
        raise HTTPException(404, "Image non analysée")
    label = next(
        (c["label"] for c in STATE["categories"] if c["slug"] == req.category_slug),
        classifier.FALLBACK_CATEGORY["label"] if req.category_slug == "autre" else req.category_slug,
    )
    item["category_slug"] = req.category_slug
    item["category_label"] = label
    return item


def _run_details(paths: list[str]):
    STATE["details_job"] = {"status": "running", "done": 0, "total": len(paths), "current": None, "cancel_requested": False}
    try:
        for path in paths:
            if STATE["details_job"]["cancel_requested"]:
                STATE["details_job"]["status"] = "cancelled"
                STATE["details_job"]["current"] = None
                return
            item = STATE["results"].get(path)
            if item is None or "error" in item:
                STATE["details_job"]["done"] += 1
                continue
            STATE["details_job"]["current"] = path
            try:
                detail = details_module.extract_detail(Path(path), item["category_slug"])
                item["details"] = detail["text"]
                item["details_slug"] = detail["slug"]
            except Exception as e:
                item["details_error"] = str(e)
            STATE["details_job"]["done"] += 1
        STATE["details_job"]["current"] = None
        STATE["details_job"]["status"] = "done"
    except Exception as e:
        # Même filet que _run_analysis — sans lui un crash hors du try
        # par-image bloque "status" sur "running" pour toujours.
        STATE["details_job"]["status"] = "error"
        STATE["details_job"]["current"] = str(e)


@app.post("/api/extract-details/cancel")
def extract_details_cancel():
    if STATE["details_job"]["status"] == "running":
        STATE["details_job"]["cancel_requested"] = True
    return STATE["details_job"]


@app.post("/api/extract-details")
def extract_details(req: ExtractDetailsRequest):
    with STATE["details_job_lock"]:
        if STATE["details_job"]["status"] == "running":
            raise HTTPException(409, "Une extraction est déjà en cours")
        if req.paths is not None:
            paths = req.paths
        else:
            paths = [p for p, v in STATE["results"].items() if "error" not in v and "details" not in v]
        if not paths:
            raise HTTPException(400, "Rien à extraire")

    thread = threading.Thread(target=_run_details, args=(paths,), daemon=True)
    thread.start()
    return {"started": True, "total": len(paths)}


@app.get("/api/details-progress")
def details_progress():
    return STATE["details_job"]


def _run_refine(paths: list[str]):
    STATE["refine_job"] = {"status": "running", "done": 0, "total": len(paths), "current": None, "cancel_requested": False}
    try:
        for path in paths:
            if STATE["refine_job"]["cancel_requested"]:
                STATE["refine_job"]["status"] = "cancelled"
                STATE["refine_job"]["current"] = None
                return
            item = STATE["results"].get(path)
            if item is None or "error" in item:
                STATE["refine_job"]["done"] += 1
                continue
            STATE["refine_job"]["current"] = path
            try:
                item["attributes"] = details_module.refine_attributes(Path(path), item["category_slug"])
            except Exception as e:
                item["attributes_error"] = str(e)
            STATE["refine_job"]["done"] += 1
        STATE["refine_job"]["current"] = None
        STATE["refine_job"]["status"] = "done"
    except Exception as e:
        # Même filet que _run_analysis — sans lui un crash hors du try
        # par-image bloque "status" sur "running" pour toujours.
        STATE["refine_job"]["status"] = "error"
        STATE["refine_job"]["current"] = str(e)


@app.post("/api/refine/cancel")
def refine_cancel():
    if STATE["refine_job"]["status"] == "running":
        STATE["refine_job"]["cancel_requested"] = True
    return STATE["refine_job"]


@app.post("/api/refine")
def refine(req: ExtractDetailsRequest):
    with STATE["refine_job_lock"]:
        if STATE["refine_job"]["status"] == "running":
            raise HTTPException(409, "Un affinage est déjà en cours")
        if req.paths is not None:
            paths = req.paths
        else:
            paths = [p for p, v in STATE["results"].items() if "error" not in v and "attributes" not in v]
        if not paths:
            raise HTTPException(400, "Rien à affiner")

    thread = threading.Thread(target=_run_refine, args=(paths,), daemon=True)
    thread.start()
    return {"started": True, "total": len(paths)}


@app.get("/api/refine-progress")
def refine_progress():
    return STATE["refine_job"]


@app.post("/api/apply")
def apply(req: ApplyRequest):
    items = [v for v in STATE["results"].values() if "error" not in v]
    if req.paths is not None:
        wanted = set(req.paths)
        items = [i for i in items if i["path"] in wanted]
    if not items:
        raise HTTPException(400, "Rien à appliquer")
    summary = organizer.apply_moves(items, req.dest_root)
    for i in items:
        STATE["results"].pop(i["path"], None)
    return summary


@app.post("/api/undo")
def undo():
    return organizer.undo_last()


@app.get("/api/library")
def get_library():
    return {"folders": library.list_folders()}


@app.get("/api/library/health")
def get_library_health():
    return {"folders": gallery_module.library_health()}


@app.post("/api/library/add")
def library_add(req: LibraryFolderRequest):
    try:
        folders = library.add_folder(req.path)
    except NotADirectoryError as e:
        raise HTTPException(404, str(e))
    return {"folders": folders}


@app.post("/api/library/remove")
def library_remove(req: LibraryFolderRequest):
    return {"folders": library.remove_folder(req.path)}


@app.get("/api/gallery")
def get_gallery():
    return {"items": gallery_module.list_gallery()}


def _run_backfill(paths: list[str]):
    STATE["backfill_job"] = {"status": "running", "done": 0, "total": 0, "current": None, "cancel_requested": False}
    try:
        gallery_module.backfill_details(paths, progress=STATE["backfill_job"])
        if STATE["backfill_job"]["status"] == "running":
            STATE["backfill_job"]["status"] = "done"
    except Exception as e:
        STATE["backfill_job"] = {"status": "error", "done": 0, "total": 0, "current": str(e)}


@app.post("/api/gallery/backfill")
def gallery_backfill(req: BackfillRequest):
    with STATE["backfill_job_lock"]:
        if STATE["backfill_job"]["status"] == "running":
            raise HTTPException(409, "Un rétro-remplissage est déjà en cours")
        if req.paths is not None:
            paths = req.paths
        else:
            items = gallery_module.list_gallery()
            paths = [i["path"] for i in items if not i.get("details")]
        if not paths:
            raise HTTPException(400, "Rien à compléter")
        STATE["backfill_job"] = {"status": "running", "done": 0, "total": len(paths), "current": None, "cancel_requested": False}

    thread = threading.Thread(target=_run_backfill, args=(paths,), daemon=True)
    thread.start()
    return {"started": True, "total": len(paths)}


@app.get("/api/gallery/backfill-progress")
def gallery_backfill_progress():
    return STATE["backfill_job"]


@app.post("/api/gallery/backfill/cancel")
def gallery_backfill_cancel():
    if STATE["backfill_job"]["status"] == "running":
        STATE["backfill_job"]["cancel_requested"] = True
    return STATE["backfill_job"]


def _run_refine_gallery(paths: list[str]):
    STATE["refine_gallery_job"] = {"status": "running", "done": 0, "total": len(paths), "current": None, "cancel_requested": False}
    try:
        gallery_module.refine_attributes_for(paths, progress=STATE["refine_gallery_job"])
        if STATE["refine_gallery_job"]["status"] == "running":
            STATE["refine_gallery_job"]["status"] = "done"
    except Exception as e:
        STATE["refine_gallery_job"] = {"status": "error", "done": 0, "total": 0, "current": str(e)}


@app.post("/api/gallery/refine")
def gallery_refine(req: RefineRequest):
    with STATE["refine_gallery_job_lock"]:
        if STATE["refine_gallery_job"]["status"] == "running":
            raise HTTPException(409, "Un réaffinage est déjà en cours")
        if not req.paths:
            raise HTTPException(400, "Rien à réaffiner")
        STATE["refine_gallery_job"] = {"status": "running", "done": 0, "total": len(req.paths), "current": None, "cancel_requested": False}

    thread = threading.Thread(target=_run_refine_gallery, args=(req.paths,), daemon=True)
    thread.start()
    return {"started": True, "total": len(req.paths)}


@app.get("/api/gallery/refine-progress")
def gallery_refine_progress():
    return STATE["refine_gallery_job"]


@app.post("/api/gallery/refine/cancel")
def gallery_refine_cancel():
    if STATE["refine_gallery_job"]["status"] == "running":
        STATE["refine_gallery_job"]["cancel_requested"] = True
    return STATE["refine_gallery_job"]


def _run_aesthetic(paths: list[str]):
    STATE["aesthetic_job"] = {"status": "running", "done": 0, "total": len(paths), "current": None, "cancel_requested": False}
    try:
        gallery_module.score_aesthetic_for(paths, progress=STATE["aesthetic_job"])
        if STATE["aesthetic_job"]["status"] == "running":
            STATE["aesthetic_job"]["status"] = "done"
    except Exception as e:
        STATE["aesthetic_job"] = {"status": "error", "done": 0, "total": 0, "current": str(e)}


@app.post("/api/gallery/aesthetic")
def gallery_aesthetic(req: RefineRequest):
    with STATE["aesthetic_job_lock"]:
        if STATE["aesthetic_job"]["status"] == "running":
            raise HTTPException(409, "Un calcul de score esthétique est déjà en cours")
        if not req.paths:
            raise HTTPException(400, "Rien à noter")
        STATE["aesthetic_job"] = {"status": "running", "done": 0, "total": len(req.paths), "current": None, "cancel_requested": False}

    thread = threading.Thread(target=_run_aesthetic, args=(req.paths,), daemon=True)
    thread.start()
    return {"started": True, "total": len(req.paths)}


@app.get("/api/gallery/aesthetic-progress")
def gallery_aesthetic_progress():
    return STATE["aesthetic_job"]


@app.post("/api/gallery/aesthetic/cancel")
def gallery_aesthetic_cancel():
    if STATE["aesthetic_job"]["status"] == "running":
        STATE["aesthetic_job"]["cancel_requested"] = True
    return STATE["aesthetic_job"]


def _run_canon(paths: list[str]):
    STATE["canon_job"] = {"status": "running", "done": 0, "total": len(paths), "current": None, "cancel_requested": False}
    try:
        gallery_module.check_canon_for(paths, progress=STATE["canon_job"])
        if STATE["canon_job"]["status"] == "running":
            STATE["canon_job"]["status"] = "done"
    except Exception as e:
        STATE["canon_job"] = {"status": "error", "done": 0, "total": 0, "current": str(e)}


@app.post("/api/gallery/canon")
def gallery_canon(req: RefineRequest):
    with STATE["canon_job_lock"]:
        if STATE["canon_job"]["status"] == "running":
            raise HTTPException(409, "Une vérification de canon est déjà en cours")
        if not req.paths:
            raise HTTPException(400, "Rien à vérifier")
        STATE["canon_job"] = {"status": "running", "done": 0, "total": len(req.paths), "current": None, "cancel_requested": False}

    thread = threading.Thread(target=_run_canon, args=(req.paths,), daemon=True)
    thread.start()
    return {"started": True, "total": len(req.paths)}


@app.get("/api/gallery/canon-progress")
def gallery_canon_progress():
    return STATE["canon_job"]


@app.post("/api/gallery/canon/cancel")
def gallery_canon_cancel():
    if STATE["canon_job"]["status"] == "running":
        STATE["canon_job"]["cancel_requested"] = True
    return STATE["canon_job"]


@app.post("/api/gallery/rating")
def gallery_rating(req: RatingRequest):
    try:
        gallery_module.set_rating(req.path, req.rating)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(400, str(e))
    return {"path": req.path, "rating": req.rating}


@app.get("/api/gallery/item")
def gallery_item(path: str):
    try:
        return gallery_module.get_item(path)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.post("/api/gallery/search")
def gallery_search(req: SearchRequest):
    return {"items": gallery_module.semantic_search(req.query, req.category, req.min_rating, req.top_k)}


def _run_renegat_cli(args: list[str]) -> dict:
    """Sous-processus vers ~/DEV/Recta (tsx, pas de build Electron nécessaire
    pour renegat-cli.ts) — pont entre la galerie Iris et la publication Recta."""
    try:
        proc = subprocess.run(
            ["npx", "tsx", "src/renegat-cli.ts", *args],
            cwd=RECTA_DIR, capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Recta n'a pas répondu à temps")
    except FileNotFoundError:
        raise HTTPException(500, "npx introuvable — Recta est-il installé ?")
    lines = proc.stdout.strip().splitlines()
    if not lines:
        raise HTTPException(500, f"Recta : aucune sortie (code {proc.returncode}) — {proc.stderr[-500:]}")
    try:
        data = json.loads(lines[-1])
    except Exception:
        raise HTTPException(500, f"Recta : sortie illisible — {lines[-1][:300]}")
    if "error" in data:
        raise HTTPException(400, data["error"])
    return data


@app.post("/api/recta/renegat/preview")
def renegat_preview(req: RenegatPreviewRequest):
    args = [f"--image={req.image_path}", "--dry"]
    if req.lang:
        args.append(f"--lang={req.lang}")
    return _run_renegat_cli(args)


@app.post("/api/recta/renegat/publish")
def renegat_publish(req: RenegatPublishRequest):
    args = [f"--image={req.image_path}", f"--numero={req.numero}", f"--lang={req.lang}"]
    return _run_renegat_cli(args)


def _run_dedupe(threshold: float, category: str | None):
    STATE["dedupe_job"] = {"status": "running", "done": 0, "total": 0, "phase": "scan", "cancel_requested": False}
    try:
        items = gallery_module.list_gallery()
        if category:
            items = [i for i in items if i["category_label"] == category]
        files = [Path(i["path"]) for i in items]
        groups = dedupe_module.find_duplicate_groups(files, threshold, progress=STATE["dedupe_job"])
        if STATE["dedupe_job"]["status"] == "running":
            STATE["dedupe_groups"] = groups
            STATE["dedupe_job"]["status"] = "done"
    except Exception as e:
        STATE["dedupe_job"] = {"status": "error", "done": 0, "total": 0, "phase": str(e)}


@app.post("/api/dedupe")
def dedupe(req: DedupeRequest):
    with STATE["dedupe_job_lock"]:
        if STATE["dedupe_job"]["status"] == "running":
            raise HTTPException(409, "Une détection de doublons est déjà en cours")
        STATE["dedupe_job"] = {"status": "running", "done": 0, "total": 0, "phase": "scan", "cancel_requested": False}

    thread = threading.Thread(target=_run_dedupe, args=(req.threshold, req.category), daemon=True)
    thread.start()
    return {"started": True}


@app.post("/api/dedupe/cancel")
def dedupe_cancel():
    if STATE["dedupe_job"]["status"] == "running":
        STATE["dedupe_job"]["cancel_requested"] = True
    return STATE["dedupe_job"]


@app.get("/api/dedupe-progress")
def dedupe_progress():
    return STATE["dedupe_job"]


@app.get("/api/dedupe-results")
def dedupe_results():
    return {"groups": STATE["dedupe_groups"]}


@app.post("/api/dedupe/discard")
def dedupe_discard(req: DiscardRequest):
    try:
        trashed_to = dedupe_module.discard(req.path)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    # Retire l'image écartée de tous les groupes en mémoire (et les groupes
    # redevenus des singletons, qui n'ont plus rien à comparer).
    for g in STATE["dedupe_groups"]:
        if req.path in g["images"]:
            g["images"].remove(req.path)
    STATE["dedupe_groups"] = [g for g in STATE["dedupe_groups"] if len(g["images"]) > 1]
    return {"trashed_to": trashed_to}


def _run_graph(category: str | None, top_k: int, min_similarity: float, mode: str):
    STATE["graph_job"] = {"status": "running", "done": 0, "total": 0, "phase": "scan", "cancel_requested": False}
    try:
        if mode == "identity":
            data = identity_module.build_identity_graph(top_k, min_similarity, progress=STATE["graph_job"])
        else:
            data = graph_module.build_similarity_graph(category, top_k, min_similarity, progress=STATE["graph_job"])
        if STATE["graph_job"]["status"] == "running":
            STATE["graph_data"] = data
            STATE["graph_job"]["status"] = "done"
    except Exception as e:
        STATE["graph_job"] = {"status": "error", "done": 0, "total": 0, "phase": str(e)}


@app.post("/api/gallery/graph")
def gallery_graph(req: GraphRequest):
    with STATE["graph_job_lock"]:
        if STATE["graph_job"]["status"] == "running":
            raise HTTPException(409, "Un calcul de graphe est déjà en cours")
        STATE["graph_job"] = {"status": "running", "done": 0, "total": 0, "phase": "scan", "cancel_requested": False}

    thread = threading.Thread(
        target=_run_graph, args=(req.category, req.top_k, req.min_similarity, req.mode), daemon=True
    )
    thread.start()
    return {"started": True}


@app.get("/api/gallery/graph-progress")
def gallery_graph_progress():
    return STATE["graph_job"]


@app.get("/api/gallery/graph-results")
def gallery_graph_results():
    return STATE["graph_data"]


@app.post("/api/gallery/graph/cancel")
def gallery_graph_cancel():
    if STATE["graph_job"]["status"] == "running":
        STATE["graph_job"]["cancel_requested"] = True
    return STATE["graph_job"]


@app.get("/api/gallery/similar")
def gallery_similar(path: str, top_k: int = 5, min_similarity: float = 0.5):
    try:
        return {"items": graph_module.similar_images(path, top_k, min_similarity)}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/api/gallery/taxonomy")
def gallery_taxonomy(category: str | None = None):
    return gallery_module.taxonomy(category)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
