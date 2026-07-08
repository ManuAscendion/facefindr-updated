"""
PhotoStore: save/read/list/delete photo bytes for an event.

Today: local filesystem, one folder per event.
Later: Azure Blob Storage, one container (or prefix) per event.
Everything outside this file works with photo *names* and *bytes*,
never with `Path.write_bytes()` directly.
"""
import io
from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .config import config


class InvalidImageError(Exception):
    """Raised when uploaded bytes are not a decodable image."""


def validate_image_bytes(data: bytes) -> None:
    """
    Verify that `data` is actually a loadable image, not just a file
    with an image-like extension. Raises InvalidImageError if not.
    This is cheap (Pillow decodes header + does a verify pass) and
    catches renamed/corrupt files before they hit the matching pipeline.
    """
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()  # checks structure without fully decoding pixels
    except (UnidentifiedImageError, OSError, SyntaxError) as e:
        raise InvalidImageError(f"File is not a valid image: {e}") from e


class PhotoStore(ABC):
    @abstractmethod
    def save_photo(self, event_name: str, filename: str, data: bytes) -> None:
        ...

    @abstractmethod
    def list_photo_paths(self, event_name: str) -> list[Path]:
        """Return local-filesystem paths usable by the face-matching pipeline."""
        ...

    @abstractmethod
    def get_photo_bytes(self, event_name: str, filename: str) -> bytes:
        ...

    @abstractmethod
    def delete_all_photos(self, event_name: str) -> None:
        ...

    @abstractmethod
    def delete_photo(self, event_name: str, filename: str) -> None:
        ...


class LocalPhotoStore(PhotoStore):
    def __init__(self, root_dir: Path = None):
        self.root_dir = root_dir or config.EVENTS_ROOT_DIR

    def _event_dir(self, event_name: str) -> Path:
        return self.root_dir / event_name

    def save_photo(self, event_name: str, filename: str, data: bytes) -> None:
        validate_image_bytes(data)  # raises InvalidImageError if bad
        dest = self._event_dir(event_name) / filename
        dest.write_bytes(data)

    def list_photo_paths(self, event_name: str) -> list[Path]:
        folder = self._event_dir(event_name)
        if not folder.exists():
            return []
        return sorted(
            p for p in folder.iterdir()
            if p.suffix.lower() in config.SUPPORTED_EXTENSIONS
        )

    def get_photo_bytes(self, event_name: str, filename: str) -> bytes:
        return (self._event_dir(event_name) / filename).read_bytes()

    def delete_all_photos(self, event_name: str) -> None:
        folder = self._event_dir(event_name)
        if not folder.exists():
            return
        for img in folder.iterdir():
            if img.suffix.lower() in config.SUPPORTED_EXTENSIONS:
                img.unlink(missing_ok=True)

    def delete_photo(self, event_name: str, filename: str) -> None:
        (self._event_dir(event_name) / filename).unlink(missing_ok=True)


def get_photo_store() -> PhotoStore:
    """Factory — add an AzureBlobPhotoStore branch here when migrating."""
    if config.STORAGE_BACKEND == "local":
        return LocalPhotoStore()
    raise NotImplementedError(
        f"No PhotoStore implementation for backend '{config.STORAGE_BACKEND}' yet. "
        "Add one here (e.g. AzureBlobPhotoStore) when you migrate."
    )