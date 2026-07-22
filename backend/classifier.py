import numpy as np
import torch
from PIL import Image

import cache

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

CONFIDENCE_THRESHOLD = 0.35

DEFAULT_CATEGORIES = [
    {"slug": "personnes", "label": "Personnes", "prompt": "a photo of one or more people"},
    {"slug": "paysages", "label": "Paysages", "prompt": "a photo of a landscape or outdoor scenery"},
    {"slug": "animaux", "label": "Animaux", "prompt": "a photo of an animal"},
    {"slug": "objets", "label": "Objets_documents_schemas", "prompt": "a photo of an object, a document, a screenshot or a technical diagram"},
]
FALLBACK_CATEGORY = {"slug": "autre", "label": "Autre"}

_model = None
_preprocess = None
_tokenizer = None


def _load_model():
    global _model, _preprocess, _tokenizer
    if _model is not None:
        return
    import open_clip

    _model, _, _preprocess = open_clip.create_model_and_transforms(
        "ViT-L-14", pretrained="laion2b_s32b_b82k", device=DEVICE
    )
    _tokenizer = open_clip.get_tokenizer("ViT-L-14")
    _model.eval()


def text_embeddings(categories: list[dict]) -> torch.Tensor:
    _load_model()
    prompts = [c["prompt"] for c in categories]
    with torch.no_grad():
        tokens = _tokenizer(prompts).to(DEVICE)
        feats = _model.encode_text(tokens)
        feats = feats / feats.norm(dim=-1, keepdim=True)
    return feats


def embed_image_raw(img: Image.Image) -> np.ndarray:
    """Encode une image (déjà en mémoire, ex: un crop) sans passer par le
    cache disque — utilisé par identity.py, qui gère son propre cache sous
    une clé distincte (le crop n'est pas l'image entière)."""
    _load_model()
    with torch.no_grad():
        tensor = _preprocess(img).unsqueeze(0).to(DEVICE)
        feat = _model.encode_image(tensor)
        feat = feat / feat.norm(dim=-1, keepdim=True)
    return feat.squeeze(0).cpu().numpy().astype(np.float32)


def image_embedding(path, mtime: float, size: int) -> np.ndarray:
    cached = cache.get_embedding(str(path), mtime, size)
    if cached is not None:
        return cached
    _load_model()
    img = Image.open(path).convert("RGB")
    with torch.no_grad():
        tensor = _preprocess(img).unsqueeze(0).to(DEVICE)
        feat = _model.encode_image(tensor)
        feat = feat / feat.norm(dim=-1, keepdim=True)
    emb = feat.squeeze(0).cpu().numpy().astype(np.float32)
    cache.set_embedding(str(path), mtime, size, emb)
    return emb


class Cancelled(Exception):
    """Levée par batch_image_embeddings quand cancel_check() devient vrai
    entre deux lots — laisse l'appelant décider comment marquer le job."""


def batch_image_embeddings(paths_with_stat: list[tuple], batch_size: int = 64, cancel_check=None):
    """paths_with_stat: list of (path, mtime, size). Yields (path, embedding) pairs,
    using cache where possible and running uncached ones through the model in batches.
    `cancel_check`, si fourni, est interrogé entre deux lots — lève Cancelled si vrai."""
    _load_model()
    results: dict[str, np.ndarray] = {}
    to_compute = []

    for path, mtime, size in paths_with_stat:
        cached = cache.get_embedding(str(path), mtime, size)
        if cached is not None:
            results[str(path)] = cached
        else:
            to_compute.append((path, mtime, size))

    for i in range(0, len(to_compute), batch_size):
        if cancel_check is not None and cancel_check():
            raise Cancelled()
        chunk = to_compute[i : i + batch_size]
        tensors = []
        valid = []
        for path, mtime, size in chunk:
            try:
                img = Image.open(path).convert("RGB")
                tensors.append(_preprocess(img))
                valid.append((path, mtime, size))
            except Exception:
                continue
        if not tensors:
            continue
        batch = torch.stack(tensors).to(DEVICE)
        with torch.no_grad():
            feats = _model.encode_image(batch)
            feats = feats / feats.norm(dim=-1, keepdim=True)
        feats = feats.cpu().numpy().astype(np.float32)
        for (path, mtime, size), emb in zip(valid, feats):
            cache.set_embedding(str(path), mtime, size, emb)
            results[str(path)] = emb

    return results


def classify(embedding: np.ndarray, categories: list[dict], text_feats: torch.Tensor) -> tuple[str, float]:
    emb_t = torch.from_numpy(embedding).to(DEVICE).unsqueeze(0)
    sims = (emb_t @ text_feats.T).squeeze(0)
    probs = torch.softmax(sims * 100, dim=0)
    best_idx = int(torch.argmax(probs).item())
    confidence = float(probs[best_idx].item())
    if confidence < CONFIDENCE_THRESHOLD:
        return FALLBACK_CATEGORY["slug"], confidence
    return categories[best_idx]["slug"], confidence


def classify_scores(embedding: np.ndarray, categories: list[dict], text_feats: torch.Tensor, topk: int = 4) -> list[dict]:
    """Full softmax distribution over categories, sorted best-first, top-k kept.
    Used to surface the runner-up guesses in the inspector."""
    emb_t = torch.from_numpy(embedding).to(DEVICE).unsqueeze(0)
    sims = (emb_t @ text_feats.T).squeeze(0)
    probs = torch.softmax(sims * 100, dim=0)
    pairs = [
        {"slug": categories[i]["slug"], "label": categories[i]["label"], "prob": round(float(probs[i].item()), 3)}
        for i in range(len(categories))
    ]
    pairs.sort(key=lambda x: -x["prob"])
    return pairs[:topk]


def detect_color_mode(path) -> str:
    """Returns 'NB' or 'Couleur' without any model, purely from pixel data.
    Ignore les pixels quasi-blancs/quasi-noirs pour la moyenne de saturation :
    un fond blanc à 50% (très courant sur ces illustrations IA) dilue la
    saturation moyenne et fait passer sous le seuil un sujet pourtant bien
    coloré (bug vécu : personnage en veste camo + accents rouges classé NB
    à cause du fond blanc). Repli sur la moyenne globale si le sujet est trop
    petit pour laisser assez de pixels "informatifs" (ex: logo sur fond noir)."""
    img = Image.open(path).convert("RGB")
    img.thumbnail((64, 64))
    hsv = img.convert("HSV")
    _, s, v = hsv.split()
    sat = np.array(s, dtype=np.float32)
    val = np.array(v, dtype=np.float32)
    informative = (val > 25) & (val < 235)
    if informative.sum() >= sat.size * 0.05:
        mean_sat = sat[informative].mean()
    else:
        mean_sat = sat.mean()
    return "NB" if mean_sat < 15 else "Couleur"


def detect_orientation(path) -> str:
    with Image.open(path) as img:
        w, h = img.size
    return "Paysage" if w >= h else "Portrait"
