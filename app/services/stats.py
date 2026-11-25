"""Statistik AGREGAT untuk admin. Tidak ada data per-pengguna di sini."""
from datetime import datetime, timedelta, timezone

from ..supabase_client import admin_client


def _count(table, **eq):
    qb = admin_client().table(table).select("id", count="exact")
    for key, value in eq.items():
        qb = qb.eq(key, value)
    return qb.limit(1).execute().count or 0


def overview():
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    last_24h = (admin_client().table("predictions").select("id", count="exact")
                .gte("created_at", since).limit(1).execute().count or 0)
    return {
        "users": _count("profiles"),
        "active_users": _count("profiles", is_active=True),
        "admins": _count("profiles", role="admin"),
        "predictions": _count("predictions"),
        "errors": _count("predictions", status="error"),
        "last_24h": last_24h,
        "feedback": _count("feedback"),
    }


def _view(name, order, desc=True, limit=None):
    qb = admin_client().table(name).select("*").order(order, desc=desc)
    if limit:
        qb = qb.limit(limit)
    return qb.execute().data


def daily(days=14):
    return _view("stats_daily", "day", True, days)


def by_source():
    return _view("stats_by_source", "total")


def by_feature_method():
    return _view("stats_by_feature_method", "total")


def by_label():
    return _view("stats_by_label", "total")


def by_model():
    return _view("stats_by_model", "total")


def feedback_by_model():
    return _view("stats_feedback_by_model", "total")
