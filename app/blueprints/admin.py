import math
import re

from flask import (Blueprint, abort, current_app, flash, g, redirect,
                   render_template, request, url_for)

from ..security import admin_required
from ..services import audit, models, profiles, stats
from ..supabase_client import AuthApiError, public_client

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _page():
    return max(request.args.get("page", 1, type=int), 1)


# ---------------------------------------------------------------- statistik agregat
@bp.get("/")
@admin_required
def dashboard():
    daily = stats.daily(14)
    fb = [{**row, "pct": round(100 * row["correct"] / row["total"]) if row["total"] else 0}
          for row in stats.feedback_by_model()]
    return render_template(
        "admin/dashboard.html",
        o=stats.overview(),
        daily=daily,
        daily_max=max([d["total"] for d in daily] or [1]),
        by_source=stats.by_source(),
        by_feature=stats.by_feature_method(),
        by_model=stats.by_model(),
        by_label=stats.by_label(),
        fb=fb,
    )


# ---------------------------------------------------------------- akun pengguna
@bp.get("/users")
@admin_required
def users():
    q = re.sub(r"[^A-Za-z0-9_.]", "", request.args.get("q", ""))
    per = current_app.config["USERS_PAGE_SIZE"]
    page = _page()
    rows, total = profiles.list_profiles(q, page, per)
    return render_template("admin/users.html", rows=rows, q=q, page=page, total=total,
                           pages=max(math.ceil(total / per), 1))


def _target(user_id):
    """Akun yang akan diubah. Admin tidak boleh mengubah akunnya sendiri dari sini
    (mencegah terkunci / tidak ada admin tersisa)."""
    target = profiles.get_profile(str(user_id))
    if not target:
        abort(404)
    if target["id"] == g.user["id"]:
        flash("You can't change your own account from here.", "error")
        return None
    return target


def _back():
    return redirect(request.referrer or url_for("admin.users"))


@bp.post("/users/<uuid:user_id>/toggle-active")
@admin_required
def toggle_active(user_id):
    target = _target(user_id)
    if target:
        new_state = not target["is_active"]
        profiles.set_active(target["id"], new_state)
        audit.log("user_activated" if new_state else "user_deactivated", actor=g.user, target=target)
        flash(f"{target['username']} has been {'activated' if new_state else 'deactivated'}.", "success")
    return _back()


@bp.post("/users/<uuid:user_id>/send-reset")
@admin_required
def send_reset(user_id):
    """Kirim email reset password ke pengguna. Admin tidak pernah melihat atau menentukan password."""
    target = _target(user_id)
    if not target:
        return _back()
    try:
        email = profiles.get_email(target["id"])
        if not email:
            raise RuntimeError("no email on file")
        public_client().auth.reset_password_for_email(email)
    except AuthApiError as err:
        current_app.logger.warning("admin reset email failed: %s", err)
        flash("Please wait a minute before sending another reset email."
              if getattr(err, "status", None) == 429 else "Couldn't send the reset email.", "error")
    except Exception:
        current_app.logger.exception("admin reset email failed")
        flash("Couldn't send the reset email.", "error")
    else:
        audit.log("password_reset_sent", actor=g.user, target=target)
        flash(f"A password reset email was sent to {target['username']}.", "success")
    return _back()


@bp.post("/users/<uuid:user_id>/role")
@admin_required
def change_role(user_id):
    role = request.form.get("role")
    if role not in ("user", "admin"):
        abort(400)
    target = _target(user_id)
    if target and target["role"] != role:
        profiles.set_role(target["id"], role)
        audit.log("role_changed", actor=g.user, target=target,
                  details={"from": target["role"], "to": role})
        flash(f"{target['username']} is now {'an admin' if role == 'admin' else 'a user'}.", "success")
    return _back()


# ---------------------------------------------------------------- model aktif
@bp.get("/models")
@admin_required
def models_page():
    return render_template("admin/models.html", rows=models.list_models())


@bp.post("/models")
@admin_required
def add_model():
    name = request.form.get("name", "").strip()[:100]
    version = request.form.get("version", "").strip()[:50]
    desc = request.form.get("description", "").strip()[:300]
    if not name or not version:
        flash("Name and version are required.", "error")
    elif models.add_model(name, version, desc) is None:
        flash("That version is already registered.", "error")
    else:
        audit.log("model_added", actor=g.user, details={"version": version})
        flash("Model added. Activate it when it's ready.", "success")
    return redirect(url_for("admin.models_page"))


@bp.post("/models/<uuid:model_id>/activate")
@admin_required
def activate_model(model_id):
    target = next((m for m in models.list_models() if m["id"] == str(model_id)), None)
    if not target:
        abort(404)
    models.set_active_model(target["id"])
    audit.log("model_activated", actor=g.user, details={"version": target["version"]})
    flash(f"Model {target['version']} is now active.", "success")
    return redirect(url_for("admin.models_page"))


# ---------------------------------------------------------------- audit log
@bp.get("/audit")
@admin_required
def audit_page():
    per = current_app.config["AUDIT_PAGE_SIZE"]
    page = _page()
    rows, total = audit.list_entries(page, per)
    return render_template("admin/audit.html", rows=rows, page=page, total=total,
                           pages=max(math.ceil(total / per), 1))
