from flask import current_app
from supabase import create_client

try:  # nama modul berbeda antar versi supabase-py
    from supabase import AuthApiError
except ImportError:  # pragma: no cover
    from gotrue.errors import AuthApiError

__all__ = ["AuthApiError", "public_client", "admin_client"]


def public_client():
    """Client baru (publishable key) untuk setiap operasi auth.

    Jangan dipakai ulang: sign_in / verify_otp menyimpan sesi pengguna di dalam client,
    dan itu tidak boleh bocor ke request pengguna lain.
    """
    cfg = current_app.config
    return create_client(cfg["SUPABASE_URL"], cfg["SUPABASE_PUBLISHABLE_KEY"])


_admin = None


def admin_client():
    """Client server (secret key, melewati RLS). Hanya untuk query tabel dan auth.admin.*.
    Jangan pernah memanggil sign_in / verify_otp di client ini."""
    global _admin
    if _admin is None:
        cfg = current_app.config
        _admin = create_client(cfg["SUPABASE_URL"], cfg["SUPABASE_SECRET_KEY"])
    return _admin
