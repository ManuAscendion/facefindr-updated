"""
EmbeddingCache: get/set/clear cached face embeddings, keyed by a hash
of the source image bytes.

Today: one pickle file per image, in a local folder.
Later: a Postgres table (key, embedding, created_at) or Azure Table
Storage. Everything outside this file calls get()/set()/clear()/delete()
and never touches `pickle` or the filesystem directly.
"""
import hashlib
import pickle
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from .config import config


def hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class EmbeddingCache(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[list]:
        """Return cached embeddings for key, or None if not cached."""
        ...

    @abstractmethod
    def set(self, key: str, embeddings: list) -> None:
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clear the entire cache (e.g. on event delete or manual reset)."""
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...


class LocalPickleEmbeddingCache(EmbeddingCache):
    def __init__(self, cache_dir: Path = None):
        self.cache_dir = cache_dir or config.CACHE_DIR
        self.cache_dir.mkdir(exist_ok=True, parents=True)

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.pkl"

    def get(self, key: str) -> Optional[list]:
        p = self._path(key)
        if not p.exists():
            return None
        try:
            with open(p, "rb") as f:
                return pickle.load(f)
        except Exception:
            p.unlink(missing_ok=True)
            return None

    def set(self, key: str, embeddings: list) -> None:
        try:
            with open(self._path(key), "wb") as f:
                pickle.dump(embeddings, f)
        except Exception:
            pass  # cache write failure shouldn't break matching

    def clear(self) -> None:
        for p in self.cache_dir.glob("*.pkl"):
            p.unlink(missing_ok=True)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


def get_embedding_cache() -> EmbeddingCache:
    """Factory — add a PostgresEmbeddingCache branch here when migrating."""
    if config.STORAGE_BACKEND == "local":
        return LocalPickleEmbeddingCache()
    raise NotImplementedError(
        f"No EmbeddingCache implementation for backend '{config.STORAGE_BACKEND}' yet. "
        "Add one here (e.g. PostgresEmbeddingCache) when you migrate."
    )
