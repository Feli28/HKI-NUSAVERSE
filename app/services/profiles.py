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
    """Matikan semua sesi lama milik user. Mengembalikan versi baru."""
    profile = get_profile(user_id)
    if not profile:
        return None
    new_version = profile["session_version"] + 1
    admin_client().table("profiles").update({"session_version": new_version}).eq("id", user_id).execute()
    return new_version


def set_password(user_id, new_password):
    admin_client().auth.admin.update_user_by_id(user_id, {"password": new_password})


def get_email(user_id):
    user = admin_client().auth.admin.get_user_by_id(user_id).user
    return getattr(user, "email", None) if user else None


# ---------------------------------------------------------------- manajemen akun (admin)
def list_profiles(q="", page=1, per_page=15):
    qb = admin_client().table("profiles").select(
        "id,username,role,is_active,created_at,last_login_at", count="exact")
    if q:
        qb = qb.ilike("username", f"%{q}%")   # q sudah dibersihkan ke [A-Za-z0-9_.]
    start = (page - 1) * per_page
    res = qb.order("created_at", desc=True).range(start, start + per_page - 1).execute()
    return res.data, (res.count or 0)


def set_active(user_id, active):
    admin_client().table("profiles").update({"is_active": active}).eq("id", user_id).execute()


def set_role(user_id, role):
    admin_client().table("profiles").update({"role": role}).eq("id", user_id).execute()


def find_by_username(username):
    """Cari persis (tidak peka huruf besar/kecil)."""
    res = admin_client().table("profiles").select("*").ilike("username", username).execute()
    for row in res.data or []:
        if row["username"].lower() == username.lower():
            return row
    return None


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
