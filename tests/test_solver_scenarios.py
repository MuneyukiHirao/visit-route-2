from vrp.data import generate_branch, generate_targets
from vrp.solver import build_daily_plan


def test_one_driver_weekday_plan_runs():
    branch = generate_branch(seed=1)
    targets = generate_targets(seed=2, n=8)
    config = {
        "date": "2024-12-12",
        "drivers": [{"id": "A", "start_time": 8 * 60, "end_time": 19 * 60}],
        "branch": branch,
        "speed_kmph": 40.0,
        "max_solve_seconds": 10,
    }
    plan = build_daily_plan(config, targets)
    assert plan["status"] == "success"
    assert "routes" in plan
    assert plan["routes"][0]["driver_id"] == "A"


def test_three_driver_weekday_plan_runs():
    branch = generate_branch(seed=3)
    targets = generate_targets(seed=4, n=12)
    config = {
        "date": "2024-12-13",
        "drivers": [
            {"id": "A", "start_time": 8 * 60, "end_time": 19 * 60},
            {"id": "B", "start_time": 8 * 60, "end_time": 19 * 60},
            {"id": "C", "start_time": 8 * 60, "end_time": 19 * 60},
        ],
        "branch": branch,
        "speed_kmph": 40.0,
        "max_solve_seconds": 10,
    }
    plan = build_daily_plan(config, targets)
    assert plan["status"] == "success"
    assert len(plan["routes"]) == 3
    # Optional visits may be dropped; required should remain in route or reported unassigned
    required_ids = {t["id"] for t in targets if t["required"]}
    visited = {s["target_id"] for r in plan["routes"] for s in r["stops"]}
    unassigned = set(plan.get("unassigned", []))
    assert required_ids.issubset(visited.union(unassigned))
