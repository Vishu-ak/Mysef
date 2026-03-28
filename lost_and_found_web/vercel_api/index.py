"""Vercel serverless entrypoint for the Flask app."""

from __future__ import annotations

import os
from pathlib import Path

from lost_and_found_web.app import create_app


base_dir = Path(__file__).resolve().parent.parent
db_path = os.environ.get("DB_PATH", str(base_dir / "data" / "lost_and_found.db"))
app = create_app(db_path=db_path)

