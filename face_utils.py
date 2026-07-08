import os
import io
import sys
import logging
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from PIL import Image, ImageEnhance

from storage import get_embedding_cache, hash_file, config

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

IS_WINDOWS = sys.platform == "win32"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("FaceFind")

SUPPORTED_EXTENSIONS = config.SUPPORTED_EXTENSIONS
MODEL_NAME   = "Facenet512"
MIN_FACE_PX  = 20
# Faster detector order: opencv is ~10x faster than retinaface
DETECTORS    = ["opencv", "mtcnn", "retinaface"]
GROUP_PHOTO_THRESHOLD = 3
TMP_DIR      = Path(tempfile.gettempdir()) if IS_WINDOWS else Path("/tmp")

# Single cache instance for this process. The factory decides whether
# this is local-pickle (today) or Postgres/Azure (later) based on config.
_embedding_cache = get_embedding_cache()

# ── Pre-warm model once at import time ────────────────────────────────────────
_MODEL_WARMED = False

def _warm_model():
    global _MODEL_WARMED
    if _MODEL_WARMED:
        return
    try:
        from deepface import DeepFace
        dummy = np.ones((160, 160, 3), dtype=np.uint8) * 128
        dummy_path = str(TMP_DIR / "_warmup.jpg")
        Image.fromarray(dummy).save(dummy_path)
        DeepFace.represent(
            img_path=dummy_path,
            model_name=MODEL_NAME,
            detector_backend="opencv",
            enforce_detection=False,
        )
        os.remove(dummy_path)
        _MODEL_WARMED = True
        log.info("[FaceFind] Model pre-warmed.")
    except Exception as e:
        log.warning(f"[FaceFind] Warm-up skipped: {e}")

_warm_model()

from deepface import DeepFace  # import after env vars set

# ── Utilities ─────────────────────────────────────────────────────────────────

def bytes_to_image_path(image_bytes: bytes, tmp_path: str) -> str:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.save(tmp_path, quality=95)
    return tmp_path


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


# ── Detection ─────────────────────────────────────────────────────────────────

def _represent(img_path: str, detector: str, enforce: bool = False) -> list:
    try:
        return DeepFace.represent(
            img_path=img_path,
            model_name=MODEL_NAME,
            detector_backend=detector,
            enforce_detection=enforce,
            align=True,
        ) or []
    except Exception:
        return []


def _detect_with_detectors(img_path: str, enforce: bool = False) -> list:
    for det in DETECTORS:
        faces = _represent(img_path, det, enforce)
        if faces:
            return faces
    return []


def _deduplicated_add(all_faces, seen, new_faces,
                      x_offset=0, y_offset=0, scale=1.0, grid=30):
    for face in new_faces:
        area = face.get("facial_area", {})
        if area.get("w", 999) < MIN_FACE_PX or area.get("h", 999) < MIN_FACE_PX:
            continue
        ox = round((area.get("x", 0) + x_offset) / scale / grid) * grid
        oy = round((area.get("y", 0) + y_offset) / scale / grid) * grid
        key = (ox, oy)
        if key not in seen:
            seen.add(key)
            all_faces.append(face)


def detect_faces_multi_pass(img_path: str) -> list:
    all_faces, seen = [], set()

    faces = _detect_with_detectors(img_path)
    _deduplicated_add(all_faces, seen, faces)

    if len(all_faces) >= GROUP_PHOTO_THRESHOLD:
        img = Image.open(img_path).convert("RGB")
        w, h = img.size
        tmp = img_path + "_crop"
        crops = [
            (tmp + "_L.jpg",  (0,             0, int(w * 0.55), h), 0,             0),
            (tmp + "_R.jpg",  (int(w * 0.45), 0, w,             h), int(w * 0.45), 0),
            (tmp + "_TC.jpg", (int(w * 0.2),  0, int(w * 0.8),  int(h * 0.6)), int(w * 0.2), 0),
        ]
        for path, box, xoff, yoff in crops:
            img.crop(box).save(path, quality=95)
            crop_faces = _detect_with_detectors(path)
            _deduplicated_add(all_faces, seen, crop_faces, x_offset=xoff, y_offset=yoff)
            if os.path.exists(path):
                os.remove(path)

    if len(all_faces) == 0:
        img = Image.open(img_path).convert("RGB")
        w, h = img.size
        up = img_path + "_up.jpg"
        img.resize((int(w * 1.5), int(h * 1.5)), Image.LANCZOS).save(up, quality=95)
        up_faces = _detect_with_detectors(up)
        _deduplicated_add(all_faces, seen, up_faces, scale=1.5)
        if os.path.exists(up):
            os.remove(up)

    return all_faces


# ── Selfie embeddings ─────────────────────────────────────────────────────────

_SELFIE_VARIANTS = {
    "original":  lambda img: img,
    "brighter":  lambda img: ImageEnhance.Brightness(img).enhance(1.35),
    "darker":    lambda img: ImageEnhance.Brightness(img).enhance(0.70),
    "flipped":   lambda img: img.transpose(Image.FLIP_LEFT_RIGHT),
    "contrast+": lambda img: ImageEnhance.Contrast(img).enhance(1.2),
}


