"""Akses tabel public.profiles dan operasi admin Supabase Auth."""
from datetime import datetime, timezone

from flask import current_app

from ..supabase_client import admin_client


def get_profile(user_id):
    try:
        res = admin_client().table("profiles").select("*").eq("id", user_id).limit(1).execute()
    except Exception:
        current_app.logger.exception("get_profile failed")
        return None
    return res.data[0] if res.data else None


def username_available(username):
    res = admin_client().rpc("username_available", {"p_username": username}).execute()
    return bool(res.data)


def touch_login(user_id):
    admin_client().table("profiles").update(
        {"last_login_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", user_id).execute()


def bump_session_version(user_id):
    """Matikan semua sesi lama milik user (dipanggil setelah password diganti)."""
    profile = get_profile(user_id)
    if profile:
        admin_client().table("profiles").update(
            {"session_version": profile["session_version"] + 1}
        ).eq("id", user_id).execute()


def set_password(user_id, new_password):
    admin_client().auth.admin.update_user_by_id(user_id, {"password": new_password})


def discard_unconfirmed(user_id, username):
    """Hapus akun yang BELUM terverifikasi bila pemiliknya memilih 'Back to Sign Up'
    (mis. salah ketik email), supaya username-nya tidak 'terkunci'.
    Hanya menghapus bila akun belum terverifikasi dan username-nya cocok dengan sesi ini."""
    try:
        user = admin_client().auth.admin.get_user_by_id(user_id).user
        if user is None or getattr(user, "email_confirmed_at", None):
            return
        profile = get_profile(user_id)
        if not profile or profile["username"].lower() != (username or "").lower():
            return
        admin_client().auth.admin.delete_user(user_id)
    except Exception:
        current_app.logger.exception("discard_unconfirmed failed")
