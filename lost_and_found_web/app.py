"""Flask entrypoint for the lost-and-found map web app."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from .db import (
    create_user,
    create_item,
    get_user_by_email,
    get_user_by_session_token,
    get_all_items,
    get_item,
    get_matches_for_item,
    init_db,
    item_to_dict,
    set_user_session_token,
)


ALLOWED_UPLOAD_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_UPLOAD_EXTENSIONS


def _public_upload_url(filename: str) -> str:
    return f"/uploads/{filename}"


def _extract_auth_token() -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return request.cookies.get("session_token")


def create_app(db_path: str | None = None) -> Flask:
    """Application factory."""
    app = Flask(__name__, template_folder="templates", static_folder="static")
    default_db = Path(__file__).resolve().parent / "data" / "lost_and_found.db"
    app.config["DB_PATH"] = db_path or str(default_db)
    app.config["SECRET_KEY"] = "change-this-for-production"
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
    app.config["UPLOAD_FOLDER"] = str(Path(__file__).resolve().parent / "uploads")
    app.config["PUBLIC_BASE_URL"] = (
        Path(".").resolve().as_uri()
        if False
        else ""  # placeholder to keep type checker happy; overwritten below
    )

    from os import getenv

    app.config["PUBLIC_BASE_URL"] = getenv("PUBLIC_BASE_URL", "").strip()

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    init_db(app.config["DB_PATH"])

    def _current_user() -> dict[str, Any] | None:
        token = _extract_auth_token()
        if not token:
            return None
        user = get_user_by_session_token(app.config["DB_PATH"], token)
        if not user:
            return None
        return {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
        }

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/uploads/<path:filename>")
    def uploads(filename: str) -> Any:
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    @app.post("/api/auth/register")
    def register() -> Any:
        payload = request.get_json(silent=True) or {}
        name = str(payload.get("name", "")).strip()
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", ""))

        if not name or not email or not password:
            return jsonify({"error": "name, email, and password are required"}), 400
        if len(password) < 8:
            return jsonify({"error": "password must be at least 8 characters"}), 400
        if get_user_by_email(app.config["DB_PATH"], email):
            return jsonify({"error": "email is already registered"}), 409

        password_hash = generate_password_hash(password)
        user_id = create_user(app.config["DB_PATH"], name=name, email=email, password_hash=password_hash)
        token = uuid.uuid4().hex
        set_user_session_token(app.config["DB_PATH"], user_id=user_id, session_token=token)
        response = jsonify({"user": {"id": user_id, "name": name, "email": email}, "session_token": token})
        response.set_cookie("session_token", token, httponly=True, samesite="Lax")
        return response, 201

    @app.post("/api/auth/login")
    def login() -> Any:
        payload = request.get_json(silent=True) or {}
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", ""))
        user = get_user_by_email(app.config["DB_PATH"], email)
        if not user:
            return jsonify({"error": "invalid credentials"}), 401
        if not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "invalid credentials"}), 401

        token = uuid.uuid4().hex
        set_user_session_token(app.config["DB_PATH"], user_id=int(user["id"]), session_token=token)
        response = jsonify(
            {
                "user": {"id": user["id"], "name": user["name"], "email": user["email"]},
                "session_token": token,
            }
        )
        response.set_cookie("session_token", token, httponly=True, samesite="Lax")
        return response

    @app.post("/api/auth/logout")
    def logout() -> Any:
        user = _current_user()
        if user:
            set_user_session_token(app.config["DB_PATH"], user_id=int(user["id"]), session_token=None)
        response = jsonify({"ok": True})
        response.delete_cookie("session_token")
        return response

    @app.get("/api/auth/me")
    def me() -> Any:
        user = _current_user()
        return jsonify({"user": user})

    @app.post("/api/uploads")
    def upload_image() -> Any:
        user = _current_user()
        if not user:
            return jsonify({"error": "login required"}), 401
        if "image" not in request.files:
            return jsonify({"error": "image file is required"}), 400

        file = request.files["image"]
        if not file.filename:
            return jsonify({"error": "filename is required"}), 400
        if not _allowed_file(file.filename):
            return jsonify({"error": "unsupported file type"}), 400

        original = secure_filename(file.filename)
        extension = original.rsplit(".", 1)[1].lower()
        generated_name = f"{uuid.uuid4().hex}.{extension}"
        target_path = Path(app.config["UPLOAD_FOLDER"]) / generated_name
        file.save(target_path)
        return jsonify({"image_url": _public_upload_url(generated_name)})

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
        user = _current_user()
        if not user:
            return jsonify({"error": "login required"}), 401

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
                image_filename=str(payload.get("image_filename", "")).strip(),
                user_id=int(user["id"]),
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
