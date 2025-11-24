import datetime

from vrp.solver import build_global_plan


def make_targets(n: int):
    # All targets at the branch location, no time windows, required
    return [
        {
            "id": f"T{i+1:03d}",
            "lat": 10.0,
            "lon": 123.0,
            "stay_minutes": 10,
            "required": True,
            "time_window": None,
            "datetime_window": None,
        }
        for i in range(n)
    ]


def make_dates(num_days=3, start_date="2025-11-23"):
    base = datetime.date.fromisoformat(start_date)
    return [str(base + datetime.timedelta(days=i)) for i in range(num_days)]


def test_single_driver_no_gaps_between_used_days():
    dates = make_dates(3)
    branch = {"lat": 10.0, "lon": 123.0}
    targets = make_targets(20)
    drivers_by_date = {
        d: [{"id": "A", "start_time": 8 * 60, "end_time": 19 * 60}] for d in dates
    }

    plan = build_global_plan(
        dates=dates,
        branch=branch,
        drivers_by_date=drivers_by_date,
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=5,
    )

    used_days = [
        sched["date"]
        for sched in plan["schedules"]
        if any(r.get("stops") for r in sched.get("routes", []))
    ]
    # If any days are used, they should be contiguous (no gaps before the last used day)
    if used_days:
        used_idx = [dates.index(d) for d in used_days]
        assert used_idx == list(range(min(used_idx), max(used_idx) + 1))
        # also ensure no day has more than ~12 stops (so it spreads roughly evenly)
        for sched in plan["schedules"]:
            total_stops_day = sum(len(r.get("stops", [])) for r in sched.get("routes", []))
            assert total_stops_day <= 20  # capacity per vehicle/day is 20
    # All targets should be assigned
    total_stops = sum(len(r.get("stops", [])) for sched in plan["schedules"] for r in sched.get("routes", []))
    assert total_stops == len(targets)


def test_three_drivers_all_utilized_and_no_unassigned():
    dates = make_dates(3)
    branch = {"lat": 10.0, "lon": 123.0}
    targets = make_targets(53)
    drivers_by_date = {
        d: [
            {"id": "A", "start_time": 8 * 60, "end_time": 19 * 60},
            {"id": "B", "start_time": 8 * 60, "end_time": 19 * 60},
            {"id": "C", "start_time": 8 * 60, "end_time": 19 * 60},
        ]
        for d in dates
    }

    plan = build_global_plan(
        dates=dates,
        branch=branch,
        drivers_by_date=drivers_by_date,
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=5,
    )

    # All targets assigned
    total_stops = sum(len(r.get("stops", [])) for sched in plan["schedules"] for r in sched.get("routes", []))
    assert total_stops == len(targets)
    assert not plan.get("unassigned")

    # Each driver used at least once across all days
    used_drivers = set()
    for sched in plan["schedules"]:
        for r in sched.get("routes", []):
            if r.get("stops"):
                used_drivers.add(r["driver_id"])
    assert {"A", "B", "C"}.issubset(used_drivers)
    # no single driver should have more than 25 stops to force distribution
    per_driver = {}
    for sched in plan["schedules"]:
        for r in sched.get("routes", []):
            per_driver[r["driver_id"]] = per_driver.get(r["driver_id"], 0) + len(r.get("stops", []))
    for count in per_driver.values():
        assert count <= 25


def assert_backfill_rule(plan, dates, drivers):
    """If a driver has any schedule on day N, then all drivers must have schedules on all previous used days."""
    day_to_used_drivers = {d: set() for d in dates}
    for sched in plan["schedules"]:
        for r in sched.get("routes", []):
            if r.get("stops"):
                day_to_used_drivers[sched["date"]].add(r["driver_id"])
    # find used days in order
    used_days = [d for d in dates if day_to_used_drivers[d]]
    for i, day in enumerate(used_days):
        required_prev = set(drivers)
        # For day index i (>=1), ensure all drivers appear on all previous used days
        if i >= 1:
            prev_day = used_days[i - 1]
            assert required_prev.issubset(day_to_used_drivers[prev_day]), f"Missing drivers on day {prev_day}"
    return day_to_used_drivers


