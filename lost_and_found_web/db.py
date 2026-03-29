"""Database layer for the lost-and-found map web app."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .geo import haversine_km


DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "lost_and_found.db"
VALID_ITEM_STATUSES = {"open", "in_discussion", "claimed", "returned", "closed"}
VALID_CLAIM_STATUSES = {"pending", "approved", "rejected", "cancelled"}


def _dict_factory(cursor: sqlite3.Cursor, row: Iterable[Any]) -> Dict[str, Any]:
    return {column[0]: row[index] for index, column in enumerate(cursor.description)}


def _resolve_db_path(db_path: str | None = None) -> Path:
    return Path(db_path) if db_path else DEFAULT_DB_PATH


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Return a sqlite connection configured for dictionary rows."""
    path = _resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = _dict_factory
    return connection


def init_db(db_path: str | None = None) -> None:
    """Initialize database schema if it does not already exist."""
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                session_token TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                auth_provider TEXT NOT NULL DEFAULT 'local',
                oauth_sub TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        existing_user_columns = {
            row["name"]
            for row in cursor.execute("PRAGMA table_info(users)").fetchall()
        }
        if "session_token" not in existing_user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN session_token TEXT UNIQUE")
        if "auth_provider" not in existing_user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN auth_provider TEXT NOT NULL DEFAULT 'local'")
        if "oauth_sub" not in existing_user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN oauth_sub TEXT NOT NULL DEFAULT ''")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_type TEXT NOT NULL CHECK(item_type IN ('lost', 'found')),
                user_id INTEGER,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                contact_name TEXT NOT NULL,
                contact_phone TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                location_label TEXT NOT NULL DEFAULT '',
                reward_note TEXT NOT NULL DEFAULT '',
                image_filename TEXT NOT NULL DEFAULT '',
                image_url TEXT NOT NULL DEFAULT '',
                image_meta TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        existing_columns = {
            row["name"]
            for row in cursor.execute("PRAGMA table_info(items)").fetchall()
        }
        if "user_id" not in existing_columns:
            cursor.execute("ALTER TABLE items ADD COLUMN user_id INTEGER")
        if "image_filename" not in existing_columns:
            cursor.execute(
                "ALTER TABLE items ADD COLUMN image_filename TEXT NOT NULL DEFAULT ''"
            )
        if "image_url" not in existing_columns:
            cursor.execute(
                "ALTER TABLE items ADD COLUMN image_url TEXT NOT NULL DEFAULT ''"
            )
        if "image_meta" not in existing_columns:
            cursor.execute(
                "ALTER TABLE items ADD COLUMN image_meta TEXT NOT NULL DEFAULT ''"
            )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_items_type_category
            ON items(item_type, category);
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_items_created_at
            ON items(created_at DESC);
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_items_user_id
            ON items(user_id);
            """
        )
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
            ON users(email);
            """
        )
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_session_token
            ON users(session_token);
            """
        )
        connection.commit()


def _clean_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    return cleaned


def _normalize_item_type(item_type: str) -> str:
    normalized = item_type.strip().lower()
    if normalized not in {"lost", "found"}:
        raise ValueError("item_type must be either 'lost' or 'found'")
    return normalized


def _normalize_coords(lat: float, lon: float) -> tuple[float, float]:
    if not -90.0 <= lat <= 90.0:
        raise ValueError("Latitude must be between -90 and 90")
    if not -180.0 <= lon <= 180.0:
        raise ValueError("Longitude must be between -180 and 180")
    return lat, lon


def create_item(
    db_path: str | None,
    *,
    item_type: str,
    title: str,
    category: str,
    description: str,
    contact_name: str,
    contact_phone: str,
    lat: float,
    lon: float,
    location_label: str = "",
    reward_note: str = "",
    image_filename: str = "",
    image_url: str = "",
    image_meta: Dict[str, Any] | None = None,
    user_id: int | None = None,
) -> int:
    """Insert a new lost/found item and return its ID."""
    normalized_type = _normalize_item_type(item_type)
    normalized_title = _clean_text(title, "title")
    normalized_category = _clean_text(category, "category").lower()
    normalized_description = _clean_text(description, "description")
    normalized_contact_name = _clean_text(contact_name, "contact_name")
    normalized_contact_phone = _clean_text(contact_phone, "contact_phone")
    normalized_lat, normalized_lon = _normalize_coords(float(lat), float(lon))

    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO items (
                item_type, user_id, category, title, description, contact_name, contact_phone,
                latitude, longitude, location_label, reward_note, image_filename, image_url, image_meta
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_type,
                user_id,
                normalized_category,
                normalized_title,
                normalized_description,
                normalized_contact_name,
                normalized_contact_phone,
                normalized_lat,
                normalized_lon,
                location_label.strip(),
                reward_note.strip(),
                image_filename.strip(),
                image_url.strip(),
                json.dumps(image_meta or {}),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def get_item(db_path: str | None, item_id: int) -> Dict[str, Any] | None:
    """Fetch one item by ID."""
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT i.id, i.item_type, i.user_id, i.category, i.title, i.description,
                   i.contact_name, i.contact_phone, i.latitude, i.longitude, i.location_label,
                   i.reward_note, i.image_filename, i.image_url, i.image_meta, i.created_at, u.email AS owner_email
            FROM items i
            LEFT JOIN users u ON u.id = i.user_id
            WHERE i.id = ?
            """,
            (item_id,),
        ).fetchone()


