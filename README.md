# Face Findr

Live-camera face search for event photos, built with Streamlit + DeepFace.

## Folder structure

```
face_findr/
├── app.py                        # Streamlit UI (user tab + admin tab)
├── face_utils.py                 # Face detection & matching pipeline
├── requirements.txt
├── .gitignore
├── README.md
│
├── storage/                      # Storage abstraction layer
│   ├── __init__.py
│   ├── config.py                 # All paths/settings, read from env vars
│   ├── event_store.py            # EventStore interface + local impl
│   ├── photo_store.py            # PhotoStore interface + local impl (+ image validation)
│   └── embedding_cache.py        # EmbeddingCache interface + local pickle impl
│
├── static/                       # Optional: bot.mp4 / loadingg.mp4 for loading screen
│
├── .streamlit/
│   ├── secrets.toml.example      # Copy to secrets.toml and fill in
│   └── secrets.toml              # (you create this — gitignored)
│
├── event_images/                 # Created automatically at runtime — one folder per event
└── embeddings_cache/             # Created automatically at runtime — cached face embeddings
```

## Why the `storage/` layer exists

`app.py` and `face_utils.py` never touch the filesystem directly for events,
photos, or the embedding cache. They call `event_store`, `photo_store`, and
the cache returned by `get_embedding_cache()`. Today those are backed by
local folders and pickle files. When you move to Azure, you add:

- `AzureBlobPhotoStore` in `photo_store.py`
- `AzureTableEventStore` (or similar) in `event_store.py`
- `PostgresEmbeddingCache` in `embedding_cache.py`

...and switch `FACEFINDR_STORAGE_BACKEND` from `local` to whatever you name
the new backend in each `get_*()` factory function. No changes needed in
`app.py` or `face_utils.py`.

## Setup

1. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up admin credentials**:
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```
   Edit `.streamlit/secrets.toml` and set a real `ADMIN_PASSWORD`.

4. **(Optional) Add a loading video**:
   Place `loadingg.mp4` (or `bot.mp4`) in the `static/` folder. If absent,
   the app falls back to an animated CSS loading screen automatically.

5. **(Optional) Override config via environment variables**:
   ```bash
   export FACEFINDR_MATCH_THRESHOLD=0.65
   export FACEFINDR_MAX_WORKERS=4
   export FACEFINDR_EVENTS_DIR=event_images
   export FACEFINDR_CACHE_DIR=embeddings_cache
   ```
   All have working defaults, so this step can be skipped for local dev.

## Running

```bash
streamlit run app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`).

- **User tab**: give consent → pick event → take a live selfie → search.
- **Admin tab**: log in with the credentials from `secrets.toml` → create
  events → upload photos → manage/delete events.

## Notes

- `opencv-python-headless` version in `requirements.txt` was garbled in the
  original file you shared (showed as a redacted IP address) — I've pinned
  it to `4.9.0.80`, a known-good version for this DeepFace/TF combo. Double
  check this matches what you were actually running before deploying.
- No database is used yet — intentional, see project discussion. The
  `storage/` interfaces are the seam for adding one later without a rewrite.
- Per your team's direction, per-event access codes, admin login
  rate-limiting, and upload size caps are intentionally **not** implemented
  in this version.
