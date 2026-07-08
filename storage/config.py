"""
Central configuration for Face Findr.

Every path, threshold, and setting that might differ between local dev
and an Azure deployment lives here, read from environment variables with
sane local defaults. When you move to Azure, you set different env vars
(or Azure App Settings) — no code changes needed anywhere else.
"""
import os
from pathlib import Path


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


class Config:
    # ── Storage backend selection ──────────────────────────────────────
    # "local" today. Later: "azure_blob" for PhotoStore, "postgres" or
    # "azure_table" for EmbeddingCache. The factory functions in each
    # store module read this to decide which implementation to build.
    STORAGE_BACKEND = os.environ.get("FACEFINDR_STORAGE_BACKEND", "local")

    # ── Local filesystem paths (used when STORAGE_BACKEND == "local") ──
    EVENTS_ROOT_DIR = _env_path("FACEFINDR_EVENTS_DIR", "event_images")
    CACHE_DIR       = _env_path("FACEFINDR_CACHE_DIR", "embeddings_cache")

    # ── Azure placeholders (fill in when you migrate) ──────────────────
    AZURE_STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
    AZURE_BLOB_CONTAINER            = os.environ.get("AZURE_BLOB_CONTAINER", "face-findr-photos")
    AZURE_DB_CONNECTION_STRING      = os.environ.get("AZURE_DB_CONNECTION_STRING", "")

    # ── Matching / model settings ───────────────────────────────────────
    MATCH_THRESHOLD = _env_float("FACEFINDR_MATCH_THRESHOLD", 0.62)
    MAX_WORKERS      = _env_int("FACEFINDR_MAX_WORKERS", 4)

    # ── Admin credentials (kept in st.secrets, not here — see app.py) ──
    # Left as a note: ADMIN_USERNAME / ADMIN_PASSWORD should live in
    # .streamlit/secrets.toml, not in this file or source control.

    # ── Supported file types ────────────────────────────────────────────
    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


config = Config()