def get_all_items(
    db_path: str | None,
    *,
    item_type: str | None = None,
    category: str | None = None,
    query: str | None = None,
    location_filter: Dict[str, float] | None = None,
) -> List[Dict[str, Any]]:
    """Return filtered items ordered by newest first."""
    sql = """
        SELECT i.id, i.item_type, i.user_id, i.category, i.title, i.description,
               i.contact_name, i.contact_phone, i.latitude, i.longitude, i.location_label,
               i.reward_note, i.image_filename, i.image_url, i.image_meta, i.created_at, u.email AS owner_email
        FROM items i
        LEFT JOIN users u ON u.id = i.user_id
        WHERE 1 = 1
    """
    params: List[Any] = []

    if item_type:
        sql += " AND item_type = ?"
        params.append(item_type.strip().lower())
    if category:
        sql += " AND category = ?"
        params.append(category.strip().lower())
    if query:
        sql += " AND (LOWER(title) LIKE ? OR LOWER(description) LIKE ?)"
        query_text = f"%{query.strip().lower()}%"
        params.extend([query_text, query_text])

    sql += " ORDER BY created_at DESC, id DESC"

    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        rows: List[Dict[str, Any]] = cursor.execute(sql, params).fetchall()

    if not location_filter:
        return rows

    center_lat = float(location_filter["lat"])
    center_lon = float(location_filter["lon"])
    radius_km = float(location_filter["radius_km"])

    filtered: List[Dict[str, Any]] = []
    for row in rows:
        distance_km = haversine_km(center_lat, center_lon, row["latitude"], row["longitude"])
        if distance_km <= radius_km:
            with_distance = dict(row)
            with_distance["distance_km"] = round(distance_km, 2)
            filtered.append(with_distance)
    return filtered


def get_matches_for_item(
    db_path: str | None,
    *,
    item_id: int,
    distance_limit_km: float = 8.0,
    time_limit_days: int = 14,
) -> List[Dict[str, Any]]:
    """Return possible matches by opposite type, same category, and nearby location."""
    base_item = get_item(db_path, item_id)
    if not base_item:
        return []

    opposite_type = "found" if base_item["item_type"] == "lost" else "lost"
    day_window = max(1, int(time_limit_days))
    distance_limit = max(0.1, float(distance_limit_km))

    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        candidates: List[Dict[str, Any]] = cursor.execute(
            """
            SELECT i.id, i.item_type, i.user_id, i.category, i.title, i.description,
                   i.contact_name, i.contact_phone, i.latitude, i.longitude, i.location_label,
                   i.reward_note, i.image_filename, i.image_url, i.image_meta, i.created_at, u.email AS owner_email
            FROM items i
            LEFT JOIN users u ON u.id = i.user_id
            WHERE i.item_type = ?
              AND i.category = ?
              AND i.id != ?
              AND i.created_at >= datetime('now', ?)
            ORDER BY i.created_at DESC, i.id DESC
            """,
            (opposite_type, base_item["category"], item_id, f"-{day_window} day"),
        ).fetchall()

    scored_matches: List[Dict[str, Any]] = []
    for candidate in candidates:
        distance_km = haversine_km(
            base_item["latitude"],
            base_item["longitude"],
            candidate["latitude"],
            candidate["longitude"],
        )
        if distance_km <= distance_limit:
            with_distance = dict(candidate)
            with_distance["distance_km"] = round(distance_km, 2)
            scored_matches.append(with_distance)

    scored_matches.sort(key=lambda item: item["distance_km"])
    return scored_matches


