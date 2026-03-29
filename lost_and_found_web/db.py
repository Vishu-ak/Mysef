"""Database layer for the lost-and-found map web app."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .geo import haversine_km


DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "lost_and_found.db"
VALID_ITEM_STATUSES = {"open", "in_discussion", "claimed", "returned", "closed"}
VALID_CLAIM_STATUSES = {"pending", "approved", "rejected", "cancelled"}


def _dict_factory(cursor: sqlite3.Cursor, row: Iterable[Any]) -> Dict[str, Any]:
    return {column[0]: row[idx] for idx, column in enumerate(cursor.description)}


def _resolve_db_path(db_path: str | None = None) -> Path:
    return Path(db_path) if db_path else DEFAULT_DB_PATH


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Return sqlite connection configured for dict-like rows."""
    path = _resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = _dict_factory
    return connection


def _column_names(cursor: sqlite3.Cursor, table_name: str) -> set[str]:
    return {row["name"] for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()}


def init_db(db_path: str | None = None) -> None:
    """Initialize or migrate schema."""
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
                email_verified INTEGER NOT NULL DEFAULT 0,
                phone TEXT NOT NULL DEFAULT '',
                phone_verified INTEGER NOT NULL DEFAULT 0,
                notify_email INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        user_columns = _column_names(cursor, "users")
        if "session_token" not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN session_token TEXT")
        if "auth_provider" not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN auth_provider TEXT NOT NULL DEFAULT 'local'")
        if "oauth_sub" not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN oauth_sub TEXT NOT NULL DEFAULT ''")
        if "email_verified" not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
        if "phone" not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
        if "phone_verified" not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN phone_verified INTEGER NOT NULL DEFAULT 0")
        if "notify_email" not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN notify_email INTEGER NOT NULL DEFAULT 1")

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
                status TEXT NOT NULL DEFAULT 'open',
                status_updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        item_columns = _column_names(cursor, "items")
        if "user_id" not in item_columns:
            cursor.execute("ALTER TABLE items ADD COLUMN user_id INTEGER")
        if "image_filename" not in item_columns:
            cursor.execute("ALTER TABLE items ADD COLUMN image_filename TEXT NOT NULL DEFAULT ''")
        if "image_url" not in item_columns:
            cursor.execute("ALTER TABLE items ADD COLUMN image_url TEXT NOT NULL DEFAULT ''")
        if "image_meta" not in item_columns:
            cursor.execute("ALTER TABLE items ADD COLUMN image_meta TEXT NOT NULL DEFAULT ''")
        if "status" not in item_columns:
            cursor.execute("ALTER TABLE items ADD COLUMN status TEXT NOT NULL DEFAULT 'open'")
        if "status_updated_at" not in item_columns:
            cursor.execute(
                "ALTER TABLE items ADD COLUMN status_updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
            )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS otp_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel TEXT NOT NULL,
                destination TEXT NOT NULL,
                code TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                consumed_at TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 5,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        otp_columns = _column_names(cursor, "otp_codes")
        if "attempts" not in otp_columns:
            cursor.execute("ALTER TABLE otp_codes ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
        if "max_attempts" not in otp_columns:
            cursor.execute("ALTER TABLE otp_codes ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 5")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                claimant_user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                request_message TEXT NOT NULL DEFAULT '',
                proof_answer TEXT NOT NULL DEFAULT '',
                resolution_note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        claim_columns = _column_names(cursor, "claims")
        if "request_message" not in claim_columns:
            cursor.execute("ALTER TABLE claims ADD COLUMN request_message TEXT NOT NULL DEFAULT ''")
        if "proof_answer" not in claim_columns:
            cursor.execute("ALTER TABLE claims ADD COLUMN proof_answer TEXT NOT NULL DEFAULT ''")
        if "resolution_note" not in claim_columns:
            cursor.execute("ALTER TABLE claims ADD COLUMN resolution_note TEXT NOT NULL DEFAULT ''")
        if "updated_at" not in claim_columns:
            cursor.execute("ALTER TABLE claims ADD COLUMN updated_at TEXT NOT NULL DEFAULT (datetime('now'))")
        if "message" in claim_columns and "request_message" in claim_columns:
            cursor.execute(
                """
                UPDATE claims
                SET request_message = CASE
                    WHEN request_message = '' THEN message
                    ELSE request_message
                END
                """
            )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS watchers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_type TEXT NOT NULL CHECK(item_type IN ('lost', 'found')),
                category TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                radius_km REAL NOT NULL DEFAULT 10,
                last_notified_item_id INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_id INTEGER,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS item_status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                owner_user_id INTEGER NOT NULL,
                old_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )

        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_session_token ON users(session_token)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_type_category ON items(item_type, category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_created_at ON items(created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_user_id ON items(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_item_id ON claims(item_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_claimant_user_id ON claims(claimant_user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_otp_user_channel ON otp_codes(user_id, channel)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_watchers_lookup ON watchers(item_type, category)")

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
    """Insert a new item and return ID."""
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
                latitude, longitude, location_label, reward_note, image_filename, image_url, image_meta, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
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
    """Fetch item by ID."""
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT i.id, i.item_type, i.user_id, i.category, i.title, i.description,
                   i.contact_name, i.contact_phone, i.latitude, i.longitude, i.location_label,
                   i.reward_note, i.image_filename, i.image_url, i.image_meta,
                   i.status, i.status_updated_at, i.created_at,
                   u.email AS owner_email
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
               i.reward_note, i.image_filename, i.image_url, i.image_meta,
               i.status, i.status_updated_at, i.created_at,
               u.email AS owner_email
        FROM items i
        LEFT JOIN users u ON u.id = i.user_id
        WHERE 1 = 1
    """
    params: List[Any] = []
    if item_type:
        sql += " AND i.item_type = ?"
        params.append(item_type.strip().lower())
    if category:
        sql += " AND i.category = ?"
        params.append(category.strip().lower())
    if query:
        sql += " AND (LOWER(i.title) LIKE ? OR LOWER(i.description) LIKE ?)"
        query_text = f"%{query.strip().lower()}%"
        params.extend([query_text, query_text])
    sql += " ORDER BY i.created_at DESC, i.id DESC"

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
            enriched = dict(row)
            enriched["distance_km"] = round(distance_km, 2)
            filtered.append(enriched)
    return filtered


def get_matches_for_item(
    db_path: str | None,
    *,
    item_id: int,
    distance_limit_km: float = 8.0,
    time_limit_days: int = 14,
) -> List[Dict[str, Any]]:
    """Return opposite-type candidates in same category and nearby radius."""
    base_item = get_item(db_path, item_id)
    if not base_item:
        return []
    opposite = "found" if base_item["item_type"] == "lost" else "lost"
    day_window = max(1, int(time_limit_days))
    limit = max(0.1, float(distance_limit_km))

    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        candidates = cursor.execute(
            """
            SELECT i.id, i.item_type, i.user_id, i.category, i.title, i.description,
                   i.contact_name, i.contact_phone, i.latitude, i.longitude, i.location_label,
                   i.reward_note, i.image_filename, i.image_url, i.image_meta,
                   i.status, i.status_updated_at, i.created_at,
                   u.email AS owner_email
            FROM items i
            LEFT JOIN users u ON u.id = i.user_id
            WHERE i.item_type = ?
              AND i.category = ?
              AND i.id != ?
              AND i.created_at >= datetime('now', ?)
              AND i.status != 'closed'
            ORDER BY i.created_at DESC, i.id DESC
            """,
            (opposite, base_item["category"], item_id, f"-{day_window} day"),
        ).fetchall()

    matches: List[Dict[str, Any]] = []
    for row in candidates:
        distance = haversine_km(base_item["latitude"], base_item["longitude"], row["latitude"], row["longitude"])
        if distance <= limit:
            enriched = dict(row)
            enriched["distance_km"] = round(distance, 2)
            matches.append(enriched)
    matches.sort(key=lambda row: row["distance_km"])
    return matches


def item_to_dict(item: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Convert DB row to serializable dict."""
    if not item:
        return None
    parsed_meta: Dict[str, Any] = {}
    raw_meta = item.get("image_meta", "")
    if raw_meta:
        try:
            parsed_meta = json.loads(raw_meta)
        except json.JSONDecodeError:
            parsed_meta = {}
    image_url = item.get("image_url", "")
    if not image_url and item.get("image_filename", ""):
        image_url = f"/uploads/{item['image_filename']}"
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
        "location_label": item.get("location_label", ""),
        "reward_note": item.get("reward_note", ""),
        "image_filename": item.get("image_filename", ""),
        "image_url": image_url,
        "image_meta": parsed_meta,
        "status": item.get("status", "open"),
        "status_updated_at": item.get("status_updated_at", ""),
        "owner_email": item.get("owner_email"),
        "created_at": item["created_at"],
    }
    if "distance_km" in item:
        payload["distance_km"] = float(item["distance_km"])
    if "match_score" in item:
        payload["match_score"] = float(item["match_score"])
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
    normalized_name = _clean_text(name, "name")
    normalized_email = _clean_text(email, "email").lower()
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO users (name, email, password_hash, auth_provider, oauth_sub)
            VALUES (?, ?, ?, ?, ?)
            """,
            (normalized_name, normalized_email, password_hash, auth_provider, oauth_sub.strip()),
        )
        connection.commit()
        return int(cursor.lastrowid)


def get_user_by_email(db_path: str | None, email: str) -> Dict[str, Any] | None:
    normalized_email = email.strip().lower()
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT id, name, email, session_token, password_hash, auth_provider, oauth_sub,
                   email_verified, phone, phone_verified, notify_email, created_at
            FROM users
            WHERE email = ?
            """,
            (normalized_email,),
        ).fetchone()


def get_user_by_id(db_path: str | None, user_id: int) -> Dict[str, Any] | None:
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT id, name, email, session_token, password_hash, auth_provider, oauth_sub,
                   email_verified, phone, phone_verified, notify_email, created_at
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
    provider = auth_provider.strip().lower()
    sub = oauth_sub.strip()
    if not provider or not sub:
        return None
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT id, name, email, session_token, password_hash, auth_provider, oauth_sub,
                   email_verified, phone, phone_verified, notify_email, created_at
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
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE users
            SET auth_provider = ?, oauth_sub = ?
            WHERE id = ?
            """,
            (auth_provider.strip().lower(), oauth_sub.strip(), user_id),
        )
        connection.commit()


def set_user_session_token(
    db_path: str | None,
    *,
    user_id: int,
    session_token: str | None,
) -> None:
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE users SET session_token = ? WHERE id = ?", (session_token, user_id))
        connection.commit()


def get_user_by_session_token(
    db_path: str | None,
    session_token: str,
) -> Dict[str, Any] | None:
    token = session_token.strip()
    if not token:
        return None
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT id, name, email, session_token, password_hash, auth_provider, oauth_sub,
                   email_verified, phone, phone_verified, notify_email, created_at
            FROM users
            WHERE session_token = ?
            """,
            (token,),
        ).fetchone()


def _utc_dt_string(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def save_auth_otp(
    db_path: str | None,
    *,
    user_id: int,
    code: str,
    ttl_minutes: int,
    max_attempts: int,
) -> int:
    user = get_user_by_id(db_path, user_id)
    if not user:
        raise ValueError("user not found")
    expires_at = _utc_dt_string(datetime.now(timezone.utc) + timedelta(minutes=max(1, ttl_minutes)))
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO otp_codes (user_id, channel, destination, code, expires_at, attempts, max_attempts)
            VALUES (?, 'auth', ?, ?, ?, 0, ?)
            """,
            (user_id, str(user["email"]), code.strip(), expires_at, max(1, max_attempts)),
        )
        connection.commit()
        return int(cursor.lastrowid)


def verify_auth_otp(
    db_path: str | None,
    *,
    user_id: int,
    code: str,
) -> tuple[bool, str]:
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        otp = cursor.execute(
            """
            SELECT id, code, expires_at, consumed_at, attempts, max_attempts
            FROM otp_codes
            WHERE user_id = ? AND channel = 'auth'
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        if not otp:
            return False, "OTP not found"
        if otp["consumed_at"]:
            return False, "OTP already used"
        if otp["attempts"] >= otp["max_attempts"]:
            return False, "OTP attempts exceeded"
        now_string = _utc_dt_string(datetime.now(timezone.utc))
        if now_string > str(otp["expires_at"]):
            return False, "OTP expired"
        if str(otp["code"]) != code.strip():
            cursor.execute(
                "UPDATE otp_codes SET attempts = attempts + 1 WHERE id = ?",
                (otp["id"],),
            )
            connection.commit()
            return False, "Invalid OTP"
        cursor.execute(
            "UPDATE otp_codes SET consumed_at = datetime('now') WHERE id = ?",
            (otp["id"],),
        )
        connection.commit()
    return True, "ok"


def create_otp_code(
    db_path: str | None,
    *,
    user_id: int,
    channel: str,
    destination: str,
    code: str,
    expires_at: str,
) -> int:
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO otp_codes (user_id, channel, destination, code, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, channel.strip(), destination.strip(), code.strip(), expires_at),
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
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT *
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
            (user_id, channel.strip(), destination.strip(), code.strip()),
        ).fetchone()


def consume_otp_code(db_path: str | None, *, otp_id: int) -> None:
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE otp_codes SET consumed_at = datetime('now') WHERE id = ?", (otp_id,))
        connection.commit()


def verify_user_contact(
    db_path: str | None,
    *,
    user_id: int,
    channel: str,
    value: str,
) -> None:
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        if channel == "email":
            cursor.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (user_id,))
        elif channel == "phone":
            cursor.execute(
                "UPDATE users SET phone = ?, phone_verified = 1 WHERE id = ?",
                (value.strip(), user_id),
            )
        else:
            raise ValueError("channel must be email or phone")
        connection.commit()


def subscribe_watcher(
    db_path: str | None,
    *,
    user_id: int,
    item_type: str,
    category: str,
    latitude: float,
    longitude: float,
    radius_km: float,
) -> int:
    normalized_type = _normalize_item_type(item_type)
    normalized_category = _clean_text(category, "category").lower()
    normalized_lat, normalized_lon = _normalize_coords(latitude, longitude)
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO watchers (user_id, item_type, category, latitude, longitude, radius_km)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, normalized_type, normalized_category, normalized_lat, normalized_lon, max(0.5, float(radius_km))),
        )
        connection.commit()
        return int(cursor.lastrowid)


