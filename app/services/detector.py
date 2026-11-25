"""Pipeline deteksi etnis.

  foto -> MTCNN (kotak wajah) -> crop 510x510 -> MediaPipe (478 landmark) -> 22 fitur antropometri
       -> Pipeline sklearn (SimpleImputer -> StandardScaler -> SVC)

PENTING: antro_own_1738_svm.pkl sudah berisi scaler di dalam Pipeline-nya. Fitur MENTAH langsung
diberikan ke pipeline.predict(). Jangan men-scale lagi di luar (hasilnya akan salah).
"""
import base64
import io
import threading
import time
import warnings

import cv2
import joblib
import numpy as np
from PIL import Image, ImageOps

from ..ml import features

IMAGE_SIZE = (510, 510)            # ukuran crop saat training
DETECTION_THRESHOLD = 0.95         # ambang probabilitas MTCNN
MAX_FACES = 5
THUMB_SIZE = 220
Image.MAX_IMAGE_PIXELS = 50_000_000

_state = {"pipeline": None, "mtcnn": None}
_ready = threading.Event()
_error = {"msg": None}
_load_lock = threading.Lock()
_infer_lock = threading.Lock()


# ---------------------------------------------------------------- status
def is_ready():
    return _ready.is_set()


def load_error():
    return _error["msg"]


# ---------------------------------------------------------------- memuat model
def load_pipeline(path):
    """Muat Pipeline dan periksa bahwa isinya sesuai: 22 fitur dengan urutan yang sama seperti training."""
    pipeline = joblib.load(path)
    if not hasattr(pipeline, "predict"):
        raise TypeError("The model file is not a scikit-learn estimator.")

    n_features = getattr(pipeline, "n_features_in_", None)
    if n_features is not None and n_features != 22:
        raise ValueError(f"Model expects {n_features} features, but 22 are produced.")

    names = getattr(pipeline, "feature_names_in_", None)
    if names is not None and list(names) != features.ANTHROPOMETRY_FEATURE_NAMES:
        raise ValueError("Feature order in the model differs from the extractor "
                         "(features.ANTHROPOMETRY_FEATURE_NAMES).")
    return pipeline


def _load_mtcnn():
    import torch
    from facenet_pytorch import MTCNN

    torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
    return MTCNN(keep_all=True, device="cpu")


def load_all(model_path):
    with _load_lock:
        if _state["pipeline"] is None:
            _state["pipeline"] = load_pipeline(model_path)
        if _state["mtcnn"] is None:
            _state["mtcnn"] = _load_mtcnn()
    # pemanasan: paksa MTCNN dan MediaPipe menginisialisasi diri sekarang, bukan saat request pertama
    _state["mtcnn"].detect(Image.fromarray(np.zeros((480, 640, 3), dtype=np.uint8)))
    features.detect_landmarks(np.zeros((IMAGE_SIZE[1], IMAGE_SIZE[0], 3), dtype=np.uint8))


def start_preload(app):
    """Muat semua model di thread latar saat server menyala, supaya request pertama pengguna cepat."""
    def worker():
        with app.app_context():
            t0 = time.perf_counter()
            try:
                load_all(app.config["ANTRO_MODEL_PATH"])
                _ready.set()
                app.logger.info("Detector ready in %.1fs (classes: %s)", time.perf_counter() - t0,
                                list(getattr(_state["pipeline"], "classes_", [])))
            except Exception as exc:
                _error["msg"] = str(exc)
                app.logger.exception("Detector failed to load")

    threading.Thread(target=worker, name="detector-preload", daemon=True).start()


# ---------------------------------------------------------------- membaca gambar
class ImageError(ValueError):
    """Gambar tidak bisa dipakai (pesan aman untuk ditampilkan ke pengguna)."""


def read_image(data, max_side):
    """bytes -> PIL RGB (JPEG/PNG), orientasi EXIF dikoreksi, sisi terpanjang <= max_side."""
    try:
        image = Image.open(io.BytesIO(data))
        if image.format not in ("JPEG", "PNG"):
            raise ImageError("Please use a JPG or PNG photo.")
        image = ImageOps.exif_transpose(image).convert("RGB")
    except ImageError:
        raise
    except Exception as exc:
        raise ImageError("That file couldn't be read as an image. Please use a JPG or PNG photo.") from exc

    scale = min(1.0, max_side / max(image.size))
    if scale < 1.0:
        image = image.resize((round(image.width * scale), round(image.height * scale)),
                             Image.Resampling.LANCZOS)
    return image


