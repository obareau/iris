"""Écrit dans le fichier lui-même (EXIF) ce qu'Iris sait d'une photo, en plus
du sidecar JSON — pour que la donnée survive même hors d'Iris (Windows
Explorer, digiKam, un simple visualisateur d'images qui lit XPComment/
XPKeywords). Le sidecar reste la source de vérité ; ceci n'est qu'un miroir
best-effort. JPEG uniquement — PNG/WEBP n'ont pas ce mécanisme EXIF standard
(nécessiterait des chunks de texte propres à chaque format, pas fait ici)."""

from pathlib import Path

import piexif

JPEG_EXTS = {".jpg", ".jpeg"}


def write_exif(path: Path, sidecar: dict) -> None:
    """`sidecar` : le dict déjà lu/mis à jour par l'appelant (mêmes clés que
    ce qu'écrit `gallery._write_sidecar`) — prend le dict entier plutôt qu'un
    paramètre par champ, pour ne pas faire grossir la signature à chaque
    nouveau champ (rating, aesthetic_score, canon_*, character_name...)."""
    if path.suffix.lower() not in JPEG_EXTS:
        return
    try:
        exif_dict = piexif.load(str(path))
    except Exception:
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

    category_label = sidecar.get("category_label")
    details = sidecar.get("details")
    attrs = sidecar.get("attributes") or []
    rating = sidecar.get("rating") or 0
    aesthetic_score = sidecar.get("aesthetic_score")
    canon_faction = sidecar.get("canon_faction")
    canon_verdict = sidecar.get("canon_verdict")
    character_name = sidecar.get("character_name")

    attrs_text = "; ".join(f"{a['label']}: {a['value']}" for a in attrs)
    description = (details or category_label or "")[:1000]
    comment = f"[Iris] {category_label or '?'}"
    if character_name:
        comment += f" — {character_name}"
    if attrs_text:
        comment += f" — {attrs_text}"
    if rating:
        comment += f" — note {rating}/5"
    if aesthetic_score is not None:
        comment += f" — score esthétique {aesthetic_score}/10 (IA)"
    if canon_faction:
        comment += f" — canon {canon_faction}: {canon_verdict or '?'}"
    keywords_list = [category_label] if category_label else []
    if character_name:
        keywords_list.append(character_name)
    keywords_list += [a["value"] for a in attrs]
    keywords = ", ".join(keywords_list)

    exif_dict.setdefault("0th", {})
    exif_dict["0th"][piexif.ImageIFD.ImageDescription] = description.encode("utf-8", "replace")
    exif_dict["0th"][piexif.ImageIFD.XPComment] = comment.encode("utf-16-le")
    if keywords:
        exif_dict["0th"][piexif.ImageIFD.XPKeywords] = keywords.encode("utf-16-le")

    try:
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, str(path))
    except Exception:
        pass  # best-effort — un JPEG corrompu/atypique ne doit pas faire échouer le sidecar
