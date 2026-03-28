"""Flask entrypoint for the lost-and-found map web app."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from .db import (
    create_item,
    get_all_items,
    get_item,
    get_matches_for_item,
    init_db,
    item_to_dict,
)


def create_app(db_path: str | None = None) -> Flask:
    """Application factory."""
    app = Flask(__name__)
    default_db = Path(__file__).resolve().parent / "data" / "lost_and_found.db"
    app.config["DB_PATH"] = db_path or str(default_db)

    init_db(app.config["DB_PATH"])

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/items")
    def list_items() -> Any:
        item_type = request.args.get("type")
        category = request.args.get("category")
        query = request.args.get("q")
        lat_raw = request.args.get("lat")
        lon_raw = request.args.get("lon")
        radius_km_raw = request.args.get("radius_km")

        location_filter = None
        if lat_raw and lon_raw:
            try:
                lat = float(lat_raw)
                lon = float(lon_raw)
                radius_km = float(radius_km_raw) if radius_km_raw else 10.0
                location_filter = {"lat": lat, "lon": lon, "radius_km": radius_km}
            except ValueError:
                return jsonify({"error": "lat, lon, and radius_km must be numeric"}), 400

        items = get_all_items(
            app.config["DB_PATH"],
            item_type=item_type,
            category=category,
            query=query,
            location_filter=location_filter,
        )
        return jsonify({"items": [item_to_dict(item) for item in items]})

    @app.post("/api/items")
    def add_item() -> Any:
        payload = request.get_json(silent=True) or {}
        required = ["item_type", "title", "category", "description", "contact_name", "contact_phone", "lat", "lon"]
        missing = [key for key in required if key not in payload or payload[key] in (None, "")]
        if missing:
            return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

        item_type = str(payload["item_type"]).strip().lower()
        if item_type not in {"lost", "found"}:
            return jsonify({"error": "item_type must be either 'lost' or 'found'"}), 400

        try:
            created_id = create_item(
                app.config["DB_PATH"],
                item_type=item_type,
                title=str(payload["title"]).strip(),
                category=str(payload["category"]).strip().lower(),
                description=str(payload["description"]).strip(),
                contact_name=str(payload["contact_name"]).strip(),
                contact_phone=str(payload["contact_phone"]).strip(),
                lat=float(payload["lat"]),
                lon=float(payload["lon"]),
                location_label=str(payload.get("location_label", "")).strip(),
                reward_note=str(payload.get("reward_note", "")).strip(),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except sqlite3.IntegrityError:
            return jsonify({"error": "Invalid payload for item creation"}), 400

        new_item = get_item(app.config["DB_PATH"], created_id)
        return jsonify({"item": item_to_dict(new_item)}), 201

    @app.get("/api/items/<int:item_id>/matches")
    def get_matches(item_id: int) -> Any:
        distance_limit_raw = request.args.get("distance_km")
        time_limit_raw = request.args.get("time_days")

        try:
            distance_limit_km = float(distance_limit_raw) if distance_limit_raw else 8.0
            time_limit_days = int(time_limit_raw) if time_limit_raw else 14
        except ValueError:
            return jsonify({"error": "distance_km and time_days must be numeric"}), 400

        item = get_item(app.config["DB_PATH"], item_id)
        if not item:
            return jsonify({"error": "Item not found"}), 404

        matches = get_matches_for_item(
            app.config["DB_PATH"],
            item_id=item_id,
            distance_limit_km=distance_limit_km,
            time_limit_days=time_limit_days,
        )
        return jsonify(
            {
                "item": item_to_dict(item),
                "matches": [item_to_dict(match) for match in matches],
            }
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
