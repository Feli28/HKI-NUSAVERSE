"""Riwayat prediksi + feedback. Dipakai oleh halaman Riwayat dan oleh kode inferensi (prediction.py)."""
import re
import threading
import time

from flask import current_app

from ..supabase_client import admin_client
from . import models

_LABEL_RE = re.compile(r"^[\w .\-/]{1,40}$", re.UNICODE)
_live_last = {}            # user_id -> waktu pencatatan live terakhir (memori proses)
_live_lock = threading.Lock()


# ---------------------------------------------------------------- mencatat
def record_prediction(user_id, source, feature_method, face_count, result_label=None,
                      detection_score=None, details=None, status="ok", error_message=None):
    model = models.get_active_model()
    res = admin_client().table("predictions").insert({
        "user_id": user_id,
        "source": source,
        "feature_method": feature_method,
        "model_version": model["version"] if model else "unknown",
        "face_count": face_count,
        "result_label": result_label,
        "detection_score": detection_score,
        "details": details,
        "status": status,
        "error_message": (error_message or "")[:500] or None,
    }).execute()
    return res.data[0]


def live_allowed(user_id):
    interval = current_app.config["LIVE_LOG_INTERVAL_SECONDS"]
    now = time.time()
    with _live_lock:
        if now - _live_last.get(user_id, 0) < interval:
            return False
        _live_last[user_id] = now
        return True


def log_from_results(user_id, source, feature_method, results, live=False):
    """Satu baris pemanggilan dari predict_route.

    `results` = keluaran predict_faces(): list dict dengan kunci
    index, detection_confidence, prediction, error.
    Tidak pernah melempar error (pencatatan tidak boleh merusak prediksi).
    """
    try:
        if source not in current_app.config["SOURCES"]:
            source = "live" if live else "upload"
        if live:
            if not results or not live_allowed(user_id):   # live: hanya bila ada wajah, dan dibatasi
                return None

        ok = [r for r in results if r.get("prediction")]
        errors = [r for r in results if r.get("error")]
        top = max(ok, key=lambda r: r.get("detection_confidence") or 0) if ok else None
        status = "error" if (results and not ok and errors) else "ok"
        score = top.get("detection_confidence") if top else None

        details = [{
            "index": r.get("index"),
            "label": r.get("prediction"),
            "score": None if r.get("detection_confidence") is None else round(float(r["detection_confidence"]), 4),
            "error": r.get("error"),
        } for r in results]

        return record_prediction(
            user_id, source, feature_method, len(results),
            top["prediction"] if top else None,
            None if score is None else float(score),
            details, status,
            errors[0]["error"] if status == "error" else None)
    except Exception:
        current_app.logger.exception("log_from_results failed")
        return None


def log_error(user_id, source, feature_method, message):
    """Catat kegagalan di level request (gambar tak terbaca, model gagal dimuat, dsb.)."""
    try:
        if source not in current_app.config["SOURCES"]:
            source = "upload"
        return record_prediction(user_id, source, feature_method, 0, status="error",
                                 error_message=message)
    except Exception:
        current_app.logger.exception("log_error failed")
        return None


# ---------------------------------------------------------------- membaca (khusus milik sendiri)
def list_for_user(user_id, page=1, per_page=15):
    start = (page - 1) * per_page
    res = (admin_client().table("predictions").select("*", count="exact")
           .eq("user_id", user_id).order("created_at", desc=True)
           .range(start, start + per_page - 1).execute())
    return res.data, (res.count or 0)


def owns_prediction(pred_id, user_id):
    try:
        res = (admin_client().table("predictions").select("id").eq("id", pred_id)
               .eq("user_id", user_id).limit(1).execute())
    except Exception:
        return False
    return bool(res.data)


def get_prediction(pred_id, user_id):
    """Prediksi milik user ini (dict) atau None."""
    try:
        res = (admin_client().table("predictions").select("*").eq("id", pred_id)
               .eq("user_id", user_id).limit(1).execute())
    except Exception:
        return None
    return res.data[0] if res.data else None


def delete_all(user_id):
    """Hapus seluruh riwayat milik user (feedback terkait ikut terhapus). Mengembalikan jumlahnya."""
    res = admin_client().table("predictions").delete().eq("user_id", user_id).execute()
    return len(res.data or [])


# ---------------------------------------------------------------- feedback
def valid_label(label, allowed):
    label = (label or "").strip()
    if allowed:
        return label if label in allowed else None
    return label if _LABEL_RE.match(label) else None


def feedback_map(user_id, prediction_ids):
    if not prediction_ids:
        return {}
    res = (admin_client().table("feedback").select("*").eq("user_id", user_id)
           .in_("prediction_id", prediction_ids).execute())
    return {f["prediction_id"]: f for f in res.data}


def save_feedback(prediction_id, user_id, is_correct, corrected_label):
    admin_client().table("feedback").upsert(
        {"prediction_id": prediction_id, "user_id": user_id, "is_correct": is_correct,
         "corrected_label": None if is_correct else corrected_label},
        on_conflict="prediction_id,user_id",
    ).execute()
