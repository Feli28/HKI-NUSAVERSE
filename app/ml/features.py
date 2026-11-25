"""Ekstraksi fitur antropometri: MediaPipe FaceLandmarker -> 22 jarak Euclidean 2D.

Isi file ini setia pada feature_extraction.py milikmu (daftar pasangan landmark dan urutan 22 fitur
TIDAK diubah, karena model dilatih dengan urutan itu). Yang dihapus hanya LBP, karena aplikasi memakai
model antropometri saja.
"""
import threading
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# ============================================================
# 1. KONFIGURASI MEDIAPIPE
# ============================================================
BASE_DIR = Path(__file__).resolve().parents[2]          # folder proyek (sejajar run.py)
MODEL_PATH = BASE_DIR / "models" / "face_landmarker.task"
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/"
             "face_landmarker/face_landmarker/float16/1/face_landmarker.task")

LANDMARK_COUNT = 478

LANDMARK_PAIRS = [
    (172, 397), (0, 14), (14, 17), (468, 473), (133, 362), (33, 263), (98, 327),
    (168, 2), (168, 4), (61, 291), (168, 152), (2, 152), (159, 145), (386, 374),
    (33, 133), (263, 362), (468, 159), (468, 145), (473, 386), (473, 374),
    (37, 267), (2, 0),
]

ANTHROPOMETRY_FEATURE_NAMES = [
    "Mandible Width", "Upper Vermilion Height", "Lower Vermilion Height",
    "Interpupillary Distance (IPD)", "Intercanthal Width", "Biocular Width",
    "Nasal Width", "Nasal Height", "Nasal Length", "Mouth Width",
    "Morphological Facial Height", "Lower Facial Height", "PFH Left", "PFH Right",
    "HPA Left", "HPA Right", "Approx MRD1 Left", "Approx MRD2 Left",
    "Approx MRD1 Right", "Approx MRD2 Right", "Approx Philtrum Width",
    "Approx Philtrum Height",
]

_face_landmarker = None
_LANDMARK_LOCK = threading.RLock()


# ============================================================
# 2. MEMUAT MODEL MEDIAPIPE
# ============================================================
def _ensure_model_file():
    if MODEL_PATH.is_file() and MODEL_PATH.stat().st_size > 0:
        return
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = MODEL_PATH.with_suffix(".task.tmp")
    try:
        urllib.request.urlretrieve(MODEL_URL, str(tmp_path))
        if not tmp_path.is_file() or tmp_path.stat().st_size == 0:
            raise RuntimeError("Downloaded model file is empty.")
        tmp_path.replace(MODEL_PATH)
    except Exception as exc:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise FileNotFoundError(
            f"MediaPipe model not found: {MODEL_PATH}. "
            "Download face_landmarker.task and put it in the models/ folder."
        ) from exc


def _create_face_landmarker():
    _ensure_model_file()
    options = vision.FaceLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.IMAGE,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
    )
    return vision.FaceLandmarker.create_from_options(options)


def _get_face_landmarker():
    global _face_landmarker
    with _LANDMARK_LOCK:
        if _face_landmarker is None:
            _face_landmarker = _create_face_landmarker()
        return _face_landmarker


def _validate_bgr_image(image_bgr):
    if image_bgr is None:
        raise ValueError("Empty image.")
    if not isinstance(image_bgr, np.ndarray):
        raise TypeError("Image must be a numpy.ndarray.")
    if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        raise ValueError("Image must have three BGR channels.")
    if image_bgr.size == 0:
        raise ValueError("Empty image.")
    if image_bgr.dtype != np.uint8:
        raise TypeError(f"Pixel format must be uint8, not {image_bgr.dtype}.")


# ============================================================
# 3. DETEKSI LANDMARK
# ============================================================
def detect_landmarks(image_bgr):
    """Satu crop wajah BGR uint8 -> list array float32 (478, 3). Kosong bila wajah tak ditemukan."""
    if image_bgr is None:
        return []
    _validate_bgr_image(image_bgr)

    image_rgb = np.ascontiguousarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB), dtype=np.uint8)
    height, width = image_rgb.shape[:2]
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)

    with _LANDMARK_LOCK:
        result = _get_face_landmarker().detect(mp_image)

    if not result.face_landmarks:
        return []

    all_landmarks = []
    for face in result.face_landmarks:
        points = np.asarray(
            [[lm.x * width, lm.y * height, lm.z * width] for lm in face], dtype=np.float32)
        if points.shape == (LANDMARK_COUNT, 3):
            all_landmarks.append(points)
    return all_landmarks


# ============================================================
# 4. ANTROPOMETRI 22 FITUR
# ============================================================
def extract_antropometri22(landmarks):
    """22 jarak Euclidean 2D (piksel pada crop 510x510), urutan sama dengan saat training."""
    landmarks = np.asarray(landmarks, dtype=np.float32)
    if landmarks.shape != (LANDMARK_COUNT, 3):
        raise ValueError(f"Landmarks must have shape ({LANDMARK_COUNT}, 3), got {landmarks.shape}.")
    if not np.isfinite(landmarks).all():
        raise ValueError("Landmarks contain NaN or infinity.")

    features = np.asarray(
        [float(np.linalg.norm(landmarks[i, :2] - landmarks[j, :2])) for i, j in LANDMARK_PAIRS],
        dtype=np.float32)
    if features.shape != (22,):
        raise ValueError(f"Wrong number of anthropometric features: {features.shape}")
    return features


def close_face_landmarker():
    global _face_landmarker
    with _LANDMARK_LOCK:
        if _face_landmarker is not None:
            _face_landmarker.close()
            _face_landmarker = None
