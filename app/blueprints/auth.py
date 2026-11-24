import time

from flask import (Blueprint, current_app, flash, g, make_response, redirect,
                   render_template, request, session, url_for)

from ..extensions import limiter
from ..security import (normalize_email, safe_next, validate_email,
                        validate_password, validate_username)
from ..services import profiles
from ..supabase_client import AuthApiError, public_client

bp = Blueprint("auth", __name__)

GENERIC_ERROR = "Something went wrong. Please try again."


# ---------------------------------------------------------------- helpers
def _status(err):
    return getattr(err, "status", None) or getattr(err, "status_code", None)


def _text(err):
    return str(err).lower()


def _is_rate_limited(err):
    return _status(err) == 429 or "rate limit" in _text(err)


def _is_unconfirmed(err):
    return getattr(err, "code", None) == "email_not_confirmed" or "not confirmed" in _text(err)


def _cooldown_left(pending):
    elapsed = time.time() - pending.get("sent_at", 0)
    return max(0, int(current_app.config["RESEND_COOLDOWN_SECONDS"] - elapsed))


def _message_page(title, body, button_text, button_url, status=200):
    resp = make_response(render_template(
        "message.html", title=title, body=body,
        button_text=button_text, button_url=button_url), status)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _link_invalid():
    return _message_page(
        "Link Expired",
        "This link is invalid or has expired. Log in to request a new verification email, "
        "or use Forgot Password to reset your password.",
        "Back to Log In", url_for("auth.login"), status=400)


# ---------------------------------------------------------------- login
@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per minute", methods=["POST"])
def login():
    if g.user:
        return redirect(url_for("main.home"))

    nxt = request.values.get("next", "")
    if request.method == "GET":
        return render_template("login.html", email="", next=nxt)

    email = normalize_email(request.form.get("email"))
    password = request.form.get("password") or ""
    if not email or not password:
        flash("Please enter your email and password.", "error")
        return render_template("login.html", email=email, next=nxt), 400

    try:
        res = public_client().auth.sign_in_with_password({"email": email, "password": password})
    except AuthApiError as err:
        if _is_unconfirmed(err):
            # Password benar tetapi email belum diverifikasi -> arahkan ke halaman "Check Your Email".
            session["pending"] = {"email": email, "uid": None, "username": None, "sent_at": 0}
            flash("Please verify your email before logging in.", "info")
            return redirect(url_for("auth.check_email"))
        if _is_rate_limited(err):
            flash("Too many attempts. Please wait a moment and try again.", "error")
            return render_template("login.html", email=email, next=nxt), 429
        flash("Invalid email or password.", "error")
        return render_template("login.html", email=email, next=nxt), 401
    except Exception:
        current_app.logger.exception("login failed")
        flash(GENERIC_ERROR, "error")
        return render_template("login.html", email=email, next=nxt), 503

    user = res.user
    profile = profiles.get_profile(str(user.id)) if user else None
    if not profile:
        flash("Your account isn't set up correctly. Please contact support.", "error")
        return render_template("login.html", email=email, next=nxt), 500
    if not profile["is_active"]:
        flash("This account has been deactivated.", "error")
        return render_template("login.html", email=email, next=nxt), 403

    session.clear()  # cegah session fixation
    session.permanent = True
    session["uid"] = profile["id"]
    session["sv"] = profile["session_version"]
    try:
        profiles.touch_login(profile["id"])
    except Exception:
        current_app.logger.exception("touch_login failed")
    return redirect(safe_next(request.form.get("next")))


# ---------------------------------------------------------------- sign up
def _signup_error(message, email, username, status):
    flash(message, "error")
    return render_template("signup.html", email=email, username=username), status


@bp.route("/signup", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def signup():
    if g.user:
        return redirect(url_for("main.home"))
    if request.method == "GET":
        return render_template("signup.html", email="", username="")

    email = normalize_email(request.form.get("email"))
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    error = validate_email(email) or validate_username(username) or validate_password(password)
    if error:
        return _signup_error(error, email, username, 400)

    try:
        if not profiles.username_available(username):
            return _signup_error("That username is already taken.", email, username, 409)

        res = public_client().auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"username": username}},
        })
    except AuthApiError as err:
        current_app.logger.warning("sign_up failed: %s", err)
        if _is_rate_limited(err):
            msg = "Too many emails were sent recently. Please wait a few minutes and try again."
        elif "password" in _text(err):
            msg = "Please choose a stronger password."
        else:
            msg = ("We couldn't create your account. The username may have just been taken, "
                   "so try another one.")
        return _signup_error(msg, email, username, 400)
    except Exception:
        current_app.logger.exception("signup failed")
        return _signup_error(GENERIC_ERROR, email, username, 503)

    if res.session is not None:
        # Email confirmation dimatikan di dashboard Supabase -> akun langsung aktif.
        current_app.logger.warning("Supabase returned a session on sign-up: 'Confirm email' is OFF.")
        flash("Account created. You can now log in.", "success")
        return redirect(url_for("auth.login"))

    user = res.user
    # identities kosong = email itu sudah terdaftar (Supabase sengaja menyamarkannya).
    is_new = bool(user and getattr(user, "identities", None))
    session["pending"] = {
        "email": email,
        "uid": str(user.id) if is_new else None,
        "username": username,
        "sent_at": time.time(),
    }
    return redirect(url_for("auth.check_email"))


