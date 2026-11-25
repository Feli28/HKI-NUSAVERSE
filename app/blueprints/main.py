from flask import Blueprint, current_app, jsonify, render_template, url_for

from ..security import login_required
from ..services import models

bp = Blueprint("main", __name__)


@bp.get("/")
@login_required
def home():
    try:
        model = models.get_active_model()
    except Exception:
        current_app.logger.exception("could not load active model")
        model = None
    return render_template("home.html", model=model)


@bp.get("/manifest.webmanifest")
def manifest():
    """Web App Manifest: membuat NusaVerse bisa di-'Add to Home Screen' dan tampil layar penuh di HP."""
    data = {
        "name": "NusaVerse",
        "short_name": "NusaVerse",
        "start_url": url_for("main.home"),
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#FFF8EF",
        "theme_color": "#FFF8EF",
        "icons": [
            {"src": url_for("static", filename="img/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": url_for("static", filename="img/icon-512.png"), "sizes": "512x512", "type": "image/png"},
        ],
    }
    resp = jsonify(data)
    resp.mimetype = "application/manifest+json"
    return resp
