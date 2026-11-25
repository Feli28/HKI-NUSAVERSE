from flask import (Blueprint, current_app, flash, g, redirect, render_template,
                   request, session, url_for)

from ..extensions import limiter
from ..security import login_required, validate_password
from ..services import audit, profiles
from ..supabase_client import AuthApiError, public_client

bp = Blueprint("account", __name__)


def _email(user_id):
    try:
        return profiles.get_email(user_id)
    except Exception:
        current_app.logger.exception("could not load email")
        return None


@bp.get("/account")
@login_required
def index():
    return render_template("account.html", email=_email(g.user["id"]))


@bp.post("/account/password")
@limiter.limit("10 per hour")
@login_required
def change_password():
    """Semua role (user dan admin) boleh mengganti password sendiri."""
    current = request.form.get("current") or ""
    new = request.form.get("new") or ""
    confirm = request.form.get("confirm") or ""

    if not current:
        error = "Please enter your current password."
    elif new != confirm:
        error = "Passwords do not match."
    elif new == current:
        error = "Your new password must be different from the current one."
    else:
        error = validate_password(new)

    email = _email(g.user["id"])
    if error:
        flash(error, "error")
        return render_template("account.html", email=email), 400

    if not email:
        flash("Something went wrong. Please try again.", "error")
        return render_template("account.html", email=email), 503

    # Verifikasi password lama dengan mencoba login.
    try:
        public_client().auth.sign_in_with_password({"email": email, "password": current})
    except AuthApiError:
        flash("Your current password is incorrect.", "error")
        return render_template("account.html", email=email), 400

    try:
        profiles.set_password(g.user["id"], new)
    except Exception as err:
        current_app.logger.warning("change password failed: %s", err)
        flash("Please choose a stronger password." if "password" in str(err).lower()
              else "Something went wrong. Please try again.", "error")
        return render_template("account.html", email=email), 400

    # Sesi di perangkat lain berhenti berlaku; sesi ini tetap login.
    session["sv"] = profiles.bump_session_version(g.user["id"])
    audit.log("password_changed", actor=g.user)
    flash("Your password has been updated.", "success")
    return redirect(url_for("account.index"))