def list_user_watchers(db_path: str | None, *, user_id: int) -> List[Dict[str, Any]]:
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT id, user_id, item_type, category, latitude, longitude, radius_km, last_notified_item_id, created_at
            FROM watchers
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()


def get_item_watchers_for_match(
    db_path: str | None,
    new_item: Dict[str, Any] | int,
) -> List[Dict[str, Any]]:
    if isinstance(new_item, int):
        item_row = get_item(db_path, new_item)
    else:
        item_row = new_item
    if not item_row:
        return []
    item_lat = float(item_row["latitude"])
    item_lon = float(item_row["longitude"])
    item_type = str(item_row["item_type"])
    category = str(item_row["category"]).lower()
    owner_user_id = int(item_row.get("user_id") or 0)

    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        watchers = cursor.execute(
            """
            SELECT w.id AS watcher_id, w.user_id AS watcher_user_id, w.item_type, w.category,
                   w.latitude, w.longitude, w.radius_km,
                   u.name AS watcher_name, u.email AS watcher_email, u.email_verified, u.notify_email
            FROM watchers w
            JOIN users u ON u.id = w.user_id
            WHERE w.item_type = ?
              AND w.category = ?
              AND w.user_id != ?
              AND u.email_verified = 1
              AND u.notify_email = 1
            """,
            (item_type, category, owner_user_id),
        ).fetchall()

    matches: List[Dict[str, Any]] = []
    for watcher in watchers:
        distance = haversine_km(item_lat, item_lon, watcher["latitude"], watcher["longitude"])
        if distance <= float(watcher["radius_km"]):
            row = dict(watcher)
            row["distance_km"] = round(distance, 2)
            matches.append(row)
    matches.sort(key=lambda row: row["distance_km"])
    return matches


