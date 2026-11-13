"""Flask application factory."""
from __future__ import annotations

import logging

from flask import Flask
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Settings, get_settings
from .db import Database


def create_app(settings: Settings | None = None, db: Database | None = None) -> Flask:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = settings or get_settings()
    db = db or Database(settings.database_url)
    db.create_all()  # tables appear automatically on first start

    app = Flask(__name__)
    # Render sits behind a proxy; this makes generated links use https and the real host.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    app.json.sort_keys = False
    app.config.update(SETTINGS=settings, DB=db)
    CORS(app, origins=settings.cors_origins)

    from .routes import bp
    app.register_blueprint(bp)
    return app
