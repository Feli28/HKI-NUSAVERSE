import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def _required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing environment variable: {name} (see .env.example)")
    return value


class Config:
    SECRET_KEY = _required("SECRET_KEY")
    SUPABASE_URL = _required("SUPABASE_URL").rstrip("/")
    SUPABASE_PUBLISHABLE_KEY = _required("SUPABASE_PUBLISHABLE_KEY")
    SUPABASE_SECRET_KEY = _required("SUPABASE_SECRET_KEY")

    BEHIND_PROXY = os.environ.get("BEHIND_PROXY") == "1"

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV") == "production"
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # Harus sama dengan "Email OTP Expiration" di Supabase (1800 detik = 30 menit).
    VERIFY_LINK_MINUTES = 30
    RESEND_COOLDOWN_SECONDS = 60       # Supabase juga membatasi 60 dtk per user
    RESET_SESSION_SECONDS = 15 * 60    # waktu untuk mengisi form password baru setelah klik link
