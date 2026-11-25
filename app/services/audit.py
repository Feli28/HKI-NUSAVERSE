"""Audit log: siapa melakukan apa, kapan. Tidak boleh membuat request utama gagal."""
from flask import current_app, request

from ..supabase_client import admin_client


def log(action, actor=None, target=None, details=None, actor_username=None):
    try:
        admin_client().table("audit_log").insert({
            "action": action,
            "actor_id": actor["id"] if actor else None,
            "actor_username": actor["username"] if actor else actor_username,
            "target_user_id": target["id"] if target else None,
            "target_username": target["username"] if target else None,
            "ip": request.remote_addr if request else None,
            "details": details,
        }).execute()
    except Exception:
        current_app.logger.exception("audit log failed")


def list_entries(page=1, per_page=30):
    start = (page - 1) * per_page
    res = (admin_client().table("audit_log").select("*", count="exact")
           .order("created_at", desc=True).range(start, start + per_page - 1).execute())
    return res.data, (res.count or 0)
