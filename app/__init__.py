from datetime import datetime, timedelta, timezone

from flask import Flask, g, jsonify, render_template, request, session
from flask_wtf.csrf import CSRFError
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .extensions import csrf, limiter
from .services import profiles

try:
    from zoneinfo import ZoneInfo
    WIB = ZoneInfo("Asia/Jakarta")
except Exception:  # tzdata tidak terpasang (mis. Windows tanpa paket tzdata)
    WIB = timezone(timedelta(hours=7))


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    if app.config["BEHIND_PROXY"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    csrf.init_app(app)
    limiter.init_app(app)

    from .blueprints.account import bp as account_bp
    from .blueprints.admin import bp as admin_bp
    from .blueprints.auth import bp as auth_bp
    from .blueprints.detect import bp as detect_bp
    from .blueprints.history import bp as history_bp
    from .blueprints.main import bp as main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(detect_bp)
    app.register_blueprint(admin_bp)
    @app.before_request
    def load_user():
        g.user = None
        if request.endpoint in (None, "static"):
            return
        uid = session.get("uid")
        if not uid:
            return
        profile = profiles.get_profile(uid)
        # Sesi tidak berlaku bila akun dinonaktifkan atau password sudah direset.
        if profile and profile["is_active"] and session.get("sv") == profile["session_version"]:
            g.user = profile
        else:
            session.clear()

    def _parse(value):
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    @app.template_filter("dt")
    def fmt_datetime(value):
        """'2026-11-12T07:30:00+00:00' -> '12 Nov 2026, 14:30' (WIB)."""
        if not value:
            return "Never"
        try:
            return _parse(value).astimezone(WIB).strftime("%d %b %Y, %H:%M")
        except ValueError:
            return str(value)

    @app.template_filter("dshort")
    def fmt_day(value):
        """'2026-11-12' -> '12 Nov'."""
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%d %b")
        except ValueError:
            return str(value)

    @app.context_processor
    def inject_globals():
        return {"verify_minutes": app.config["VERIFY_LINK_MINUTES"]}

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # Kamera dibutuhkan fitur foto/live, jadi hanya diizinkan dari origin sendiri.
        resp.headers.setdefault("Permissions-Policy", "camera=(self), microphone=()")
        return resp

    def _error(code, title, text):
        if request.path.startswith("/api/"):          # API selalu membalas JSON
            return jsonify(status="error", message=text), code
        return render_template("error.html", code=code, title=title, text=text), code

    @app.errorhandler(413)
    def too_large(_):
        return _error(413, "Photo Too Large", "The photo is too large (maximum 5 MB).")

    @app.errorhandler(CSRFError)
    def csrf_failed(_):
        return _error(400, "Session Expired", "Your form session expired. Please go back and try again.")

    @app.errorhandler(403)
    def forbidden(_):
        return _error(403, "Access Denied", "You don't have access to this page.")

    @app.errorhandler(404)
    def not_found(_):
        return _error(404, "Page Not Found", "The page you're looking for doesn't exist.")

    @app.errorhandler(429)
    def too_many(_):
        return _error(429, "Too Many Requests", "Please slow down and try again in a moment.")

    if app.config["PRELOAD_MODEL"]:
        from .services import detector
        detector.start_preload(app)      # muat model di thread latar saat server menyala

    return app