def mark_watcher_notified(
    db_path: str | None,
    *,
    watcher_id: int,
    matched_item_id: int,
) -> None:
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE watchers SET last_notified_item_id = ? WHERE id = ?",
            (matched_item_id, watcher_id),
        )
        connection.commit()


def list_owned_items(
    db_path: str | None,
    *,
    owner_user_id: int,
) -> List[Dict[str, Any]]:
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT i.id, i.item_type, i.user_id, i.category, i.title, i.description,
                   i.contact_name, i.contact_phone, i.latitude, i.longitude, i.location_label,
                   i.reward_note, i.image_filename, i.image_url, i.image_meta,
                   i.status, i.status_updated_at, i.created_at,
                   u.email AS owner_email
            FROM items i
            LEFT JOIN users u ON u.id = i.user_id
            WHERE i.user_id = ?
            ORDER BY i.created_at DESC, i.id DESC
            """,
            (owner_user_id,),
        ).fetchall()


def request_claim(
    db_path: str | None,
    *,
    item_id: int,
    claimer_user_id: int,
    message: str,
    proof_answer: str,
) -> int:
    item = get_item(db_path, item_id)
    if not item:
        raise ValueError("item not found")
    if int(item.get("user_id") or 0) == int(claimer_user_id):
        raise ValueError("cannot claim your own item")
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO claims (item_id, claimant_user_id, status, request_message, proof_answer, resolution_note)
            VALUES (?, ?, 'pending', ?, ?, '')
            """,
            (item_id, claimer_user_id, message.strip(), proof_answer.strip()),
        )
        connection.commit()
        return int(cursor.lastrowid)


