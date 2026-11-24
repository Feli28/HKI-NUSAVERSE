import re
from functools import wraps

from flask import abort, g, redirect, request, url_for

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{3,30}$")
RESERVED_USERNAMES = {"admin", "administrator", "root", "support", "moderator", "nusaverse", "system"}


def normalize_email(raw):
    return (raw or "").strip().lower()


def validate_email(email):
    if not email or len(email) > 254 or not EMAIL_RE.match(email):
        return "Please enter a valid email address."
    return None


def validate_username(username):
    if not USERNAME_RE.match(username or ""):
        return "Username must be 3-30 characters: letters, numbers, dots or underscores."
    if username.lower() in RESERVED_USERNAMES:
        return "That username is not available."
    return None


def validate_password(password):
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if len(password.encode("utf-8")) > 72:  # batas bcrypt di Supabase Auth
        return "Password is too long (maximum 72 characters)."
    return None


def safe_next(target):
    """Cegah open redirect: hanya izinkan path internal."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("main.home")


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not g.user:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return f(*args, **kwargs)

    return wrapper


def admin_required(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if g.user["role"] != "admin":
            abort(403)
        return f(*args, **kwargs)

    return wrapper