def item_to_dict(item: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Convert an item row to a serializable dict."""
    if not item:
        return None

    parsed_image_meta: Dict[str, Any] = {}
    raw_meta = item.get("image_meta", "")
    if raw_meta:
        try:
            parsed_image_meta = json.loads(raw_meta)
        except json.JSONDecodeError:
            parsed_image_meta = {}

    resolved_image_url = item.get("image_url", "")
    if not resolved_image_url and item.get("image_filename", ""):
        resolved_image_url = f"/uploads/{item.get('image_filename', '')}"

    payload = {
        "id": item["id"],
        "item_type": item["item_type"],
        "user_id": item.get("user_id"),
        "category": item["category"],
        "title": item["title"],
        "description": item["description"],
        "contact_name": item["contact_name"],
        "contact_phone": item["contact_phone"],
        "latitude": float(item["latitude"]),
        "longitude": float(item["longitude"]),
        "location_label": item["location_label"],
        "reward_note": item["reward_note"],
        "image_filename": item.get("image_filename", ""),
        "image_url": resolved_image_url,
        "image_meta": parsed_image_meta,
        "owner_email": item.get("owner_email"),
        "created_at": item["created_at"],
    }
    if "distance_km" in item:
        payload["distance_km"] = float(item["distance_km"])
    return payload


def create_user(
    db_path: str | None,
    *,
    name: str,
    email: str,
    password_hash: str,
    auth_provider: str = "local",
    oauth_sub: str = "",
) -> int:
    """Create a user account and return its ID."""
    normalized_name = _clean_text(name, "name")
    normalized_email = _clean_text(email, "email").lower()
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO users (name, email, password_hash, auth_provider, oauth_sub)
            VALUES (?, ?, ?, ?, ?)
            """,
            (normalized_name, normalized_email, password_hash, auth_provider, oauth_sub),
        )
        connection.commit()
        return int(cursor.lastrowid)


def get_user_by_email(db_path: str | None, email: str) -> Dict[str, Any] | None:
    """Fetch one user by email."""
    normalized_email = email.strip().lower()
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT id, name, email, session_token, password_hash, auth_provider, oauth_sub, created_at
            FROM users
            WHERE email = ?
            """,
            (normalized_email,),
        ).fetchone()


def get_user_by_id(db_path: str | None, user_id: int) -> Dict[str, Any] | None:
    """Fetch one user by ID."""
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT id, name, email, session_token, password_hash, auth_provider, oauth_sub, created_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()


def get_user_by_oauth_sub(
    db_path: str | None,
    *,
    auth_provider: str,
    oauth_sub: str,
) -> Dict[str, Any] | None:
    """Fetch one user by OAuth provider subject."""
    provider = auth_provider.strip().lower()
    sub = oauth_sub.strip()
    if not provider or not sub:
        return None
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT id, name, email, session_token, password_hash, auth_provider, oauth_sub, created_at
            FROM users
            WHERE auth_provider = ? AND oauth_sub = ?
            """,
            (provider, sub),
        ).fetchone()


def link_user_oauth(
    db_path: str | None,
    *,
    user_id: int,
    auth_provider: str,
    oauth_sub: str,
) -> None:
    """Attach OAuth provider/sub information to an existing user."""
    provider = auth_provider.strip().lower()
    sub = oauth_sub.strip()
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE users
            SET auth_provider = ?, oauth_sub = ?
            WHERE id = ?
            """,
            (provider, sub, user_id),
        )
        connection.commit()


def set_user_session_token(
    db_path: str | None,
    *,
    user_id: int,
    session_token: str | None,
) -> None:
    """Update session token for a user."""
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE users
            SET session_token = ?
            WHERE id = ?
            """,
            (session_token, user_id),
        )
        connection.commit()