@bp.get("/check-email")
def check_email():
    pending = session.get("pending")
    if not pending:
        return redirect(url_for("auth.signup"))
    return render_template("check_email.html", email=pending["email"],
                           cooldown=_cooldown_left(pending))


@bp.post("/check-email/resend")
@limiter.limit("6 per hour")
def resend():
    pending = session.get("pending")
    if not pending:
        return redirect(url_for("auth.signup"))

    wait = _cooldown_left(pending)
    if wait > 0:
        flash(f"Please wait {wait} seconds before requesting another email.", "info")
        return redirect(url_for("auth.check_email"))

    try:
        public_client().auth.resend({"type": "signup", "email": pending["email"]})
    except AuthApiError as err:
        current_app.logger.warning("resend failed: %s", err)
        if _is_rate_limited(err):
            flash("Please wait a minute before requesting another email.", "error")
        else:
            flash("We couldn't send the email. Please try again later.", "error")
    except Exception:
        current_app.logger.exception("resend failed")
        flash(GENERIC_ERROR, "error")
    else:
        pending["sent_at"] = time.time()
        session["pending"] = pending
        flash("Verification email sent.", "success")
    return redirect(url_for("auth.check_email"))


@bp.post("/signup/cancel")
def signup_cancel():
    """'Back to Sign Up' di halaman Check Your Email."""
    pending = session.pop("pending", None)
    if pending and pending.get("uid"):
        profiles.discard_unconfirmed(pending["uid"], pending.get("username"))
    return redirect(url_for("auth.signup"))


# ---------------------------------------------------------------- tautan dari email
@bp.get("/auth/confirm")
def confirm():
    token_hash = request.args.get("token_hash", "").strip()
    otp_type = request.args.get("type", "").strip().lower()
    if otp_type == "signup":
        otp_type = "email"
    if not token_hash or otp_type not in ("email", "recovery"):
        return _link_invalid()

    try:
        res = public_client().auth.verify_otp({"token_hash": token_hash, "type": otp_type})
    except AuthApiError:
        return _link_invalid()
    except Exception:
        current_app.logger.exception("verify_otp failed")
        return _message_page("Something Went Wrong", GENERIC_ERROR,
                             "Back to Log In", url_for("auth.login"), status=503)

    if not res or not res.user:
        return _link_invalid()

    if otp_type == "recovery":
        session["reset"] = {"uid": str(res.user.id), "ts": time.time()}
        return redirect(url_for("auth.reset_password"))

    session.pop("pending", None)
    return _message_page("Email Verified",
                         "Your email has been verified. You can now log in.",
                         "Log In", url_for("auth.login"))


# ---------------------------------------------------------------- forgot / reset password
@bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("forgot_password.html", email="")

    email = normalize_email(request.form.get("email"))
    error = validate_email(email)
    if error:
        flash(error, "error")
        return render_template("forgot_password.html", email=email), 400

    try:
        public_client().auth.reset_password_for_email(email)
    except AuthApiError as err:
        current_app.logger.warning("reset_password_for_email failed: %s", err)
        if _is_rate_limited(err):
            flash("Please wait a minute before requesting another email.", "error")
            return render_template("forgot_password.html", email=email), 429
    except Exception:
        current_app.logger.exception("forgot_password failed")

    # Selalu tampilkan pesan yang sama agar tidak membocorkan email mana yang terdaftar.
    flash("If an account exists for that email, a reset link is on its way. "
          f"It is valid for {current_app.config['VERIFY_LINK_MINUTES']} minutes.", "success")
    return render_template("forgot_password.html", email=""), 200


def _reset_uid():
    data = session.get("reset")
    if not data:
        return None
    if time.time() - data["ts"] > current_app.config["RESET_SESSION_SECONDS"]:
        session.pop("reset", None)
        return None
    return data["uid"]


@bp.route("/reset-password", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def reset_password():
    uid = _reset_uid()
    if not uid:
        return _link_invalid()
    if request.method == "GET":
        return render_template("reset_password.html")

    password = request.form.get("password") or ""
    confirm = request.form.get("confirm") or ""
    error = validate_password(password)
    if not error and password != confirm:
        error = "Passwords do not match."
    if error:
        flash(error, "error")
        return render_template("reset_password.html"), 400

    try:
        profiles.set_password(uid, password)
        profiles.bump_session_version(uid)
    except Exception as err:
        current_app.logger.warning("reset password failed: %s", err)
        flash("Please choose a stronger password." if "password" in _text(err) else GENERIC_ERROR, "error")
        return render_template("reset_password.html"), 400

    session.pop("reset", None)
    flash("Your password has been updated. Please log in.", "success")
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------- logout
@bp.post("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
