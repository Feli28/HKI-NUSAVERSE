from flask import Flask, g, render_template, request, session
from flask_wtf.csrf import CSRFError
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .extensions import csrf, limiter
from .services import profiles


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    if app.config["BEHIND_PROXY"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    csrf.init_app(app)
    limiter.init_app(app)

    from .blueprints.auth import bp as auth_bp
    from .blueprints.main import bp as main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    # Tambahkan blueprint lain (mis. prediction) di sini:
    # from .blueprints.prediction import bp as prediction_bp
    # app.register_blueprint(prediction_bp)

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
        return render_template("error.html", code=code, title=title, text=text), code

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

    return app
