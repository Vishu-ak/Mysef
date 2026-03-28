"""Database layer for the lost-and-found map web app."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .geo import haversine_km


DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "lost_and_found.db"


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
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_type TEXT NOT NULL CHECK(item_type IN ('lost', 'found')),
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                contact_name TEXT NOT NULL,
                contact_phone TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                location_label TEXT NOT NULL DEFAULT '',
                reward_note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
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
                item_type, category, title, description, contact_name, contact_phone,
                latitude, longitude, location_label, reward_note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_type,
                normalized_category,
                normalized_title,
                normalized_description,
                normalized_contact_name,
                normalized_contact_phone,
                normalized_lat,
                normalized_lon,
                location_label.strip(),
                reward_note.strip(),
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
            SELECT id, item_type, category, title, description, contact_name, contact_phone,
                   latitude, longitude, location_label, reward_note, created_at
            FROM items
            WHERE id = ?
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
        SELECT id, item_type, category, title, description, contact_name, contact_phone,
               latitude, longitude, location_label, reward_note, created_at
        FROM items
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
            SELECT id, item_type, category, title, description, contact_name, contact_phone,
                   latitude, longitude, location_label, reward_note, created_at
            FROM items
            WHERE item_type = ?
              AND category = ?
              AND id != ?
              AND created_at >= datetime('now', ?)
            ORDER BY created_at DESC, id DESC
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

    payload = {
        "id": item["id"],
        "item_type": item["item_type"],
        "category": item["category"],
        "title": item["title"],
        "description": item["description"],
        "contact_name": item["contact_name"],
        "contact_phone": item["contact_phone"],
        "latitude": float(item["latitude"]),
        "longitude": float(item["longitude"]),
        "location_label": item["location_label"],
        "reward_note": item["reward_note"],
        "created_at": item["created_at"],
    }
    if "distance_km" in item:
        payload["distance_km"] = float(item["distance_km"])
    return payload