def create_claim(
    db_path: str | None,
    *,
    item_id: int,
    claimant_user_id: int,
    message: str,
) -> int:
    """Compatibility wrapper."""
    return request_claim(
        db_path,
        item_id=item_id,
        claimer_user_id=claimant_user_id,
        message=message,
        proof_answer="",
    )


def get_claim(db_path: str | None, claim_id: int) -> Dict[str, Any] | None:
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT c.id, c.item_id, c.claimant_user_id, c.status,
                   c.request_message, c.proof_answer, c.resolution_note,
                   c.created_at, c.updated_at,
                   u.name AS requester_name, u.email AS requester_email,
                   i.title AS item_title, i.user_id AS item_owner_user_id
            FROM claims c
            LEFT JOIN users u ON u.id = c.claimant_user_id
            LEFT JOIN items i ON i.id = c.item_id
            WHERE c.id = ?
            """,
            (claim_id,),
        ).fetchone()


def get_claim_for_item_and_claimer(
    db_path: str | None,
    *,
    item_id: int,
    claimant_user_id: int,
) -> Dict[str, Any] | None:
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT id, item_id, claimant_user_id, status, request_message, proof_answer, resolution_note, created_at, updated_at
            FROM claims
            WHERE item_id = ? AND claimant_user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (item_id, claimant_user_id),
        ).fetchone()


def list_claims_for_item(
    db_path: str | None,
    *,
    item_id: int,
    owner_user_id: int | None = None,
) -> List[Dict[str, Any]]:
    if owner_user_id is not None:
        item = get_item(db_path, item_id)
        if not item or int(item.get("user_id") or 0) != int(owner_user_id):
            return []
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT c.id, c.item_id, c.claimant_user_id, c.status,
                   c.request_message, c.proof_answer, c.resolution_note,
                   c.created_at, c.updated_at,
                   u.name AS requester_name, u.email AS requester_email
            FROM claims c
            LEFT JOIN users u ON u.id = c.claimant_user_id
            WHERE c.item_id = ?
            ORDER BY c.created_at DESC, c.id DESC
            """,
            (item_id,),
        ).fetchall()


