from flask import current_app
from supabase import create_client

try:
    from supabase import AuthApiError
except ImportError:
    from gotrue.errors import AuthApiError

__all__ = ["AuthApiError", "public_client", "admin_client"]


def public_client():
    """Client menggunakan publishable key untuk operasi Auth."""
    cfg = current_app.config

    return create_client(
        cfg["SUPABASE_URL"],
        cfg["SUPABASE_PUBLISHABLE_KEY"],
    )


_admin = None


def admin_client():
    """Client server menggunakan secret key untuk operasi admin."""
    global _admin

    if _admin is None:
        cfg = current_app.config
        _admin = create_client(
            cfg["SUPABASE_URL"],
            cfg["SUPABASE_SECRET_KEY"],
        )

    return _admin