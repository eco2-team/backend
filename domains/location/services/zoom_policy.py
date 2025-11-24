from __future__ import annotations

DEFAULT_RADIUS_METERS = 5000

ZOOM_RADIUS_TABLE = {
    1: 80000,
    2: 60000,
    3: 45000,
    4: 30000,
    5: 20000,
    6: 15000,
    7: 10000,
    8: 8000,
    9: 6000,
    10: 4500,
    11: 3000,
    12: 2000,
    13: 1200,
    14: 800,
    15: 500,
    16: 300,
    17: 200,
    18: 150,
    19: 120,
    20: 100,
}

ZOOM_LIMIT_TABLE = {
    1: 50,
    4: 80,
    7: 120,
    10: 160,
    13: 200,
}


def radius_from_zoom(zoom: int | None) -> int:
    if zoom is None:
        return DEFAULT_RADIUS_METERS
    zoom = max(1, min(zoom, 20))
    return ZOOM_RADIUS_TABLE.get(zoom, DEFAULT_RADIUS_METERS)


def limit_from_zoom(zoom: int | None) -> int:
    if zoom is None:
        return 200
    zoom = max(1, min(zoom, 20))
    for level in sorted(ZOOM_LIMIT_TABLE.keys(), reverse=True):
        if zoom >= level:
            return ZOOM_LIMIT_TABLE[level]
    return 50