def get_user_by_session_token(
    db_path: str | None,
    session_token: str,
) -> Dict[str, Any] | None:
    """Fetch one user by session token."""
    token = session_token.strip()
    if not token:
        return None
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT id, name, email, session_token, password_hash, auth_provider, oauth_sub, created_at
            FROM users
            WHERE session_token = ?
            """,
            (token,),
        ).fetchone()


def create_otp_code(
    db_path: str | None,
    *,
    user_id: int,
    channel: str,
    destination: str,
    code: str,
    expires_at: str,
) -> int:
    """Create OTP code row and return ID."""
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO otp_codes (user_id, channel, destination, code, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, channel, destination, code, expires_at),
        )
        connection.commit()
        return int(cursor.lastrowid)


def get_active_otp_code(
    db_path: str | None,
    *,
    user_id: int,
    channel: str,
    destination: str,
    code: str,
) -> Dict[str, Any] | None:
    """Return latest valid OTP row matching fields."""
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT id, user_id, channel, destination, code, expires_at, consumed_at, created_at
            FROM otp_codes
            WHERE user_id = ?
              AND channel = ?
              AND destination = ?
              AND code = ?
              AND consumed_at IS NULL
              AND expires_at > datetime('now')
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id, channel, destination, code),
        ).fetchone()


def consume_otp_code(db_path: str | None, *, otp_id: int) -> None:
    """Mark OTP as consumed."""
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE otp_codes
            SET consumed_at = datetime('now')
            WHERE id = ?
            """,
            (otp_id,),
        )
        connection.commit()


def verify_user_contact(
    db_path: str | None,
    *,
    user_id: int,
    channel: str,
    value: str,
) -> None:
    """Mark user contact channel as verified."""
    if channel not in {"email", "phone"}:
        raise ValueError("channel must be email or phone")
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        if channel == "email":
            cursor.execute(
                """
                UPDATE users
                SET email_verified = 1
                WHERE id = ?
                """,
                (user_id,),
            )
        else:
            cursor.execute(
                """
                UPDATE users
                SET phone = ?, phone_verified = 1
                WHERE id = ?
                """,
                (value.strip(), user_id),
            )
        connection.commit()


def create_claim(
    db_path: str | None,
    *,
    item_id: int,
    claimant_user_id: int,
    message: str,
) -> int:
    """Create a claim request and return claim ID."""
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO claims (item_id, claimant_user_id, status, message)
            VALUES (?, ?, 'pending', ?)
            """,
            (item_id, claimant_user_id, message.strip()),
        )
        connection.commit()
        return int(cursor.lastrowid)


def list_claims_for_item(db_path: str | None, *, item_id: int) -> List[Dict[str, Any]]:
    """List claims for an item."""
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        rows = cursor.execute(
            """
            SELECT c.id, c.item_id, c.claimant_user_id, c.status, c.message, c.created_at, c.updated_at,
                   u.name AS claimant_name, u.email AS claimant_email
            FROM claims c
            LEFT JOIN users u ON u.id = c.claimant_user_id
            WHERE c.item_id = ?
            ORDER BY c.created_at DESC, c.id DESC
            """,
            (item_id,),
        ).fetchall()
    return rows


def get_claim(db_path: str | None, *, claim_id: int) -> Dict[str, Any] | None:
    """Get a claim by ID."""
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT c.id, c.item_id, c.claimant_user_id, c.status, c.message, c.created_at, c.updated_at,
                   u.name AS claimant_name, u.email AS claimant_email
            FROM claims c
            LEFT JOIN users u ON u.id = c.claimant_user_id
            WHERE c.id = ?
            """,
            (claim_id,),
        ).fetchone()


def update_claim_status(
    db_path: str | None,
    *,
    claim_id: int,
    status: str,
) -> None:
    """Update claim status."""
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE claims
            SET status = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (status, claim_id),
        )
        connection.commit()


def update_item_status(
    db_path: str | None,
    *,
    item_id: int,
    status: str,
) -> None:
    """Update item status."""
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE items
            SET status = ?
            WHERE id = ?
            """,
            (status, item_id),
        )
        connection.commit()


def list_user_email_notification_targets(
    db_path: str | None,
    *,
    item_id: int,
) -> List[str]:
    """Return user emails to notify for an item match event."""
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        rows = cursor.execute(
            """
            SELECT DISTINCT u.email
            FROM items i
            JOIN users u ON u.id = i.user_id
            WHERE i.id = ?
              AND u.email_verified = 1
              AND u.notify_email = 1
            """,
            (item_id,),
        ).fetchall()
    return [str(row["email"]) for row in rows if row.get("email")]
