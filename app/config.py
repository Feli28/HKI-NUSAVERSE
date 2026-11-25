import os
from datetime import timedelta
from pathlib import Path

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

    # Label etnis = model.classes_ (dipakai untuk pilihan koreksi & pilih manual).
    LABELS = ["Ambon", "Batak", "Chinese", "Javanese", "Kalimantan", "Papuan", "Toraja"]

    # Model deteksi
    PROJECT_DIR = Path(__file__).resolve().parents[1]
    ANTRO_MODEL_PATH = os.environ.get("ANTRO_MODEL_PATH") or str(PROJECT_DIR / "models" / "antro_own_1738_svm.pkl")
    PRELOAD_MODEL = os.environ.get("PRELOAD_MODEL", "1") == "1"   # muat model saat server menyala
    MAX_UPLOAD_MB = 5
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024                          # batas keras request (sedikit di atas 5 MB)
    MAX_SIDE_PHOTO = 1280                                         # sisi terpanjang untuk upload / foto
    MAX_SIDE_LIVE = 640                                           # sisi terpanjang untuk frame live

    SOURCES = ("upload", "photo", "live")
    HISTORY_PAGE_SIZE = 15
    USERS_PAGE_SIZE = 15
    AUDIT_PAGE_SIZE = 30
    LIVE_LOG_INTERVAL_SECONDS = 30     # live webcam hanya dicatat sekali per 30 detik per pengguna
