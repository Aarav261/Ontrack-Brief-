"""OnTracker web app — token-paste setup + scheduled email briefs."""

from __future__ import annotations

import logging
import os
import secrets

from flask import Flask
from flask_cors import CORS

from core.jobs import startup
from extensions import limiter
from routes.main import main_bp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

    CORS(app, resources={r"/*": {"origins": "*"}})

    # Initialize extensions
    limiter.init_app(app)

    # Register blueprints
    app.register_blueprint(main_bp)

    # Startup logic (DB init, restore schedules, start scheduler)
    startup()

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, host="0.0.0.0", port=port)
