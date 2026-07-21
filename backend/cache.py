import sqlite3
import numpy as np
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "embeddings.sqlite3"


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            path TEXT PRIMARY KEY,
            mtime REAL NOT NULL,
            size INTEGER NOT NULL,
            embedding BLOB NOT NULL
        )
        """
    )
    return conn


def get_embedding(path: str, mtime: float, size: int) -> np.ndarray | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT mtime, size, embedding FROM embeddings WHERE path = ?", (path,)
        ).fetchone()
        if row is None:
            return None
        cached_mtime, cached_size, blob = row
        if cached_mtime != mtime or cached_size != size:
            return None
        return np.frombuffer(blob, dtype=np.float32)
    finally:
        conn.close()


def set_embedding(path: str, mtime: float, size: int, embedding: np.ndarray) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO embeddings (path, mtime, size, embedding) VALUES (?, ?, ?, ?)",
            (path, mtime, size, embedding.astype(np.float32).tobytes()),
        )
        conn.commit()
    finally:
        conn.close()
