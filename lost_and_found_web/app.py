"""Flask entrypoint for the lost-and-found map web app."""

from __future__ import annotations

import os
import secrets
import sqlite3
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, url_for
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash

from .db import (
    create_item,
    create_user,
    get_all_items,
    get_claim,
    get_claim_for_item_and_claimer,
    create_otp_code,
    get_active_otp_code,
    consume_otp_code,
    get_item,
    get_matches_for_item,
    get_item_watchers_for_match,
    get_user_by_id,
    get_user_by_email,
    get_user_by_oauth_sub,
    get_user_by_session_token,
    init_db,
    list_claims_for_item,
    list_claims_for_user,
    list_owned_items,
    list_user_watchers,
    link_user_oauth,
    item_to_dict,
    mark_watcher_notified,
    request_claim,
    resolve_claim,
    save_auth_otp,
    subscribe_watcher,
    set_user_session_token,
    update_item_status,
    verify_user_contact,
    verify_auth_otp,
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
    app.config["AUTH_OTP_REQUIRED"] = os.getenv("AUTH_OTP_REQUIRED", "true").strip().lower() in {"1", "true", "yes"}
    app.config["OTP_TTL_MINUTES"] = int(os.getenv("OTP_TTL_MINUTES", "10"))
    app.config["OTP_MAX_ATTEMPTS"] = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
    app.config["RATE_LIMIT_WINDOW_SECONDS"] = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    app.config["RATE_LIMIT_AUTH_REQUESTS"] = int(os.getenv("RATE_LIMIT_AUTH_REQUESTS", "20"))
    app.config["RATE_LIMIT_ITEM_POSTS"] = int(os.getenv("RATE_LIMIT_ITEM_POSTS", "12"))
    app.config["SMTP_HOST"] = os.getenv("SMTP_HOST", "").strip()
    app.config["SMTP_PORT"] = int(os.getenv("SMTP_PORT", "587"))
    app.config["SMTP_USER"] = os.getenv("SMTP_USER", "").strip()
    app.config["SMTP_PASSWORD"] = os.getenv("SMTP_PASSWORD", "").strip()
    app.config["SMTP_FROM_EMAIL"] = os.getenv("SMTP_FROM_EMAIL", "").strip() or app.config["SMTP_USER"]
    app.config["SMTP_USE_TLS"] = os.getenv("SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes"}
    app.config["EMAIL_NOTIFICATIONS_ENABLED"] = (
        os.getenv("EMAIL_NOTIFICATIONS_ENABLED", "true").strip().lower() in {"1", "true", "yes"}
    )

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    init_db(app.config["DB_PATH"])
    storage_backend = build_storage_backend()
    rate_buckets: dict[str, deque[float]] = defaultdict(deque)

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

    def _client_ip() -> str:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.remote_addr or "unknown"

    def _rate_limit_or_429(*, bucket: str, limit: int) -> Any | None:
        now = time.time()
        window = float(app.config["RATE_LIMIT_WINDOW_SECONDS"])
        queue = rate_buckets[bucket]
        while queue and now - queue[0] > window:
            queue.popleft()
        if len(queue) >= limit:
            return jsonify({"error": "Too many requests. Please try again later."}), 429
        queue.append(now)
        return None

    def _send_email(*, to_email: str, subject: str, body: str) -> None:
        if not app.config["EMAIL_NOTIFICATIONS_ENABLED"]:
            return
        host = app.config["SMTP_HOST"]
        from_email = app.config["SMTP_FROM_EMAIL"]
        if not host or not from_email:
            print(f"[Email disabled] To={to_email} Subject={subject} Body={body}")
            return
        msg = EmailMessage()
        msg["From"] = from_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        import smtplib

        with smtplib.SMTP(host, app.config["SMTP_PORT"]) as server:
            if app.config["SMTP_USE_TLS"]:
                server.starttls()
            if app.config["SMTP_USER"] and app.config["SMTP_PASSWORD"]:
                server.login(app.config["SMTP_USER"], app.config["SMTP_PASSWORD"])
            server.send_message(msg)

    def _otp_required_response(user_id: int, email: str) -> Any:
        otp_code = f"{secrets.randbelow(1_000_000):06d}"
        save_auth_otp(
            app.config["DB_PATH"],
            user_id=user_id,
            code=otp_code,
            ttl_minutes=app.config["OTP_TTL_MINUTES"],
            max_attempts=app.config["OTP_MAX_ATTEMPTS"],
        )
        _send_email(
            to_email=email,
            subject="Your Lost & Found login verification code",
            body=(
                f"Your OTP code is: {otp_code}\n\n"
                f"It expires in {app.config['OTP_TTL_MINUTES']} minutes.\n"
                "If you did not request this code, ignore this email."
            ),
        )
        response = jsonify(
            {
                "otp_required": True,
                "user_id": user_id,
                "message": "OTP sent to your email.",
            }
        )
        response.delete_cookie("session_token")
        return response

    def _score_match(base_item: dict[str, Any], candidate: dict[str, Any]) -> float:
        distance = float(candidate.get("distance_km", 9999.0))
        distance_score = max(0.0, 1.0 - min(distance, 20.0) / 20.0)
        base_text = f"{base_item.get('title', '')} {base_item.get('description', '')}".lower()
        cand_text = f"{candidate.get('title', '')} {candidate.get('description', '')}".lower()
        base_tokens = {tok for tok in base_text.replace(",", " ").split() if len(tok) >= 3}
        cand_tokens = {tok for tok in cand_text.replace(",", " ").split() if len(tok) >= 3}
        overlap = len(base_tokens & cand_tokens)
        text_score = min(1.0, overlap / 4.0)
        return round((0.65 * distance_score + 0.35 * text_score) * 100.0, 2)

    def _notify_watchers_for_new_item(new_item: dict[str, Any]) -> None:
        watchers = get_item_watchers_for_match(
            app.config["DB_PATH"],
            int(new_item["id"]),
        )
        for watcher in watchers:
            watcher_email = str(watcher.get("watcher_email", "")).strip()
            if not watcher_email:
                continue
            _send_email(
                to_email=watcher_email,
                subject=f"Potential match found: {new_item['title']}",
                body=(
                    "A potential item match was found near your watch location.\n\n"
                    f"New report: {new_item['title']} ({new_item['item_type']})\n"
                    f"Category: {new_item['category']}\n"
                    f"Distance: {watcher.get('distance_km', 'n/a')} km\n"
                    f"Contact: {new_item['contact_name']} ({new_item['contact_phone']})\n"
                ),
            )
            mark_watcher_notified(
                app.config["DB_PATH"],
                watcher_id=int(watcher["watcher_id"]),
                matched_item_id=int(new_item["id"]),
            )

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
        limited = _rate_limit_or_429(
            bucket=f"auth-register:{_client_ip()}",
            limit=app.config["RATE_LIMIT_AUTH_REQUESTS"],
        )
        if limited:
            return limited
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
        if app.config["AUTH_OTP_REQUIRED"]:
            return _otp_required_response(user_id, email), 201
        return _auth_success_response(user_id, name, email), 201

    @app.post("/api/auth/login")
    def login() -> Any:
        limited = _rate_limit_or_429(
            bucket=f"auth-login:{_client_ip()}",
            limit=app.config["RATE_LIMIT_AUTH_REQUESTS"],
        )
        if limited:
            return limited
        payload = request.get_json(silent=True) or {}
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", ""))
        user = get_user_by_email(app.config["DB_PATH"], email)
        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "invalid credentials"}), 401
        if app.config["AUTH_OTP_REQUIRED"]:
            return _otp_required_response(
                int(user["id"]),
                str(user["email"]),
            )
        return _auth_success_response(int(user["id"]), str(user["name"]), str(user["email"]))

    @app.post("/api/auth/google")
    def google_login() -> Any:
        limited = _rate_limit_or_429(
            bucket=f"auth-google:{_client_ip()}",
            limit=app.config["RATE_LIMIT_AUTH_REQUESTS"],
        )
        if limited:
            return limited
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

        if app.config["AUTH_OTP_REQUIRED"]:
            return _otp_required_response(user_id, email)
        return _auth_success_response(user_id, name, email)

    @app.post("/api/auth/verify-otp")
    def verify_otp() -> Any:
        limited = _rate_limit_or_429(
            bucket=f"auth-otp:{_client_ip()}",
            limit=app.config["RATE_LIMIT_AUTH_REQUESTS"],
        )
        if limited:
            return limited
        payload = request.get_json(silent=True) or {}
        user_id_raw = payload.get("user_id")
        code = str(payload.get("code", "")).strip()
        try:
            user_id = int(user_id_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "valid user_id is required"}), 400
        if not code:
            return jsonify({"error": "OTP code is required"}), 400
        ok, reason = verify_auth_otp(
            app.config["DB_PATH"],
            user_id=user_id,
            code=code,
        )
        if not ok:
            return jsonify({"error": reason}), 400
        user = get_user_by_id(app.config["DB_PATH"], user_id)
        if not user:
            return jsonify({"error": "user not found"}), 404
        verify_user_contact(
            app.config["DB_PATH"],
            user_id=user_id,
            channel="email",
            value=str(user.get("email", "")),
        )
        return _auth_success_response(
            user_id,
            str(user["name"]),
            str(user["email"]),
        )

    @app.post("/api/auth/email/request-otp")
    def request_email_otp() -> Any:
        user = _current_user()
        if not user:
            return jsonify({"error": "login required"}), 401
        limited = _rate_limit_or_429(
            bucket=f"auth-email-otp:{_client_ip()}:{int(user['id'])}",
            limit=app.config["RATE_LIMIT_AUTH_REQUESTS"],
        )
        if limited:
            return limited
        email = str(user["email"]).strip().lower()
        otp_code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = (
            datetime.utcnow() + timedelta(minutes=app.config["OTP_TTL_MINUTES"])
        ).strftime("%Y-%m-%d %H:%M:%S")
        create_otp_code(
            app.config["DB_PATH"],
            user_id=int(user["id"]),
            channel="email",
            destination=email,
            code=otp_code,
            expires_at=expires_at,
        )
        _send_email(
            to_email=email,
            subject="Your Lost & Found email verification code",
            body=(
                f"Your verification OTP is: {otp_code}\n\n"
                f"It expires in {app.config['OTP_TTL_MINUTES']} minutes."
            ),
        )
        response_payload: dict[str, Any] = {"message": "OTP sent to your email."}
        # convenient for local/dev smoke tests
        if os.getenv("ENV", "").strip().lower() != "production":
            response_payload["dev_otp"] = otp_code
        return jsonify(response_payload)

    @app.post("/api/auth/email/verify-otp")
    def verify_email_otp() -> Any:
        user = _current_user()
        if not user:
            return jsonify({"error": "login required"}), 401
        limited = _rate_limit_or_429(
            bucket=f"auth-email-verify:{_client_ip()}:{int(user['id'])}",
            limit=app.config["RATE_LIMIT_AUTH_REQUESTS"],
        )
        if limited:
            return limited
        payload = request.get_json(silent=True) or {}
        otp_code = str(payload.get("otp_code", "")).strip()
        if not otp_code:
            return jsonify({"error": "otp_code is required"}), 400
        active = get_active_otp_code(
            app.config["DB_PATH"],
            user_id=int(user["id"]),
            channel="email",
            destination=str(user["email"]).strip().lower(),
            code=otp_code,
        )
        if not active:
            return jsonify({"error": "invalid or expired OTP"}), 400
        consume_otp_code(app.config["DB_PATH"], otp_id=int(active["id"]))
        verify_user_contact(
            app.config["DB_PATH"],
            user_id=int(user["id"]),
            channel="email",
            value=str(user["email"]),
        )
        updated_user = get_user_by_id(app.config["DB_PATH"], int(user["id"]))
        return jsonify(
            {
                "message": "Email verified successfully.",
                "user": {
                    "id": updated_user["id"],
                    "name": updated_user["name"],
                    "email": updated_user["email"],
                    "email_verified": bool(updated_user.get("email_verified", 0)),
                },
            }
        )

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
        limited = _rate_limit_or_429(
            bucket=f"item-create:{_client_ip()}:{_extract_auth_token() or ''}",
            limit=app.config["RATE_LIMIT_ITEM_POSTS"],
        )
        if limited:
            return limited
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
        item_payload = item_to_dict(new_item)
        if item_payload:
            _notify_watchers_for_new_item(item_payload)
        return jsonify({"item": item_payload}), 201

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
        scored_matches = []
        for match in matches:
            serialized = item_to_dict(match)
            if not serialized:
                continue
            serialized["match_score"] = _score_match(item_to_dict(item) or {}, serialized)
            scored_matches.append(serialized)
        scored_matches.sort(key=lambda row: row.get("match_score", 0.0), reverse=True)
        return jsonify(
            {
                "item": item_to_dict(item),
                "matches": scored_matches,
            }
        )

    @app.post("/api/watchers")
    def create_watcher() -> Any:
        user = _current_user()
        if not user:
            return jsonify({"error": "login required"}), 401
        payload = request.get_json(silent=True) or {}
        category = str(payload.get("category", "")).strip().lower()
        item_type = str(payload.get("item_type", "")).strip().lower()
        try:
            latitude = float(payload.get("lat"))
            longitude = float(payload.get("lon"))
            radius_km = float(payload.get("radius_km", 10))
        except (TypeError, ValueError):
            return jsonify({"error": "lat, lon, radius_km must be numeric"}), 400
        if item_type not in {"lost", "found"}:
            return jsonify({"error": "item_type must be 'lost' or 'found'"}), 400
        if not category:
            return jsonify({"error": "category is required"}), 400
        watcher_id = subscribe_watcher(
            app.config["DB_PATH"],
            user_id=int(user["id"]),
            item_type=item_type,
            category=category,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
        )
        return jsonify({"watcher_id": watcher_id}), 201

    @app.get("/api/watchers")
    def get_watchers() -> Any:
        user = _current_user()
        if not user:
            return jsonify({"error": "login required"}), 401
        watchers = list_user_watchers(app.config["DB_PATH"], user_id=int(user["id"]))
        return jsonify({"watchers": watchers})

    @app.get("/api/my-items")
    def get_my_items() -> Any:
        user = _current_user()
        if not user:
            return jsonify({"error": "login required"}), 401
        items = list_owned_items(app.config["DB_PATH"], owner_user_id=int(user["id"]))
        return jsonify({"items": [item_to_dict(row) for row in items]})

    @app.post("/api/items/<int:item_id>/status")
    def patch_item_status(item_id: int) -> Any:
        user = _current_user()
        if not user:
            return jsonify({"error": "login required"}), 401
        payload = request.get_json(silent=True) or {}
        status = str(payload.get("status", "")).strip().lower()
        if status not in {"open", "in_discussion", "claimed", "returned", "closed"}:
            return jsonify({"error": "invalid status"}), 400
        note = str(payload.get("note", "")).strip()
        updated = update_item_status(
            app.config["DB_PATH"],
            item_id=item_id,
            owner_user_id=int(user["id"]),
            status=status,
            note=note,
        )
        if not updated:
            return jsonify({"error": "item not found or not owned by user"}), 404
        return jsonify({"item": item_to_dict(updated)})

    @app.post("/api/items/<int:item_id>/claims")
    def create_claim(item_id: int) -> Any:
        user = _current_user()
        if not user:
            return jsonify({"error": "login required"}), 401
        limited = _rate_limit_or_429(
            bucket=f"claim-create:{_client_ip()}:{int(user['id'])}",
            limit=app.config["RATE_LIMIT_ITEM_POSTS"],
        )
        if limited:
            return limited
        payload = request.get_json(silent=True) or {}
        message = str(payload.get("message", "")).strip()
        proof_answer = str(payload.get("proof_answer", "")).strip()
        if not message or not proof_answer:
            return jsonify({"error": "message and proof_answer are required"}), 400
        existing = get_claim_for_item_and_claimer(
            app.config["DB_PATH"],
            item_id=item_id,
            claimant_user_id=int(user["id"]),
        )
        if existing:
            return jsonify({"error": "claim already exists for this item"}), 409
        claim_id = request_claim(
            app.config["DB_PATH"],
            item_id=item_id,
            claimer_user_id=int(user["id"]),
            message=message,
            proof_answer=proof_answer,
        )
        claim = get_claim(app.config["DB_PATH"], claim_id=claim_id)
        return jsonify({"claim": claim}), 201

    @app.get("/api/items/<int:item_id>/claims")
    def get_claims(item_id: int) -> Any:
        user = _current_user()
        if not user:
            return jsonify({"error": "login required"}), 401
        claims = list_claims_for_item(
            app.config["DB_PATH"],
            item_id=item_id,
            owner_user_id=int(user["id"]),
        )
        return jsonify({"claims": claims})

    @app.post("/api/claims")
    def create_claim_from_panel() -> Any:
        user = _current_user()
        if not user:
            return jsonify({"error": "login required"}), 401
        payload = request.get_json(silent=True) or {}
        try:
            item_id = int(payload.get("item_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "valid item_id is required"}), 400
        message = str(payload.get("request_message", "")).strip()
        if not message:
            return jsonify({"error": "request_message is required"}), 400
        existing = get_claim_for_item_and_claimer(
            app.config["DB_PATH"],
            item_id=item_id,
            claimant_user_id=int(user["id"]),
        )
        if existing:
            return jsonify({"error": "claim already exists for this item"}), 409
        claim_id = request_claim(
            app.config["DB_PATH"],
            item_id=item_id,
            claimer_user_id=int(user["id"]),
            message=message,
            proof_answer="submitted-via-panel",
        )
        return jsonify({"claim": get_claim(app.config["DB_PATH"], claim_id=claim_id)}), 201

    @app.get("/api/claims/mine")
    def get_my_claims() -> Any:
        user = _current_user()
        if not user:
            return jsonify({"error": "login required"}), 401
        claims = list_claims_for_user(app.config["DB_PATH"], claimer_user_id=int(user["id"]))
        return jsonify({"claims": claims})

    @app.post("/api/claims/<int:claim_id>/decision")
    def decision_claim(claim_id: int) -> Any:
        user = _current_user()
        if not user:
            return jsonify({"error": "login required"}), 401
        payload = request.get_json(silent=True) or {}
        approve = bool(payload.get("approve"))
        status = "approved" if approve else "rejected"
        updated = resolve_claim(
            app.config["DB_PATH"],
            claim_id=claim_id,
            owner_user_id=int(user["id"]),
            status=status,
            resolution_note="",
        )
        if not updated:
            return jsonify({"error": "claim not found or not authorized"}), 404
        return jsonify({"claim": updated})

    @app.patch("/api/claims/<int:claim_id>")
    def patch_claim(claim_id: int) -> Any:
        user = _current_user()
        if not user:
            return jsonify({"error": "login required"}), 401
        payload = request.get_json(silent=True) or {}
        status = str(payload.get("status", "")).strip().lower()
        if status not in {"approved", "rejected"}:
            return jsonify({"error": "status must be approved or rejected"}), 400
        resolution_note = str(payload.get("resolution_note", "")).strip()
        updated = resolve_claim(
            app.config["DB_PATH"],
            claim_id=claim_id,
            owner_user_id=int(user["id"]),
            status=status,
            resolution_note=resolution_note,
        )
        if not updated:
            return jsonify({"error": "claim not found or not authorized"}), 404
        return jsonify({"claim": updated})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
