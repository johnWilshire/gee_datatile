"""XYZ web-mercator tile coordinate helpers."""

import math


ORIGIN_SHIFT = 20037508.342789244


def wrap_tile_x(z: int, x: int) -> int:
    """Wrap X into ``[0, 2**z)`` so dateline panning maps to a real tile."""
    n = 1 << int(z)
    return x % n


def xyz_to_bbox_4326(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Return EPSG:4326 bounds ``(min_lon, min_lat, max_lon, max_lat)`` for an XYZ tile."""
    n = 2.0**z
    lon_min = (x / n) * 360.0 - 180.0
    lon_max = ((x + 1) / n) * 360.0 - 180.0

    lat_max_rad = math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n)))
    lat_min_rad = math.atan(math.sinh(math.pi * (1.0 - 2.0 * (y + 1) / n)))

    return (lon_min, math.degrees(lat_min_rad), lon_max, math.degrees(lat_max_rad))


def xyz_to_bbox_3857(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Return EPSG:3857 bounds ``(min_x, min_y, max_x, max_y)`` for an XYZ tile."""
    origin_shift = ORIGIN_SHIFT
    tile_w = (2.0 * origin_shift) / (2.0**z)
    min_x = x * tile_w - origin_shift
    max_x = (x + 1) * tile_w - origin_shift
    max_y = origin_shift - y * tile_w
    min_y = origin_shift - (y + 1) * tile_w
    return (min_x, min_y, max_x, max_y)
