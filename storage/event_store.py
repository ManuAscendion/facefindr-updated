"""
EventStore: create/list/delete events, count photos.

An "event" is just a named bucket of photos (e.g. "Q3 Town Hall").
Today it's a folder. Later it could be a Blob container prefix + a row
in a Postgres/Cosmos table. Everything outside this file talks only to
the interface below, never to `Path` or `os` directly for event logic.
"""
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from .config import config


class EventStore(ABC):
    @abstractmethod
    def list_events(self) -> list[str]:
        """Return event names, most-recently-created first."""
        ...

    @abstractmethod
    def create_event(self, name: str) -> bool:
        """Create a new event. Returns False if it already exists."""
        ...

    @abstractmethod
    def delete_event(self, name: str) -> None:
        ...

    @abstractmethod
    def event_exists(self, name: str) -> bool:
        ...

    @abstractmethod
    def count_photos(self, name: str) -> int:
        ...


class LocalEventStore(EventStore):
    """Events map 1:1 to sub-folders of EVENTS_ROOT_DIR."""

    def __init__(self, root_dir: Path = None):
        self.root_dir = root_dir or config.EVENTS_ROOT_DIR
        self.root_dir.mkdir(exist_ok=True, parents=True)

    def _path(self, name: str) -> Path:
        return self.root_dir / name

    def list_events(self) -> list[str]:
        folders = sorted(
            [p for p in self.root_dir.iterdir() if p.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return [p.name for p in folders]

    def create_event(self, name: str) -> bool:
        folder = self._path(name)
        if folder.exists():
            return False
        folder.mkdir(parents=True, exist_ok=True)
        return True

    def delete_event(self, name: str) -> None:
        shutil.rmtree(self._path(name), ignore_errors=True)

    def event_exists(self, name: str) -> bool:
        return self._path(name).is_dir()

    def count_photos(self, name: str) -> int:
        folder = self._path(name)
        if not folder.exists():
            return 0
        return sum(
            1 for f in folder.iterdir()
            if f.suffix.lower() in config.SUPPORTED_EXTENSIONS
        )


def get_event_store() -> EventStore:
    """
    Factory. Swap the branch below when you add an Azure-backed store —
    nothing else in the codebase needs to change.
    """
    if config.STORAGE_BACKEND == "local":
        return LocalEventStore()
    raise NotImplementedError(
        f"No EventStore implementation for backend '{config.STORAGE_BACKEND}' yet. "
        "Add one here (e.g. AzureTableEventStore) when you migrate."
    )
