"""Vérifie si un personnage photographié colle au canon esthétique d'une
faction Robotariis. Deux étapes découplées, chacune réutilisant l'infra
existante d'Iris plutôt qu'un nouveau modèle :
1. Devine la faction par CLIP zero-shot (même mécanisme que la classification
   de catégorie en passe 1, juste avec 36 classes — les fiches de faction du
   vault — au lieu de 5). Aucune affirmation si aucune ne dépasse le seuil.
2. Qwen2-VL lit l'IMAGE et le texte de lore de la faction devinée pour rendre
   un verdict — pas seulement les attributs déjà extraits en passe 2/3, pour
   juger sur ce que l'image montre vraiment plutôt que sur un résumé qui a pu
   perdre l'essentiel.

⚠️ Un premier tri, pas un jugement définitif : la faction devinée peut être
fausse (CLIP zero-shot sur 36 classes assez proches visuellement), et Qwen2-
VL-2B est un petit modèle — le verdict doit rester consultatif."""

import json
import re
from pathlib import Path

from PIL import Image

import classifier
import details as details_module
import factions

CONFIDENCE_THRESHOLD = 0.15  # plus bas que la classif. catégorie (5 classes) —
# 36 factions au style parfois proche donnent une distribution plus plate.

VERDICT_LABELS = {"match": "Conforme", "uncertain": "Douteux", "mismatch": "Hors-canon"}

_faction_categories: list[dict] | None = None
_faction_text_feats = None


def _load_faction_index():
    global _faction_categories, _faction_text_feats
    if _faction_categories is not None:
        return
    facs = factions.list_factions()
    _faction_categories = [{"slug": f["id"], "label": f["label"], "prompt": f["prompt"]} for f in facs]
    _faction_text_feats = classifier.text_embeddings(_faction_categories) if _faction_categories else None


def guess_faction(path: Path) -> dict | None:
    _load_faction_index()
    if not _faction_categories:
        return None
    st = path.stat()
    emb = classifier.image_embedding(path, st.st_mtime, st.st_size)
    scores = classifier.classify_scores(emb, _faction_categories, _faction_text_feats, topk=1)
    if not scores or scores[0]["prob"] < CONFIDENCE_THRESHOLD:
        return None
    return {"id": scores[0]["slug"], "label": scores[0]["label"], "confidence": scores[0]["prob"]}


def _parse_verdict(text: str) -> tuple[str, str]:
    """JSON strict fiable à ~100% sur Qwen2-VL-2B ici, contrairement à un
    format "mot - phrase" que le modèle ignore souvent (testé : il répond
    juste "match" sans la justification demandée). Tolère un JSON entouré de
    ```json ... ``` ou tronqué, même stratégie que details._parse_attributes."""
    obj = {}
    try:
        start = text.index("{")
        snippet = text[start:]
        if "}" in snippet:
            snippet = snippet[: snippet.rindex("}") + 1]
        try:
            obj = json.loads(snippet)
        except Exception:
            m_v = re.search(r'"verdict"\s*:\s*"([^"]*)"', snippet)
            m_r = re.search(r'"reason"\s*:\s*"([^"]*)"', snippet)
            obj = {"verdict": m_v.group(1) if m_v else "", "reason": m_r.group(1) if m_r else ""}
    except ValueError:
        obj = {}
    verdict = str(obj.get("verdict", "")).strip().lower()
    if verdict not in VERDICT_LABELS:
        verdict = "uncertain"
    reason = str(obj.get("reason", "")).strip()[:300] or "Pas de justification renvoyée par le modèle."
    return verdict, reason


def check_canon(path: Path, faction: dict) -> dict:
    lore = (factions.get_faction(faction["id"]) or {}).get("lore", "")[:600]
    question = (
        f"This character is claimed to belong to the '{faction['label']}' faction, "
        f"described as: {lore}. Does the character in this image visually match "
        "that faction's aesthetic and style? "
        'Answer ONLY with a JSON object with exactly these keys: verdict, reason. '
        '"verdict" must be exactly one of "match", "uncertain", "mismatch". '
        '"reason" must be a short sentence (max 20 words) explaining why. No text before or after the JSON.'
    )
    img = Image.open(path).convert("RGB")
    img.thumbnail((768, 768))
    answer = details_module.ask(img, question, max_new_tokens=120)
    verdict, reason = _parse_verdict(answer)
    return {"verdict": verdict, "verdict_label": VERDICT_LABELS[verdict], "reason": reason}
