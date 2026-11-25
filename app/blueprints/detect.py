"""Alur deteksi: pilih sumber -> analisis -> hasil -> detail etnis / pilih manual -> jelajah budaya."""
from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect,
                   render_template, request, url_for)

from ..data import ethnicities
from ..extensions import limiter
from ..security import login_required
from ..services import detector
from ..services import history as history_svc

bp = Blueprint("detect", __name__)


# ---------------------------------------------------------------- halaman
@bp.get("/detect/upload")
@login_required
def upload_page():
    return render_template("detect_upload.html")


@bp.get("/detect/photo")
@login_required
def photo_page():
    return render_template("detect_photo.html")


@bp.get("/detect/live")
@login_required
def live_page():
    return render_template("detect_live.html")


# ---------------------------------------------------------------- API
@bp.get("/api/detect/status")
@login_required
def status():
    return jsonify(ready=detector.is_ready(), error=detector.load_error())


def _error(message, code=400):
    return jsonify(status="error", message=message), code


@bp.post("/api/detect")
@limiter.limit("120 per minute")
@login_required
def detect():
    """multipart: image (JPG/PNG), source = upload | photo | live, frame = 1 (frame live: tidak dicatat)."""
    cfg = current_app.config
    source = request.form.get("source", "")
    if source not in cfg["SOURCES"]:
        return _error("Invalid source.")
    is_frame = request.form.get("frame") == "1" and source == "live"

    if not detector.is_ready():
        if detector.load_error():
            current_app.logger.error("detector unavailable: %s", detector.load_error())
            return _error("The detector is unavailable right now. Please try again later.", 503)
        return jsonify(status="loading", message="The detector is still starting up. Please wait a moment."), 503

    file = request.files.get("image")
    data = file.read() if file else b""
    if not data:
        return _error("Please choose a photo first.")
    if len(data) > cfg["MAX_UPLOAD_MB"] * 1024 * 1024:
        return _error(f"The photo is too large (maximum {cfg['MAX_UPLOAD_MB']} MB).", 413)

    try:
        image = detector.read_image(data, cfg["MAX_SIDE_LIVE"] if source == "live" else cfg["MAX_SIDE_PHOTO"])
    except detector.ImageError as exc:
        return _error(str(exc))

    try:
        result = detector.analyze(image, want_thumb=not is_frame, blocking=not is_frame)
    except Exception:
        current_app.logger.exception("analyze failed")
        if not is_frame:
            history_svc.log_error(g.user["id"], source, "antro", "internal error")
        return _error("Something went wrong while analyzing the photo. Please try again.", 500)

    if result["status"] == "busy":                       # hanya terjadi untuk frame live: lewati saja
        return jsonify(status="busy")

    if result["status"] == "no_face":
        result["message"] = ("We couldn't find a face. Try a clear, front-facing photo with good lighting.")
    elif result["status"] == "error":
        result["message"] = "We couldn't analyze this face. Please try another photo."
    else:
        info = ethnicities.by_label(result["label"])
        result["slug"], result["display_name"] = info["slug"], info["name"]
        if len(result["faces"]) > 1:
            result["note"] = "More than one face was found. The largest one was analyzed."

    if not is_frame:          # frame live tidak dicatat; hasil akhir live dicatat klien lewat /api/predictions
        try:
            row = history_svc.record_prediction(
                g.user["id"], source, "antro", result["n_faces"],
                result.get("label"), result.get("detection_score"),
                result["faces"] or None,
                "error" if result["status"] == "error" else "ok",
                result.get("message") if result["status"] == "error" else None)
            result["prediction_id"] = row["id"]
        except Exception:
            current_app.logger.exception("could not record prediction")
            result["prediction_id"] = None

    return jsonify(result)


# ---------------------------------------------------------------- hasil & etnis
def _pid():
    """prediction_id dari query/form bila berupa UUID milik user ini, selain itu None."""
    import uuid
    raw = request.values.get("pid", "")
    try:
        pid = str(uuid.UUID(raw))
    except ValueError:
        return None
    return pid if history_svc.owns_prediction(pid, g.user["id"]) else None


@bp.get("/ethnicity/<slug>")
@login_required
def ethnicity(slug):
    info = ethnicities.by_slug(slug)
    if not info:
        abort(404)
    return render_template("ethnicity.html", e=info, pid=_pid())


@bp.route("/select-ethnicity", methods=["GET", "POST"])
@login_required
def select_ethnicity():
    """'Select Manual': pengguna memilih etnisnya sendiri bila hasil model kurang tepat."""
    pid = _pid()
    if request.method == "POST":
        info = next((e for e in ethnicities.ETHNICITIES if e["label"] == request.form.get("label")), None)
        if not info:
            flash("Please choose one of the options.", "error")
            return redirect(url_for("detect.select_ethnicity", pid=pid))
        if pid:
            row = history_svc.get_prediction(pid, g.user["id"])
            if row and row.get("result_label"):          # catat sebagai feedback untuk penelitian
                history_svc.save_feedback(pid, g.user["id"], row["result_label"] == info["label"], info["label"])
        return redirect(url_for("detect.ethnicity", slug=info["slug"], pid=pid))
    return render_template("select_ethnicity.html", items=ethnicities.ETHNICITIES, pid=pid)


@bp.get("/explore/<slug>")
@login_required
def explore(slug):
    info = ethnicities.by_slug(slug)
    if not info:
        abort(404)
    return render_template("explore.html", e=info)
