"""Flask entrypoint for the lost-and-found map web app."""

from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, url_for
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash

from .db import (
    create_item,
    create_user,
    get_all_items,
    get_item,
    get_matches_for_item,
    get_user_by_email,
    get_user_by_oauth_sub,
    get_user_by_session_token,
    init_db,
    link_user_oauth,
    item_to_dict,
    set_user_session_token,
)
from .storage import build_storage_backend

load_dotenv(Path(__file__).resolve().parent / ".env")

try:
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2 import id_token as google_id_token
except Exception:  # pragma: no cover - optional dependency in certain environments
    GoogleAuthRequest = None
    google_id_token = None


def _extract_auth_token() -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return request.cookies.get("session_token")


def _resolve_base_url() -> str:
    explicit = os.getenv("BACKEND_PUBLIC_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    return ""


def create_app(db_path: str | None = None) -> Flask:
    """Application factory."""
    app = Flask(__name__, template_folder="templates", static_folder="static")
    default_db = Path(__file__).resolve().parent / "data" / "lost_and_found.db"

    app.config["DB_PATH"] = db_path or os.getenv("DATABASE_PATH", str(default_db))
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-in-production")
    app.config["MAX_CONTENT_LENGTH"] = int(float(os.getenv("MAX_UPLOAD_MB", "8")) * 1024 * 1024)
    app.config["UPLOAD_FOLDER"] = os.getenv(
        "UPLOAD_FOLDER",
        str(Path(__file__).resolve().parent / "uploads"),
    )
    app.config["BACKEND_PUBLIC_URL"] = _resolve_base_url()
    app.config["GOOGLE_CLIENT_ID"] = os.getenv("GOOGLE_CLIENT_ID", "").strip()

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    init_db(app.config["DB_PATH"])
    storage_backend = build_storage_backend()

    def _current_user() -> dict[str, Any] | None:
        token = _extract_auth_token()
        if not token:
            return None
        user = get_user_by_session_token(app.config["DB_PATH"], token)
        if not user:
            return None
        return {"id": user["id"], "name": user["name"], "email": user["email"]}

    def _auth_success_response(user_id: int, name: str, email: str) -> Any:
        session_token = uuid.uuid4().hex
        set_user_session_token(
            app.config["DB_PATH"],
            user_id=user_id,
            session_token=session_token,
        )
        response = jsonify(
            {
                "user": {"id": user_id, "name": name, "email": email},
                "session_token": session_token,
            }
        )
        response.set_cookie("session_token", session_token, httponly=True, samesite="Lax")
        return response

    def _verify_google_token(token: str) -> dict[str, Any]:
        if not google_id_token or not GoogleAuthRequest:
            raise ValueError("Google OAuth dependencies are not installed")
        client_id = app.config["GOOGLE_CLIENT_ID"]
        if not client_id:
            raise ValueError("GOOGLE_CLIENT_ID is not configured")
        id_info = google_id_token.verify_oauth2_token(
            token,
            GoogleAuthRequest(),
            client_id,
        )
        if not id_info.get("email"):
            raise ValueError("Google account email is unavailable")
        if not id_info.get("email_verified", False):
            raise ValueError("Google account email is not verified")
        return id_info

    @app.get("/")
    def index() -> str:
        return render_template(
            "index.html",
            google_client_id=app.config["GOOGLE_CLIENT_ID"],
            backend_public_url=app.config["BACKEND_PUBLIC_URL"],
            storage_backend=storage_backend.kind,
        )

    @app.get("/uploads/<path:filename>")
    def uploads(filename: str) -> Any:
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    @app.get("/api/config")
    def config() -> Any:
        return jsonify(
            {
                "google_client_id": app.config["GOOGLE_CLIENT_ID"],
                "backend_public_url": app.config["BACKEND_PUBLIC_URL"],
                "storage_backend": storage_backend.kind,
            }
        )

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

        user_id = create_user(
            app.config["DB_PATH"],
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
        )
        return _auth_success_response(user_id, name, email), 201

    @app.post("/api/auth/login")
    def login() -> Any:
        payload = request.get_json(silent=True) or {}
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", ""))
        user = get_user_by_email(app.config["DB_PATH"], email)
        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "invalid credentials"}), 401
        return _auth_success_response(int(user["id"]), str(user["name"]), str(user["email"]))

    @app.post("/api/auth/google")
    def google_login() -> Any:
        payload = request.get_json(silent=True) or {}
        credential = str(payload.get("credential", "")).strip()
        if not credential:
            return jsonify({"error": "credential is required"}), 400

        try:
            claims = _verify_google_token(credential)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        email = str(claims["email"]).strip().lower()
        name = str(claims.get("name") or email.split("@")[0]).strip()
        oauth_sub = str(claims.get("sub", "")).strip()
        if not oauth_sub:
            return jsonify({"error": "Google subject ID missing"}), 400

        user = get_user_by_oauth_sub(
            app.config["DB_PATH"],
            auth_provider="google",
            oauth_sub=oauth_sub,
        )
        if not user:
            user = get_user_by_email(app.config["DB_PATH"], email)
        if not user:
            synthetic_password_hash = generate_password_hash(uuid.uuid4().hex)
            user_id = create_user(
                app.config["DB_PATH"],
                name=name,
                email=email,
                password_hash=synthetic_password_hash,
                auth_provider="google",
                oauth_sub=oauth_sub,
            )
        else:
            user_id = int(user["id"])
            name = str(user["name"])
            if str(user.get("auth_provider", "local")) != "google" or not str(user.get("oauth_sub", "")).strip():
                link_user_oauth(
                    app.config["DB_PATH"],
                    user_id=user_id,
                    auth_provider="google",
                    oauth_sub=oauth_sub,
                )

        return _auth_success_response(user_id, name, email)

    @app.get("/api/auth/google/start")
    def google_start() -> Any:
        client_id = app.config["GOOGLE_CLIENT_ID"]
        if not client_id:
            return jsonify({"error": "GOOGLE_CLIENT_ID is not configured"}), 400
        redirect_uri = url_for("index", _external=True)
        google_url = (
            "https://accounts.google.com/o/oauth2/v2/auth"
            f"?response_type=token&client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            "&scope=openid%20email%20profile"
            "&include_granted_scopes=true"
            "&prompt=select_account"
        )
        return redirect(google_url)

    @app.post("/api/auth/logout")
    def logout() -> Any:
        user = _current_user()
        if user:
            set_user_session_token(
                app.config["DB_PATH"],
                user_id=int(user["id"]),
                session_token=None,
            )
        response = jsonify({"ok": True})
        response.delete_cookie("session_token")
        return response

    @app.get("/api/auth/me")
    def me() -> Any:
        return jsonify({"user": _current_user()})

    @app.post("/api/uploads")
    def upload_image() -> Any:
        user = _current_user()
        if not user:
            return jsonify({"error": "login required"}), 401
        if "image" not in request.files:
            return jsonify({"error": "image file is required"}), 400

        try:
            uploaded = storage_backend.upload(
                request.files["image"],
                public_base_url=app.config["BACKEND_PUBLIC_URL"],
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 500

        return jsonify(
            {
                "image_url": uploaded["image_url"],
                "image_filename": uploaded.get("image_filename", ""),
            }
        )

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
        required = [
            "item_type",
            "title",
            "category",
            "description",
            "contact_name",
            "contact_phone",
            "lat",
            "lon",
        ]
        missing = [key for key in required if key not in payload or payload[key] in (None, "")]
        if missing:
            return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

        item_type = str(payload["item_type"]).strip().lower()
        if item_type not in {"lost", "found"}:
            return jsonify({"error": "item_type must be either 'lost' or 'found'"}), 400

        image_url = str(payload.get("image_url", "")).strip()
        image_filename = str(payload.get("image_filename", "")).strip()
        if image_url and not image_filename and "/uploads/" in image_url:
            image_filename = image_url.rsplit("/", 1)[-1]

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
                image_filename=image_filename,
                image_url=image_url,
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
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
