import json
import re
import unicodedata
from pathlib import Path

import torch
from PIL import Image

import classifier

DEVICE = classifier.DEVICE
MODEL_ID = "Qwen/Qwen2-VL-2B-Instruct"

_KEYWORDS_INSTRUCTION = "Answer with 3 to 5 short keywords only, separated by commas. No full sentences."

QUESTIONS = {
    "personnes": f"List keywords for this person's hairstyle, hair color and any visible tattoos. {_KEYWORDS_INSTRUCTION}",
    "animaux": f"List keywords for the animal species, color and notable features. {_KEYWORDS_INSTRUCTION}",
    "objets": f"List keywords for the type of machine, device or technology and its notable features. {_KEYWORDS_INSTRUCTION}",
    "autre": f"List keywords for the main subject of this image. {_KEYWORDS_INSTRUCTION}",
}

LANDSCAPE_SUBTYPES = [
    {"slug": "architecture", "prompt": "a photo of a building or architecture",
     "question": f"List keywords for the architectural style and notable structures. {_KEYWORDS_INSTRUCTION}"},
    {"slug": "nature", "prompt": "a photo of a natural landscape with no buildings",
     "question": f"List keywords for the type of natural landscape and its notable features. {_KEYWORDS_INSTRUCTION}"},
]

_model = None
_processor = None
_landscape_text_feats = None


def _load_model():
    global _model, _processor
    if _model is not None:
        return
    from transformers import AutoModelForImageTextToText, AutoProcessor

    _model = AutoModelForImageTextToText.from_pretrained(
        MODEL_ID, torch_dtype=torch.float16
    ).to(DEVICE)
    _model.eval()
    _processor = AutoProcessor.from_pretrained(MODEL_ID)


def _slugify(text: str, max_len: int = 40) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9,]+", "-", text)
    keywords = [k.strip("-") for k in text.split(",") if k.strip("-")]
    if not keywords:
        return ""
    slug = keywords[0][:max_len].rstrip("-")
    for kw in keywords[1:]:
        candidate = f"{slug}-{kw}"
        if len(candidate) > max_len:
            break
        slug = candidate
    return slug


def _question_for(category_slug: str, path: Path) -> str:
    if category_slug == "paysages":
        global _landscape_text_feats
        if _landscape_text_feats is None:
            _landscape_text_feats = classifier.text_embeddings(LANDSCAPE_SUBTYPES)
        st = path.stat()
        emb = classifier.image_embedding(path, st.st_mtime, st.st_size)
        slug, _ = classifier.classify(emb, LANDSCAPE_SUBTYPES, _landscape_text_feats)
        return next(s["question"] for s in LANDSCAPE_SUBTYPES if s["slug"] == slug)
    return QUESTIONS.get(category_slug, QUESTIONS["autre"])


def _ask(image: Image.Image, question: str, max_new_tokens: int = 48) -> str:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image"},
                {"type": "text", "text": question},
            ],
        }
    ]
    text = _processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = _processor(text=[text], images=[image], padding=True, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        generated_ids = _model.generate(**inputs, max_new_tokens=max_new_tokens)
    trimmed = [out[len(inp):] for inp, out in zip(inputs["input_ids"], generated_ids)]
    output = _processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=True)
    return output[0].strip()


def ask(image: Image.Image, question: str, max_new_tokens: int = 48) -> str:
    """Point d'entrée public pour un appel VLM libre (image + question) — utilisé
    par canon.py, qui a besoin d'un prompt propre à lui (verdict de canon contre
    une fiche de lore) plutôt que des mots-clés type extract_detail/refine_attributes."""
    _load_model()
    return _ask(image, question, max_new_tokens)


def extract_detail(path: Path, category_slug: str) -> dict:
    _load_model()
    question = _question_for(category_slug, path)
    img = Image.open(path).convert("RGB")
    img.thumbnail((768, 768))
    answer = _ask(img, question)
    return {"text": answer, "slug": _slugify(answer)}


# ---------------------------------------------------------------------------
# Passe 3 : attributs structurés (un seul appel VLM renvoyant du JSON).
# Chaque entrée = (clé JSON demandée au modèle, libellé affiché en français).
# ---------------------------------------------------------------------------
ATTRIBUTE_SCHEMAS = {
    "personnes": [
        ("hair_color", "Couleur des cheveux"),
        ("hair_length", "Longueur des cheveux"),
        ("facial_hair", "Pilosité faciale"),
        ("glasses", "Lunettes"),
        ("tattoos", "Tatouages visibles"),
        ("clothing", "Tenue"),
        ("pose_or_action", "Pose / posture"),
        ("distinctive_features", "Traits distinctifs"),
    ],
    "paysages": [
        ("scene_type", "Type de scène"),
        ("architectural_style", "Style architectural"),
        ("materials", "Matériaux"),
        ("dominant_colors", "Couleurs dominantes"),
        ("terrain", "Relief / eau"),
        ("mood", "Ambiance"),
    ],
    "animaux": [
        ("species", "Espèce"),
        ("color", "Couleur"),
        ("environment", "Environnement"),
        ("pose_or_action", "Pose / action"),
    ],
    "objets": [
        ("object_type", "Type d'objet / machine"),
        ("apparent_function", "Fonction apparente"),
        ("materials", "Matériaux"),
        ("colors", "Couleurs"),
        ("visible_text_or_brand", "Texte / marque visible"),
    ],
    "autre": [
        ("main_subject", "Sujet principal"),
        ("setting", "Contexte"),
        ("colors", "Couleurs"),
    ],
}

_EMPTY_VALUES = {"", "n/a", "na", "none", "unknown", "not visible", "aucun", "aucune"}


def _parse_attributes(text: str, schema: list[tuple]) -> list[dict]:
    obj = {}
    try:
        start = text.index("{")
        snippet = text[start:]
        if "}" in snippet:
            snippet = snippet[: snippet.rindex("}") + 1]
        try:
            obj = json.loads(snippet)
        except Exception:
            # Tolère un JSON tronqué : récupère les paires "clé": "valeur" présentes.
            for key, _ in schema:
                m = re.search(rf'"{re.escape(key)}"\s*:\s*"([^"]*)"', snippet)
                if m:
                    obj[key] = m.group(1)
    except ValueError:
        obj = {}
    out = []
    for key, label in schema:
        val = obj.get(key)
        if val is None:
            continue
        if isinstance(val, list):
            val = ", ".join(str(x).strip() for x in val if str(x).strip())
        elif isinstance(val, bool):
            val = "oui" if val else "non"
        else:
            val = str(val).strip()
        if val.lower() in _EMPTY_VALUES:
            continue
        out.append({"label": label, "value": val})
    return out


def refine_attributes(path: Path, category_slug: str) -> list[dict]:
    _load_model()
    schema = ATTRIBUTE_SCHEMAS.get(category_slug, ATTRIBUTE_SCHEMAS["autre"])
    keys = ", ".join(k for k, _ in schema)
    question = (
        f"Analyse this image and answer ONLY with a JSON object with exactly these keys: {keys}. "
        f"Each value must be a short string (max 4 words) describing that aspect, or \"n/a\" if not visible. "
        f"No text before or after the JSON."
    )
    img = Image.open(path).convert("RGB")
    img.thumbnail((768, 768))
    answer = _ask(img, question, max_new_tokens=220)
    return _parse_attributes(answer, schema)
