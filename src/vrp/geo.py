"""
Geospatial utilities for VRP.
"""

from typing import Tuple

Point = Tuple[float, float]


def haversine_km(origin: Point, destination: Point) -> float:
    """
    Compute great-circle distance between two (lat, lon) points in kilometers.
    """
    import math

    lat1, lon1 = origin
    lat2, lon2 = destination
    r = 6371.0088  # mean Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def travel_time_minutes(distance_km: float, speed_kmph: float) -> float:
    """
    Convert distance (km) to travel time in minutes given speed (km/h).
    """
    if speed_kmph <= 0:
        raise ValueError("speed_kmph must be positive")
    if distance_km <= 0:
        return 0.0
    hours = distance_km / speed_kmph
    return hours * 60.0
