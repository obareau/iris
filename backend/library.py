"""Bibliothèque — liste de dossiers déjà classés surveillés par Iris, comme
un catalogue Lightroom : plusieurs sources (disque externe, imports séparés)
vues comme une seule collection, sans avoir à retaper un chemin dans chaque
onglet. Persistée dans un simple fichier JSON — pas de base de données pour
une poignée de chemins."""

import json
from pathlib import Path

LIBRARY_FILE = Path(__file__).parent.parent / "data" / "library.json"


def list_folders() -> list[str]:
    if not LIBRARY_FILE.is_file():
        return []
    try:
        return json.loads(LIBRARY_FILE.read_text()).get("folders", [])
    except Exception:
        return []


def add_folder(path: str) -> list[str]:
    folder = str(Path(path).expanduser().resolve())
    if not Path(folder).is_dir():
        raise NotADirectoryError(f"Dossier introuvable : {folder}")
    folders = list_folders()
    if folder not in folders:
        folders.append(folder)
        _save(folders)
    return folders


def remove_folder(path: str) -> list[str]:
    folders = [f for f in list_folders() if f != path]
    _save(folders)
    return folders


def _save(folders: list[str]) -> None:
    LIBRARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    LIBRARY_FILE.write_text(json.dumps({"folders": folders}, indent=2))