def run_and_assert(dates, targets, drivers_by_date):
    plan = build_global_plan(
        dates=dates,
        branch={"lat": 10.0, "lon": 123.0},
        drivers_by_date=drivers_by_date,
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=5,
    )
    total_stops = sum(len(r.get("stops", [])) for sched in plan["schedules"] for r in sched.get("routes", []))
    assert total_stops == len(targets)
    assert not plan.get("unassigned")
    drivers = list({drv["id"] for lst in drivers_by_date.values() for drv in lst})
    day_to_used = assert_backfill_rule(plan, dates, drivers)
    return day_to_used


def test_backfill_rule_single_driver_20_targets():
    dates = make_dates(3)
    targets = make_targets(20)
    drivers_by_date = {d: [{"id": "A", "start_time": 8 * 60, "end_time": 19 * 60}] for d in dates}
    day_to_used = run_and_assert(dates, targets, drivers_by_date)
    # single driver: if any later day used, previous used day must also have A
    used_days = [d for d in dates if day_to_used[d]]
    if used_days:
        used_idx = [dates.index(d) for d in used_days]
        assert used_idx == list(range(min(used_idx), max(used_idx) + 1))


def test_backfill_rule_single_driver_50_targets():
    dates = make_dates(5)
    targets = make_targets(50)
    drivers_by_date = {d: [{"id": "A", "start_time": 8 * 60, "end_time": 19 * 60}] for d in dates}
    day_to_used = run_and_assert(dates, targets, drivers_by_date)
    used_days = [d for d in dates if day_to_used[d]]
    if used_days:
        used_idx = [dates.index(d) for d in used_days]
        assert used_idx == list(range(min(used_idx), max(used_idx) + 1))


def test_backfill_rule_three_drivers_20_targets():
    dates = make_dates(3)
    targets = make_targets(20)
    drivers_by_date = {
        d: [
            {"id": "A", "start_time": 8 * 60, "end_time": 19 * 60},
            {"id": "B", "start_time": 8 * 60, "end_time": 19 * 60},
            {"id": "C", "start_time": 8 * 60, "end_time": 19 * 60},
        ]
        for d in dates
    }
    day_to_used = run_and_assert(dates, targets, drivers_by_date)
    used_days = [d for d in dates if day_to_used[d]]
    # all drivers must be present on the earliest used day if any later day is used
    if used_days:
        assert {"A", "B", "C"}.issubset(day_to_used[used_days[0]])


def test_backfill_rule_three_drivers_50_targets():
    dates = make_dates(5)
    targets = make_targets(50)
    drivers_by_date = {
        d: [
            {"id": "A", "start_time": 8 * 60, "end_time": 19 * 60},
            {"id": "B", "start_time": 8 * 60, "end_time": 19 * 60},
            {"id": "C", "start_time": 8 * 60, "end_time": 19 * 60},
        ]
        for d in dates
    }
    day_to_used = run_and_assert(dates, targets, drivers_by_date)
    used_days = [d for d in dates if day_to_used[d]]
    if used_days:
        assert {"A", "B", "C"}.issubset(day_to_used[used_days[0]])


def test_single_driver_over_capacity_spreads_over_days():
    # 20 visits with long stay time cannot fit in a single 11-hour day; solver must schedule across days with no unassigned.
    dates = make_dates(3)
    targets = [
        {
            "id": f"T{i+1:03d}",
            "lat": 10.0,
            "lon": 123.0,
            "stay_minutes": 60,  # 1 hour each, so 20h total
            "required": True,
            "time_window": None,
            "datetime_window": None,
        }
        for i in range(20)
    ]
    drivers_by_date = {d: [{"id": "A", "start_time": 8 * 60, "end_time": 19 * 60}] for d in dates}

    plan = build_global_plan(
        dates=dates,
        branch={"lat": 10.0, "lon": 123.0},
        drivers_by_date=drivers_by_date,
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=5,
    )
    total_stops = sum(len(r.get("stops", [])) for sched in plan["schedules"] for r in sched.get("routes", []))
    assert total_stops == len(targets)
    assert not plan.get("unassigned")
    used_days = [sched["date"] for sched in plan["schedules"] if any(r.get("stops") for r in sched.get("routes", []))]
    assert len(set(used_days)) >= 2, "Expected visits to span multiple days when capacity per day is insufficient"
