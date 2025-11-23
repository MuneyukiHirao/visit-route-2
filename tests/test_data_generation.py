import pytest

from vrp.data import generate_branch, generate_targets


def test_generate_branch_is_within_cebu_bounds():
    branch = generate_branch(seed=42)
    lat, lon = branch["lat"], branch["lon"]
    assert 9.9 <= lat <= 11.5
    assert 123.4 <= lon <= 124.2


def test_generate_targets_reproducible_with_seed():
    targets1 = generate_targets(seed=99, n=5)
    targets2 = generate_targets(seed=99, n=5)
    assert targets1 == targets2


def test_generate_targets_count_and_bounds():
    targets = generate_targets(seed=1, n=100)
    assert len(targets) == 100
    for t in targets:
        lat, lon = t["lat"], t["lon"]
        stay = t["stay_minutes"]
        assert 9.9 <= lat <= 11.5
        assert 123.4 <= lon <= 124.2
        assert 30 <= stay <= 90
        assert "required" in t
        assert "time_window" in t


def test_time_window_within_day():
    targets = generate_targets(seed=7, n=10, stay_minutes_range=(30, 90), weekday_time_window=(8 * 60, 19 * 60))
    for t in targets:
        tw = t["time_window"]
        assert tw is None or (tw[0] >= 0 and tw[1] <= 24 * 60 and tw[0] < tw[1])
