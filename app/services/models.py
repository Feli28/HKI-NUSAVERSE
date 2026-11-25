"""Registri model klasifikasi. Admin menentukan model aktif."""
import time

from postgrest.exceptions import APIError

from ..supabase_client import admin_client

_cache = {"model": None, "at": 0.0}
_TTL = 30  # detik; versi aktif dibaca sering (setiap prediksi dicatat)


def list_models():
    return admin_client().table("models").select("*").order("created_at", desc=True).execute().data


def get_active_model():
    """Model aktif saat ini (dict) atau None. Dipakai kode inferensi: model['version']."""
    now = time.time()
    if _cache["model"] is not None and now - _cache["at"] < _TTL:
        return _cache["model"]
    res = admin_client().table("models").select("*").eq("is_active", True).limit(1).execute()
    _cache["model"] = res.data[0] if res.data else None
    _cache["at"] = now
    return _cache["model"]


def invalidate():
    _cache["model"] = None
    _cache["at"] = 0.0


def set_active_model(model_id):
    admin_client().rpc("set_active_model", {"p_id": model_id}).execute()
    invalidate()


def add_model(name, version, description):
    """Mengembalikan baris baru, atau None bila versi sudah ada."""
    try:
        res = admin_client().table("models").insert(
            {"name": name, "version": version, "description": description or None}).execute()
    except APIError as err:
        if "23505" in str(err) or "duplicate" in str(err).lower():
            return None
        raise
    return res.data[0]
