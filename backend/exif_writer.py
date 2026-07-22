"""Écrit dans le fichier lui-même (EXIF) ce qu'Iris sait d'une photo, en plus
du sidecar JSON — pour que la donnée survive même hors d'Iris (Windows
Explorer, digiKam, un simple visualisateur d'images qui lit XPComment/
XPKeywords). Le sidecar reste la source de vérité ; ceci n'est qu'un miroir
best-effort. JPEG uniquement — PNG/WEBP n'ont pas ce mécanisme EXIF standard
(nécessiterait des chunks de texte propres à chaque format, pas fait ici)."""

from pathlib import Path

import piexif

JPEG_EXTS = {".jpg", ".jpeg"}


def write_exif(
    path: Path,
    category_label: str,
    details: str | None,
    attributes: list[dict],
    rating: int = 0,
    aesthetic_score: float | None = None,
) -> None:
    if path.suffix.lower() not in JPEG_EXTS:
        return
    try:
        exif_dict = piexif.load(str(path))
    except Exception:
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

    attrs = attributes or []
    attrs_text = "; ".join(f"{a['label']}: {a['value']}" for a in attrs)
    description = (details or category_label or "")[:1000]
    comment = f"[Iris] {category_label or '?'}"
    if attrs_text:
        comment += f" — {attrs_text}"
    if rating:
        comment += f" — note {rating}/5"
    if aesthetic_score is not None:
        comment += f" — score esthétique {aesthetic_score}/10 (IA)"
    keywords = ", ".join([category_label] + [a["value"] for a in attrs] if category_label else [a["value"] for a in attrs])

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