# ---------------------------------------------------------------- langkah-langkah pipeline
def detect_face_boxes(image, mtcnn, threshold=DETECTION_THRESHOLD):
    boxes, probs = mtcnn.detect(image.convert("RGB"))
    if boxes is None or probs is None:
        return []
    found = []
    for box, prob in zip(boxes, probs):
        if box is None or prob is None:
            continue
        box = np.asarray(box, dtype=np.float64)
        prob = float(prob)
        if box.shape != (4,) or not np.isfinite(box).all() or not np.isfinite(prob) or prob < threshold:
            continue
        if box[2] > box[0] and box[3] > box[1]:
            found.append((box, prob))
    found.sort(key=lambda d: (d[0][2] - d[0][0]) * (d[0][3] - d[0][1]), reverse=True)   # terbesar dulu
    return found[:MAX_FACES]


def crop_face(image, box):
    """Crop persegi di sekitar wajah, dibuat SAMA dengan saat training, lalu resize ke 510x510."""
    width, height = image.size
    x1, y1, x2, y2 = map(float, box)
    bw, bh = x2 - x1, y2 - y1
    if bw <= 0 or bh <= 0:
        raise ValueError("Invalid face box.")

    cx = x1 + bw / 2
    cy = y1 + bh / 2 + bh * 0.05
    half = max(bw, bh) * 0.95 / 2
    left, top = max(0, int(round(cx - half))), max(0, int(round(cy - half)))
    right, bottom = min(width, int(round(cx + half))), min(height, int(round(cy + half)))
    if right <= left or bottom <= top:
        raise ValueError("Empty face crop.")
    return image.crop((left, top, right, bottom)).resize(IMAGE_SIZE, Image.Resampling.LANCZOS)


def predict_label(crop_rgb):
    bgr = cv2.cvtColor(np.asarray(crop_rgb), cv2.COLOR_RGB2BGR)
    landmarks = features.detect_landmarks(bgr)
    if not landmarks:
        raise ValueError("Facial landmarks could not be found.")

    feats = np.asarray(features.extract_antropometri22(landmarks[0]), dtype=np.float64).reshape(1, -1)
    if not np.isfinite(feats).all():
        raise ValueError("Invalid facial measurements.")

    with warnings.catch_warnings():       # pipeline dilatih dengan nama fitur; kita memberi array numpy
        warnings.simplefilter("ignore")
        return str(_state["pipeline"].predict(feats)[0])


def to_data_url(image_rgb, size=THUMB_SIZE, quality=82):
    thumb = image_rgb.resize((size, size), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    thumb.save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------- titik masuk
def analyze(image, want_thumb=True, blocking=True, wait_seconds=25):
    """Jalankan pipeline pada satu gambar. Hasilnya dict siap di-JSON-kan:

    status: ok | no_face | error | busy
    label / box / detection_score / thumb : milik wajah utama (kotak terbesar yang berhasil dianalisis)
    faces: semua wajah (maks 5) ; image_size: ukuran gambar yang dianalisis (untuk menskalakan box)
    """
    if not _infer_lock.acquire(blocking=blocking, timeout=wait_seconds if blocking else -1):
        return {"status": "busy"}
    try:
        detections = detect_face_boxes(image, _state["mtcnn"])
        base = {"image_size": list(image.size), "n_faces": len(detections), "faces": []}
        if not detections:
            return {**base, "status": "no_face"}

        crops = {}
        for index, (box, prob) in enumerate(detections, start=1):
            face = {"index": index, "box": [int(v) for v in box], "detection_score": round(prob, 4),
                    "label": None, "error": None}
            try:
                crops[index] = crop_face(image, box)
                face["label"] = predict_label(crops[index])
            except Exception as exc:
                face["error"] = str(exc)
            base["faces"].append(face)

        primary = next((f for f in base["faces"] if f["label"]), None)    # sudah terurut: terbesar dulu
        if primary is None:
            return {**base, "status": "error", "message": base["faces"][0]["error"]}

        return {
            **base, "status": "ok",
            "label": primary["label"], "box": primary["box"], "detection_score": primary["detection_score"],
            "thumb": to_data_url(crops[primary["index"]]) if want_thumb else None,
        }
    finally:
        _infer_lock.release()
