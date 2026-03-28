"""WSGI entrypoint for production hosts."""

from __future__ import annotations

import os

from .app import create_app


DB_PATH = os.environ.get("LOST_FOUND_DB_PATH")
application = create_app(db_path=DB_PATH)

