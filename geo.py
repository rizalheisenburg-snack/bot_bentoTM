"""Perhitungan jarak & tier minimal order berdasar lokasi customer."""
import math

EARTH_RADIUS_KM = 6371.0


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Jarak great-circle antara dua titik lat/lon, dalam km."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def get_min_order(lat: float, lon: float, cafe_lat: float, cafe_lon: float) -> int:
    """Ambang minimal order (riel) berdasar jarak dari cafe. Tiered, bukan blocking."""
    distance_km = haversine(lat, lon, cafe_lat, cafe_lon)
    return 20000 if distance_km < 5 else 40000