def list_claims_for_claimer(db_path: str | None, *, claimer_user_id: int) -> List[Dict[str, Any]]:
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        return cursor.execute(
            """
            SELECT c.id, c.item_id, c.claimant_user_id, c.status,
                   c.request_message, c.proof_answer, c.resolution_note,
                   c.created_at, c.updated_at,
                   i.title AS item_title
            FROM claims c
            LEFT JOIN items i ON i.id = c.item_id
            WHERE c.claimant_user_id = ?
            ORDER BY c.created_at DESC, c.id DESC
            """,
            (claimer_user_id,),
        ).fetchall()


def list_claims_for_user(db_path: str | None, *, claimer_user_id: int) -> List[Dict[str, Any]]:
    """Compatibility wrapper for user claim listing."""
    return list_claims_for_claimer(db_path, claimer_user_id=claimer_user_id)


def update_claim_status(
    db_path: str | None,
    *,
    claim_id: int,
    status: str,
) -> None:
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE claims SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, claim_id),
        )
        connection.commit()


def resolve_claim(
    db_path: str | None,
    *,
    claim_id: int,
    owner_user_id: int,
    status: str,
    resolution_note: str,
) -> Dict[str, Any] | None:
    normalized_status = status.strip().lower()
    if normalized_status not in {"approved", "rejected"}:
        raise ValueError("status must be approved or rejected")
    claim = get_claim(db_path, claim_id)
    if not claim:
        return None
    if int(claim.get("item_owner_user_id") or 0) != int(owner_user_id):
        return None
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE claims
            SET status = ?, resolution_note = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (normalized_status, resolution_note.strip(), claim_id),
        )
        if normalized_status == "approved":
            cursor.execute(
                """
                UPDATE items
                SET status = 'claimed', status_updated_at = datetime('now')
                WHERE id = ?
                """,
                (claim["item_id"],),
            )
        connection.commit()
    return get_claim(db_path, claim_id)