def get_selfie_embeddings(image_path: str) -> list:
    embeddings = []
    base = Image.open(image_path).convert("RGB")

    for name, transform in _SELFIE_VARIANTS.items():
        p = str(TMP_DIR / f"_selfie_{name}.jpg")
        try:
            transform(base).save(p, quality=95)
            faces = _represent(p, "opencv", enforce=True)
            if not faces:
                for det in ["mtcnn", "retinaface"]:
                    faces = _represent(p, det, enforce=True)
                    if faces:
                        break
            if faces:
                emb = np.array(faces[0]["embedding"], dtype=np.float32)
                n = np.linalg.norm(emb)
                if n > 0:
                    embeddings.append(emb / n)
                    log.info(f"  Selfie '{name}': OK")
                else:
                    log.warning(f"  Selfie '{name}': zero-norm, skipped")
            else:
                log.warning(f"  Selfie '{name}': no face detected")
        except Exception as e:
            log.warning(f"  Selfie '{name}': {e}")
        finally:
            if os.path.exists(p):
                os.remove(p)

    if len(embeddings) < 2:
        raise ValueError(
            "Could not extract reliable embeddings from the selfie. "
            "Please use a clear, well-lit, front-facing photo."
        )
    log.info(f"  Total selfie embeddings: {len(embeddings)}")
    return embeddings


def selfie_representative_embedding(embeddings: list) -> np.ndarray:
    avg = np.mean(np.stack(embeddings, axis=0), axis=0)
    n = np.linalg.norm(avg)
    return avg / n if n > 0 else avg


# ── Event image embedding (cached via EmbeddingCache abstraction) ────────────

def get_event_embeddings(img_path: str) -> list:
    """
    Returns cached embeddings for this image if present, otherwise runs
    detection and stores the result via the configured EmbeddingCache
    (local pickle today; swap the backend in storage/config.py later
    without touching this function).
    """
    cache_key = hash_file(img_path)
    cached = _embedding_cache.get(cache_key)
    if cached is not None:
        return cached

    faces      = detect_faces_multi_pass(img_path)
    embeddings = []
    for face in faces:
        emb = np.array(face["embedding"], dtype=np.float32)
        n   = np.linalg.norm(emb)
        if n > 0:
            embeddings.append(emb / n)

    _embedding_cache.set(cache_key, embeddings)
    return embeddings


def clear_embedding_cache():
    _embedding_cache.clear()
    log.info("Embedding cache cleared.")


# ── Matching ──────────────────────────────────────────────────────────────────

def _score_image(img_path, representative_emb, all_selfie_embs, threshold):
    try:
        event_embs = get_event_embeddings(str(img_path))
        if not event_embs:
            return None

        best = max(float(np.dot(representative_emb, ev)) for ev in event_embs)

        if best >= threshold * 0.90:
            best = max(
                float(np.dot(se, ev))
                for se in all_selfie_embs
                for ev in event_embs
            )

        status = "MATCH" if best >= threshold else "miss"
        log.info(f"  {img_path.name}: {best:.4f} [{status}]")

        if best >= threshold:
            return {
                "filename":   img_path.name,
                "filepath":   str(img_path.resolve()),
                "confidence": round(best * 100, 2),
            }
    except Exception as e:
        log.warning(f"  {img_path.name}: error — {e}")
    return None


def find_matching_images(
    selfie_bytes: bytes,
    event_folder: str,
    threshold: float = 0.65,
    tmp_selfie_path: str = "",
    max_workers: int = 4,   # parallel workers — tune to your CPU core count
) -> list:
    if not tmp_selfie_path:
        tmp_selfie_path = str(TMP_DIR / "facefindr_selfie_tmp.jpg")

    bytes_to_image_path(selfie_bytes, tmp_selfie_path)
    log.info("\n[FaceFind] Building selfie embeddings...")
    all_selfie_embs = get_selfie_embeddings(tmp_selfie_path)
    rep_emb         = selfie_representative_embedding(all_selfie_embs)
    log.info(f"  Representative embedding built from {len(all_selfie_embs)} variants.")

    folder = Path(event_folder)
    if not folder.exists():
        raise ValueError(f"Event folder not found: {event_folder}")

    event_images = [
        p for p in folder.iterdir()
        if p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    log.info(f"\n[FaceFind] Scanning {len(event_images)} images "
             f"with {max_workers} parallel workers...\n")

    matched = []

    # Windows: TF has multi-thread issues, stay sequential
    if IS_WINDOWS or max_workers <= 1:
        for img_path in event_images:
            result = _score_image(img_path, rep_emb, all_selfie_embs, threshold)
            if result:
                matched.append(result)
    else:
        # Linux/Mac: parallel embedding extraction (the slow part)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_score_image, img, rep_emb, all_selfie_embs, threshold): img
                for img in event_images
            }
            for future in as_completed(futures):
                result = future.result()
                if result:
                    matched.append(result)

    try:
        if os.path.exists(tmp_selfie_path):
            os.remove(tmp_selfie_path)
    except Exception:
        pass

    matched.sort(key=lambda x: x["confidence"], reverse=True)
    log.info(f"\n[FaceFind] Done. {len(matched)}/{len(event_images)} matched.")
    return matched
