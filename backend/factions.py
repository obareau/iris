"""Lecture des fiches de faction du vault Robotariis (~/robotariis-writing/
02-FACTIONS/) pour servir de référence de canon — Iris ne connaît que ce que
les fichiers .md racontent, il ne réécrit ni n'enrichit le lore.

⚠️ Le dossier mélange vraies factions (`type: faction`, `statut: canonique`)
et fiches-glossaire de leurs leaders individuels (`type: faction` aussi, mais
`statut: stub`, ex: daria-sombre.md = "Leader des Renégats") — ces stubs sont
écartés, sinon on obtient des "factions" qui sont en réalité des personnages."""

import re
from pathlib import Path

VAULT_FACTIONS_DIR = Path("/home/olivier/robotariis-writing/02-FACTIONS")

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_SEPARATOR_LINE_RE = re.compile(r"^[\s\-|:]+$")

_factions_cache: list[dict] | None = None


def _clean(text: str) -> str:
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)  # [[slug|Label]] -> Label
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)              # [[slug]] -> slug
    text = re.sub(r"[*_`#|]", " ", text)
    lines = [
        re.sub(r"^\s*-\s+", "", line)
        for line in text.splitlines()
        if not _SEPARATOR_LINE_RE.match(line)
    ]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _section(body: str, heading_substr: str) -> str | None:
    lines = body.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("##") and heading_substr.lower() in line.lower():
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].strip().startswith("##"):
            end = j
            break
    return "\n".join(lines[start:end]).strip() or None


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        fm[key.strip()] = val.strip().strip('"')
    return fm, text[m.end():]


def _load_faction(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(text)
    if fm.get("type") != "faction" or fm.get("statut") == "stub":
        return None
    lore = _section(body, "esthétique") or _section(body, "idéologie") or fm.get("definition", "")
    lore = _clean(lore)
    if not lore:
        return None
    label = fm.get("name", path.stem)
    return {
        "id": path.stem,
        "label": label,
        "lore": lore,
        "prompt": f"{label}: {lore[:220]}",
        "source": str(path),
    }


def list_factions() -> list[dict]:
    """Chargé une fois par process — le lore ne change pas pendant qu'Iris
    tourne ; un redémarrage du service suffit à voir une modification du vault."""
    global _factions_cache
    if _factions_cache is None:
        out = []
        for f in sorted(VAULT_FACTIONS_DIR.rglob("*.md")):
            if f.name == "index.md":
                continue
            try:
                faction = _load_faction(f)
            except Exception:
                faction = None
            if faction:
                out.append(faction)
        _factions_cache = out
    return _factions_cache


def get_faction(faction_id: str) -> dict | None:
    return next((f for f in list_factions() if f["id"] == faction_id), None)
