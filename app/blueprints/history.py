import math

from flask import (Blueprint, current_app, flash, g, jsonify, redirect,
                   render_template, request, url_for)

from ..extensions import limiter
from ..security import login_required, user_only
from ..services import audit
from ..services import history as history_svc

bp = Blueprint("history", __name__)


def _page(default=1):
    return max(request.values.get("page", default, type=int), 1)


# ---------------------------------------------------------------- riwayat milik sendiri (role: user)
@bp.get("/history")
@user_only
def index():
    per = current_app.config["HISTORY_PAGE_SIZE"]
    page = _page()
    rows, total = history_svc.list_for_user(g.user["id"], page, per)
    fb = history_svc.feedback_map(g.user["id"], [r["id"] for r in rows])
    return render_template("history.html", rows=rows, fb=fb, page=page, total=total,
                           pages=max(math.ceil(total / per), 1),
                           labels=current_app.config["LABELS"])


@bp.post("/history/delete")
@user_only
def delete_all():
    count = history_svc.delete_all(g.user["id"])
    audit.log("history_deleted", actor=g.user, details={"count": count})
    flash(f"{count} prediction{'s' if count != 1 else ''} deleted.", "success")
    return redirect(url_for("history.index"))


@bp.post("/history/<uuid:pred_id>/feedback")
@user_only
def feedback(pred_id):
    back = url_for("history.index", page=_page())
    pred_id = str(pred_id)
    if not history_svc.owns_prediction(pred_id, g.user["id"]):
        flash("Prediction not found.", "error")
        return redirect(back)

    is_correct = request.form.get("is_correct") == "true"
    label = None
    if not is_correct:
        label = history_svc.valid_label(request.form.get("corrected_label"), current_app.config["LABELS"])
        if not label:
            flash("Please choose the correct label.", "error")
            return redirect(back)

    history_svc.save_feedback(pred_id, g.user["id"], is_correct, label)
    flash("Thanks for your feedback!", "success")
    return redirect(back)


# ---------------------------------------------------------------- pencatatan dari frontend (opsional)
@bp.post("/api/predictions")
@limiter.limit("60 per minute")
@login_required
def api_log():
    """Alternatif bila pencatatan dilakukan dari JavaScript setelah /predict selesai.
    Kirim header X-CSRFToken (dari <meta name="csrf-token">). Dipakai semua role."""
    data = request.get_json(silent=True) or {}
    source = data.get("source")
    if source not in current_app.config["SOURCES"]:
        return jsonify(error="invalid source"), 400

    try:
        face_count = int(data.get("face_count", 0))
        score = data.get("detection_score")
        score = None if score is None else float(score)
    except (TypeError, ValueError):
        return jsonify(error="invalid number"), 400
    if not (0 <= face_count <= 50) or (score is not None and not (0 <= score <= 1)):
        return jsonify(error="value out of range"), 400

    details = data.get("details")
    if details is not None and (not isinstance(details, list) or len(details) > 50):
        return jsonify(error="details must be a list (max 50)"), 400

    label = data.get("result_label")
    row = history_svc.record_prediction(
        g.user["id"], source, str(data.get("feature_method") or "unknown")[:30], face_count,
        str(label)[:100] if label else None, score, details,
        "error" if data.get("status") == "error" else "ok",
        str(data.get("error_message") or "")[:500] or None)
    return jsonify(id=row["id"]), 201
