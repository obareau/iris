"""Fast first-pass object detection (YOLOv8n) used to skip the slower CLIP
zero-shot pass whenever the image content is already unambiguous (a clear
person, animal or object filling a good chunk of the frame). Images with no
confident, large-enough detection (typically landscapes) fall through to
CLIP as before.
"""

import classifier

DEVICE = classifier.DEVICE

ANIMAL_NAMES = {
    "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe",
}
PERSON_NAME = "person"

CONF_THRESHOLD = 0.45
MIN_AREA_FRACTION = 0.05  # dominant box must cover at least 5% of the image

_model = None


def _load_model():
    global _model
    if _model is not None:
        return
    from ultralytics import YOLO

    _model = YOLO("yolov8n.pt")
    _model.to(DEVICE)


def _class_to_slug(name: str) -> str:
    if name == PERSON_NAME:
        return "personnes"
    if name in ANIMAL_NAMES:
        return "animaux"
    return "objets"


def detect(path) -> list[dict]:
    """Runs YOLO once and returns every detection as
    {name, conf, area} (area = fraction of the image covered)."""
    _load_model()
    result = _model.predict(str(path), conf=CONF_THRESHOLD, verbose=False)[0]
    dets = []
    if result.boxes is not None and len(result.boxes) > 0:
        img_h, img_w = result.orig_shape
        img_area = img_w * img_h
        for box in result.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            area_fraction = ((x2 - x1) * (y2 - y1)) / img_area
            dets.append({
                "name": result.names[int(box.cls[0])],
                "conf": round(float(box.conf[0]), 3),
                "area": round(area_fraction, 3),
            })
    return dets


def summarize(dets: list[dict]) -> list[dict]:
    """Aggregate detections by class name -> {name, count}, most frequent first."""
    counts: dict[str, int] = {}
    for d in dets:
        counts[d["name"]] = counts.get(d["name"], 0) + 1
    return [{"name": n, "count": c} for n, c in sorted(counts.items(), key=lambda x: -x[1])]


def pick_category(dets: list[dict], available_slugs: set[str]) -> tuple[str, float] | None:
    """From a set of detections, returns (category_slug, confidence) if a
    dominant, large-enough object maps to an available category; else None
    (image should fall through to the slower CLIP pass)."""
    best = None
    best_score = 0.0
    for d in dets:
        if d["area"] < MIN_AREA_FRACTION:
            continue
        score = d["area"] * d["conf"]
        if score > best_score:
            best = (d["name"], d["conf"])
            best_score = score
    if best is None:
        return None
    name, conf = best
    slug = _class_to_slug(name)
    if slug not in available_slugs:
        return None
    return slug, conf
