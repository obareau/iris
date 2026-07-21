import json
import re
import shutil
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "data" / "logs"


def build_dest_folder(dest_root: str, category_label: str, color_mode: str, orientation: str) -> Path:
    return Path(dest_root) / category_label / color_mode / orientation


def _next_index(folder: Path, slug: str) -> int:
    if not folder.is_dir():
        return 1
    pattern = re.compile(rf"^{re.escape(slug)}_(\d+)")
    best = 0
    for p in folder.iterdir():
        m = pattern.match(p.stem)
        if m:
            best = max(best, int(m.group(1)))
    return best + 1


def apply_moves(items: list[dict], dest_root: str) -> dict:
    """items: list of {path, category_slug, category_label, color_mode, orientation}
    Moves+renames files, returns a summary and writes an undo log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    counters: dict[str, int] = {}
    log_entries = []
    errors = []

    for item in items:
        src = Path(item["path"])
        dest_folder = build_dest_folder(
            dest_root, item["category_label"], item["color_mode"], item["orientation"]
        )
        key = str(dest_folder)
        if key not in counters:
            counters[key] = _next_index(dest_folder, item["category_slug"])

        dest_folder.mkdir(parents=True, exist_ok=True)
        details_slug = item.get("details_slug")
        suffix = f"_{details_slug}" if details_slug else ""

        def _make_name(i: int) -> str:
            return f"{item['category_slug']}_{i:03d}{suffix}{src.suffix.lower()}"

        idx = counters[key]
        counters[key] += 1
        dest_path = dest_folder / _make_name(idx)

        while dest_path.exists():
            idx = counters[key]
            counters[key] += 1
            dest_path = dest_folder / _make_name(idx)

        try:
            shutil.move(str(src), str(dest_path))
            log_entries.append({"from": str(src), "to": str(dest_path)})
        except Exception as e:
            errors.append({"path": str(src), "error": str(e)})

    log_file = LOG_DIR / f"apply_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    log_file.write_text(json.dumps(log_entries, ensure_ascii=False, indent=2))

    return {"moved": len(log_entries), "errors": errors, "log_file": str(log_file)}


def last_log() -> Path | None:
    if not LOG_DIR.is_dir():
        return None
    logs = sorted(LOG_DIR.glob("apply_*.json"))
    return logs[-1] if logs else None


def undo_last() -> dict:
    log_file = last_log()
    if log_file is None:
        return {"undone": 0, "message": "Aucune opération à annuler."}

    entries = json.loads(log_file.read_text())
    undone = 0
    errors = []
    for entry in reversed(entries):
        src = Path(entry["to"])
        dest = Path(entry["from"])
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            undone += 1
        except Exception as e:
            errors.append({"path": str(src), "error": str(e)})

    log_file.unlink()
    return {"undone": undone, "errors": errors}