def update_item_status(
    db_path: str | None,
    *,
    item_id: int,
    owner_user_id: int,
    status: str,
    note: str = "",
) -> Dict[str, Any] | None:
    normalized_status = status.strip().lower()
    if normalized_status not in VALID_ITEM_STATUSES:
        raise ValueError("invalid status")
    item = get_item(db_path, item_id)
    if not item:
        return None
    if int(item.get("user_id") or 0) != int(owner_user_id):
        return None
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        old_status = str(item.get("status", "open"))
        cursor.execute(
            """
            UPDATE items
            SET status = ?, status_updated_at = datetime('now')
            WHERE id = ?
            """,
            (normalized_status, item_id),
        )
        cursor.execute(
            """
            INSERT INTO item_status_history (item_id, owner_user_id, old_status, new_status, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (item_id, owner_user_id, old_status, normalized_status, note.strip()),
        )
        connection.commit()
    return get_item(db_path, item_id)


def list_user_email_notification_targets(
    db_path: str | None,
    *,
    item_id: int,
) -> List[str]:
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


def create_notification(
    db_path: str | None,
    *,
    user_id: int,
    item_id: int,
    event_type: str,
    payload: Dict[str, Any] | None = None,
) -> int:
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO notifications (user_id, item_id, event_type, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, item_id, event_type.strip(), json.dumps(payload or {})),
        )
        connection.commit()
        return int(cursor.lastrowid)
