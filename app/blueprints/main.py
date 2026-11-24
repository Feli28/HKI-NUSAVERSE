from flask import Blueprint, jsonify, render_template, url_for

from ..security import login_required

bp = Blueprint("main", __name__)


@bp.get("/")
@login_required
def home():
    return render_template("home.html")


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
