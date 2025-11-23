import math

import pytest

from vrp.geo import haversine_km, travel_time_minutes


def test_haversine_distance_matches_known_value():
    # (0,0) to (0,1) is about 111.195 km on Earth.
    dist = haversine_km((0.0, 0.0), (0.0, 1.0))
    assert math.isclose(dist, 111.195, rel_tol=1e-3)


def test_travel_time_minutes_scales_with_speed():
    dist_km = 40.0
    speed_kmph = 40.0
    minutes = travel_time_minutes(dist_km, speed_kmph)
    assert math.isclose(minutes, 60.0, rel_tol=1e-6)
    # Doubling speed halves time.
    faster = travel_time_minutes(dist_km, speed_kmph * 2)
    assert faster < minutes


def test_travel_time_zero_distance():
    assert travel_time_minutes(0.0, 50.0) == 0.0


def test_travel_time_invalid_speed():
    with pytest.raises(ValueError):
        travel_time_minutes(10.0, 0.0)
