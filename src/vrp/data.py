"""
Data generation and model structures.
"""

import math
import random
import datetime
from typing import List, Optional, Tuple, Dict, Any

CEBU_LAT_RANGE = (9.9, 11.5)
CEBU_LON_RANGE = (123.4, 124.2)
# 粗いCebu島ポリゴン（lon, lat）。陸地判定用にシンプルな輪郭を用意。
CEBU_POLYGON = [
    (123.45, 10.00),
    (123.50, 10.30),
    (123.55, 10.65),
    (123.55, 10.90),
    (123.60, 11.05),
    (123.70, 11.20),
    (123.90, 11.30),
    (124.00, 11.25),
    (124.05, 11.05),
    (124.10, 10.75),
    (124.10, 10.55),
    (124.08, 10.35),
    (124.02, 10.15),
    (123.92, 9.95),
    (123.78, 9.85),
    (123.65, 9.80),
    (123.52, 9.82),
    (123.46, 9.90),
]

def point_in_polygon(lon: float, lat: float, polygon: List[Tuple[float, float]]) -> bool:
    """
    Ray-casting point-in-polygon (lon, lat). Polygon is list of (lon, lat).
    """
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        # Check if edge crosses the horizontal ray to the right of the point.
        if ((y1 > lat) != (y2 > lat)):
            x_int = x1 + (lon - x1) * 0  # placeholder to avoid lint warning
            x_int = (x2 - x1) * (lat - y1) / (y2 - y1 + 1e-12) + x1
            if lon < x_int:
                inside = not inside
    return inside


def generate_branch(seed: int) -> Dict[str, Any]:
    """
    Generate a branch/base location (lat, lon) within Cebu island bounds.
    """
    rng = random.Random(seed)

    def inside(lon: float, lat: float) -> bool:
        return point_in_polygon(lon, lat, CEBU_POLYGON)

    for _ in range(100):
        lat = rng.uniform(*CEBU_LAT_RANGE)
        lon = rng.uniform(*CEBU_LON_RANGE)
        if inside(lon, lat):
            return {"lat": round(lat, 6), "lon": round(lon, 6)}
    # Fallback: return center of bounding box if sampling failed
    lat = sum(CEBU_LAT_RANGE) / 2
    lon = sum(CEBU_LON_RANGE) / 2
    return {"lat": round(lat, 6), "lon": round(lon, 6)}


def generate_targets(
    seed: int,
    n: int = 100,
    stay_minutes_range: Tuple[int, int] = (30, 90),
    weekday_time_window: Optional[Tuple[int, int]] = (8 * 60, 19 * 60),
    center: Optional[Tuple[float, float]] = None,
    cluster_radius_km: Optional[float] = None,
    dates: Optional[List[str]] = None,
    approx_per_day: int = 10,
    time_windows_per_day: int = 2,
) -> List[Dict[str, Any]]:
    """
    Generate n targets in Cebu island with optional time windows, required flag, and stay durations.
    If center and cluster_radius_km are provided, generate within that radius around center.
    """
    rng = random.Random(seed)
    targets: List[Dict[str, Any]] = []
    earth_radius_km = 6371.0
    seen: set[Tuple[float, float]] = set()

    def inside(lon: float, lat: float) -> bool:
        return point_in_polygon(lon, lat, CEBU_POLYGON)

    def clamp_latlon(lat: float, lon: float) -> Tuple[float, float]:
        lat = min(max(lat, CEBU_LAT_RANGE[0]), CEBU_LAT_RANGE[1])
        lon = min(max(lon, CEBU_LON_RANGE[0]), CEBU_LON_RANGE[1])
        return lat, lon

    for i in range(n):
        stay = rng.randint(stay_minutes_range[0], stay_minutes_range[1])
        for _ in range(20):
            if center and cluster_radius_km:
                bearing = rng.uniform(0, 2 * math.pi)
                distance_km = rng.uniform(0, cluster_radius_km)
                ang_dist = distance_km / earth_radius_km
                lat1 = math.radians(center[0])
                lon1 = math.radians(center[1])
                lat2 = math.asin(math.sin(lat1) * math.cos(ang_dist) + math.cos(lat1) * math.sin(ang_dist) * math.cos(bearing))
                lon2 = lon1 + math.atan2(
                    math.sin(bearing) * math.sin(ang_dist) * math.cos(lat1),
                    math.cos(ang_dist) - math.sin(lat1) * math.sin(lat2),
                )
                lat_deg = math.degrees(lat2)
                lon_deg = math.degrees(lon2)
                lat, lon = clamp_latlon(lat_deg, lon_deg)
            else:
                lat = rng.uniform(*CEBU_LAT_RANGE)
                lon = rng.uniform(*CEBU_LON_RANGE)
            lat_r = round(lat, 6)
            lon_r = round(lon, 6)
            if (lat_r, lon_r) not in seen and inside(lon_r, lat_r):
                seen.add((lat_r, lon_r))
                lat, lon = lat_r, lon_r
                break
        else:
            # If all attempts collide, jitter slightly and keep the sampled stay.
            lat = round(lat + rng.uniform(-0.0003, 0.0003), 6)
            lon = round(lon + rng.uniform(-0.0003, 0.0003), 6)
            if inside(lon, lat):
                seen.add((lat, lon))

        # 30% required by default.
        required = rng.random() < 0.3

        targets.append(
            {
                "id": f"T{i+1:03d}",
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "stay_minutes": stay,
                "required": required,
                # Assigned later to align time windows by day block.
                "time_window": None,
                "datetime_window": None,
            }
        )
    # Assign dated time windows after all targets are created.
    if weekday_time_window:
        day_start, day_end = weekday_time_window
        date_list = dates if dates else [str(datetime.date.today())]
        total_days = max(1, (n + approx_per_day - 1) // approx_per_day)
        while len(date_list) < total_days:
            last = datetime.date.fromisoformat(date_list[-1])
            date_list.append(str(last + datetime.timedelta(days=1)))
        for day_idx in range(total_days):
            block_start = day_idx * approx_per_day
            block_end = min(n, (day_idx + 1) * approx_per_day)
            block_size = block_end - block_start
            if block_size <= 0:
                continue
            k = min(time_windows_per_day, block_size)
            chosen = rng.sample(range(block_start, block_end), k=k)
            for idx in chosen:
                window_span = rng.randint(60, 180)  # 1h to 3h window
                start = rng.randint(day_start, max(day_start, day_end - window_span))
                end = min(day_end, start + window_span)
                targets[idx]["time_window"] = (start, end)
                targets[idx]["datetime_window"] = {
                    "date": date_list[min(day_idx, len(date_list) - 1)],
                    "start": f"{start//60:02d}:{start%60:02d}",
                    "end": f"{end//60:02d}:{end%60:02d}",
                }
    return targets
