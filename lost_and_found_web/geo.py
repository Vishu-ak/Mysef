"""Geospatial utility functions for distance calculations."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance between coordinates in kilometers."""
    earth_radius_km = 6371.0
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
    )
    c = 2 * asin(sqrt(a))
    return earth_radius_km * c
