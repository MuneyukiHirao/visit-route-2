import time

from vrp.solver import build_global_plan


def make_driver(id="A"):
    return {"id": id, "start_time": 8 * 60, "end_time": 19 * 60}


def test_time_limit_is_respected_small_case():
    dates = ["2025-11-23"]
    branch = {"lat": 10.0, "lon": 123.0}
    targets = [
        {"id": "T1", "lat": 10.05, "lon": 123.05, "stay_minutes": 10, "required": True, "time_window": None, "datetime_window": None}
    ]
    drivers_by_date = {dates[0]: [make_driver("A")]}

    started = time.perf_counter()
    plan = build_global_plan(
        dates=dates,
        branch=branch,
        drivers_by_date=drivers_by_date,
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=1,
    )
    elapsed = time.perf_counter() - started

    # Should finish well under a few seconds for a tiny instance.
    assert elapsed < 5.0, f"Solver exceeded expected wall time: {elapsed:.2f}s"
    assert plan["status"] == "success"


def test_travel_positive_for_feasible_solution():
    dates = ["2025-11-23"]
    branch = {"lat": 10.0, "lon": 123.0}
    targets = [
        {"id": "T1", "lat": 10.5, "lon": 123.5, "stay_minutes": 10, "required": True, "time_window": None, "datetime_window": None},
        {"id": "T2", "lat": 10.6, "lon": 123.6, "stay_minutes": 10, "required": True, "time_window": None, "datetime_window": None},
    ]
    drivers_by_date = {dates[0]: [make_driver("A"), make_driver("B")]}

    plan = build_global_plan(
        dates=dates,
        branch=branch,
        drivers_by_date=drivers_by_date,
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=5,
    )
    assert plan["status"] == "success"
    # At least one stop should have positive travel (no fallback with zero travel)
    travel_values = []
    for sched in plan["schedules"]:
        for route in sched["routes"]:
            for stop in route.get("stops", []):
                travel_values.append(stop["travel_minutes"])
            travel_values.append(route.get("return_travel_minutes", 0))
    assert any(t > 0 for t in travel_values), "All travel times were zero, likely fallback"
    assert not plan.get("unassigned")


def test_no_solution_returns_no_solution_status():
    # Force an impossible case by giving no drivers
    dates = ["2025-11-23"]
    branch = {"lat": 10.0, "lon": 123.0}
    targets = [
        {"id": "T1", "lat": 10.1, "lon": 123.1, "stay_minutes": 10, "required": True, "time_window": None, "datetime_window": None}
    ]
    drivers_by_date = {dates[0]: []}

    plan = build_global_plan(
        dates=dates,
        branch=branch,
        drivers_by_date=drivers_by_date,
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=1,
    )
    assert plan["status"] == "error" or plan["status"] == "no_solution"


def test_travel_and_return_positive_for_spread_targets():
    dates = ["2025-11-23"]
    branch = {"lat": 10.0, "lon": 123.0}
    targets = [
        {"id": "T1", "lat": 10.0, "lon": 123.0, "stay_minutes": 10, "required": True, "time_window": None, "datetime_window": None},
        {"id": "T2", "lat": 10.6, "lon": 123.8, "stay_minutes": 10, "required": True, "time_window": None, "datetime_window": None},
    ]
    drivers_by_date = {dates[0]: [make_driver("A")]}

    plan = build_global_plan(
        dates=dates,
        branch=branch,
        drivers_by_date=drivers_by_date,
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=5,
    )
    assert plan["status"] == "success"
    sched = plan["schedules"][0]
    assert sched["routes"], "No routes created"
    route = sched["routes"][0]
    # Each stop should have non-zero travel, and total travel should be positive.
    assert all(s.get("travel_minutes", 0) > 0 for s in route["stops"])
    assert route.get("travel_minutes", 0) > 0
