import time
import math

from vrp.solver import build_global_plan
from vrp.geo import haversine_km, travel_time_minutes


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
        max_solve_seconds=1,
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
        max_solve_seconds=1,
    )
    assert plan["status"] == "success"
    sched = plan["schedules"][0]
    assert sched["routes"], "No routes created"
    route = sched["routes"][0]
    # Each stop should have non-zero travel, and total travel should be positive.
    assert all(s.get("travel_minutes", 0) > 0 for s in route["stops"])
    assert route.get("travel_minutes", 0) > 0


def test_optimizer_beats_greedy_total_travel_no_time_windows():
    """
    Without時間枠・必須100%の条件で、最適化結果の総移動時間が
    単純な逐次割当（ブランチ->targets順->ブランチ）より短いことを確認する。
    """
    dates = ["2025-11-23"]
    branch = {"lat": 10.0, "lon": 123.0}
    # 30件、規則的な配置で再現性を確保
    targets = []
    for i in range(30):
        lat = branch["lat"] + 0.2 * ((i % 10) - 5) / 10.0
        lon = branch["lon"] + 0.2 * ((i // 10) - 1) / 10.0
        targets.append(
            {
                "id": f"T{i+1:03d}",
                "lat": lat,
                "lon": lon,
                "stay_minutes": 10,
                "required": True,
                "time_window": None,
                "datetime_window": None,
            }
        )
    drivers_by_date = {dates[0]: [make_driver("A"), make_driver("B"), make_driver("C")]}

    plan = build_global_plan(
        dates=dates,
        branch=branch,
        drivers_by_date=drivers_by_date,
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=3,
    )
    assert plan["status"] == "success"
    # 総移動時間（return含む）
    opt_total = 0.0
    for sched in plan["schedules"]:
        for r in sched["routes"]:
            opt_total += r.get("travel_minutes", 0) + r.get("return_travel_minutes", 0)

    # ベースライン: targetsを順番に3等分して各ドライバーがブランチ->順番に巡回->ブランチに戻る
    def route_time(seq):
        if not seq:
            return 0.0
        total = 0.0
        prev = (branch["lat"], branch["lon"])
        for t in seq:
            total += math.ceil(travel_time_minutes(haversine_km(prev, (t["lat"], t["lon"])), 40.0))
            prev = (t["lat"], t["lon"])
        total += math.ceil(travel_time_minutes(haversine_km(prev, (branch["lat"], branch["lon"])), 40.0))
        return total

    chunk = len(targets) // 3
    baseline_total = (
        route_time(targets[:chunk])
        + route_time(targets[chunk : 2 * chunk])
        + route_time(targets[2 * chunk :])
    )

    # 最適化解は単純逐次ルートと同等以下であることを期待（同じ丸め方法で比較）
    assert opt_total <= baseline_total, f"optimized {opt_total:.1f} vs baseline {baseline_total:.1f}"


def test_single_driver_grid_is_significantly_better_than_naive_order():
    """
    1日・1人・時間枠なしでグリッド状に12件配置。
    単純なリスト順訪問（naive）より最適化解の総移動時間が十分短いことを確認。
    """
    dates = ["2025-11-23"]
    branch = {"lat": 10.0, "lon": 123.0}
    targets = []
    tid = 1
    for i in range(3):  # rows
        for j in range(4):  # cols
            targets.append(
                {
                    "id": f"T{tid:03d}",
                    "lat": branch["lat"] + 0.1 * i,
                    "lon": branch["lon"] + 0.1 * j,
                    "stay_minutes": 5,
                    "required": True,
                    "time_window": None,
                    "datetime_window": None,
                }
            )
            tid += 1
    drivers_by_date = {dates[0]: [make_driver("A")]}

    plan = build_global_plan(
        dates=dates,
        branch=branch,
        drivers_by_date=drivers_by_date,
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=1,
    )
    assert plan["status"] == "success"
    opt_total = 0.0
    for sched in plan["schedules"]:
        for r in sched["routes"]:
            opt_total += r.get("travel_minutes", 0) + r.get("return_travel_minutes", 0)

    # naive: ブランチ→生成順に巡回→ブランチ
    def route_time(seq):
        if not seq:
            return 0.0
        total = 0.0
        prev = (branch["lat"], branch["lon"])
        for t in seq:
            total += travel_time_minutes(haversine_km(prev, (t["lat"], t["lon"])), 40.0)
            prev = (t["lat"], t["lon"])
        total += travel_time_minutes(haversine_km(prev, (branch["lat"], branch["lon"])), 40.0)
        return total

    naive_total = route_time(targets)
    # 最適化がナイーブより十分短いことを期待（32%以上短縮）
    assert opt_total <= naive_total * 0.68, f"optimized {opt_total:.1f} vs naive {naive_total:.1f}"


def test_three_drivers_multi_day_beats_naive_random_routes():
    """
    3人・複数平日（5日）・53件（必須100%、時間枠なし）で、
    ランダム割当＋ランダム順巡回より総移動時間が50%以下であることを確認。
    """
    dates = [f"2025-11-{23 + i:02d}" for i in range(5)]
    branch = {"lat": 10.0, "lon": 123.0}
    targets = []
    for i in range(53):
        targets.append(
            {
                "id": f"T{i+1:03d}",
                "lat": branch["lat"] + 0.3 * (i % 10 - 5) / 10.0,
                "lon": branch["lon"] + 0.3 * (i // 10 - 2) / 10.0,
                "stay_minutes": 10,
                "required": True,
                "time_window": None,
                "datetime_window": None,
            }
        )
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
        max_solve_seconds=3,
    )
    assert plan["status"] == "success"
    opt_total = 0.0
    for sched in plan["schedules"]:
        for r in sched["routes"]:
            opt_total += r.get("travel_minutes", 0) + r.get("return_travel_minutes", 0)

    # ナイーブランダム: 日付ごとにランダムに均等割当し、各ドライバーがランダム順に巡回（ブランチ発着）
    import random

    random.seed(1234)
    def random_baseline():
        total = 0.0
        pool = targets.copy()
        random.shuffle(pool)
        per_day = len(pool) // len(dates)
        idx = 0
        for d in dates:
            day_targets = pool[idx : idx + per_day]
            idx += per_day
            random.shuffle(day_targets)
            for drv in ["A", "B", "C"]:
                if not day_targets:
                    continue
                chunk = max(1, len(day_targets) // 3)
                seq = day_targets[:chunk]
                day_targets = day_targets[chunk:]
                if not seq:
                    continue
                prev = (branch["lat"], branch["lon"])
                for t in seq:
                    total += travel_time_minutes(haversine_km(prev, (t["lat"], t["lon"])), 40.0)
                    prev = (t["lat"], t["lon"])
                total += travel_time_minutes(haversine_km(prev, (branch["lat"], branch["lon"])), 40.0)
        return total

    naive_total = random_baseline()
    # 最適化がランダムベースラインの50%以下であることを期待
    assert opt_total <= naive_total * 0.5, f"optimized {opt_total:.1f} vs naive {naive_total:.1f}"


def test_three_drivers_single_day_not_worse_than_single_driver_optimal():
    """
    3人・1日・時間枠なし・30件で、3人解の総移動時間が
    1人で全件を巡回する最適解（同じソルバーで計算）のおよそ1.3倍以内であることを確認。
    また、ターゲット重複割当がないことも確認する。
    """
    dates = ["2025-11-23"]
    branch = {"lat": 10.0, "lon": 123.0}
    targets = []
    tid = 1
    for i in range(5):  # rows
        for j in range(6):  # cols => 30 targets
            targets.append(
                {
                    "id": f"T{tid:03d}",
                    "lat": branch["lat"] + 0.15 * (i - 2),
                    "lon": branch["lon"] + 0.15 * (j - 3),
                    "stay_minutes": 5,
                    "required": True,
                    "time_window": None,
                    "datetime_window": None,
                }
            )
            tid += 1

    # Multi-driver plan (3 drivers, wide time windows)
    drivers_multi = [{"id": "A", "start_time": 0, "end_time": 24 * 60}, {"id": "B", "start_time": 0, "end_time": 24 * 60}, {"id": "C", "start_time": 0, "end_time": 24 * 60}]
    drivers_by_date_multi = {dates[0]: drivers_multi}
    plan_multi = build_global_plan(
        dates=dates,
        branch=branch,
        drivers_by_date=drivers_by_date_multi,
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=3,
    )
    assert plan_multi["status"] == "success"

    opt_total_multi = 0.0
    visited_ids = []
    for sched in plan_multi["schedules"]:
        for r in sched["routes"]:
            opt_total_multi += r.get("travel_minutes", 0) + r.get("return_travel_minutes", 0)
            visited_ids.extend([s["target_id"] for s in r.get("stops", [])])

    # No duplicate assignments
    assert len(visited_ids) == len(set(visited_ids)) == len(targets)

    # Single-driver optimal (same solver, long horizon)
    drivers_single = [{"id": "A", "start_time": 0, "end_time": 24 * 60}]
    plan_single = build_global_plan(
        dates=dates,
        branch=branch,
        drivers_by_date={dates[0]: drivers_single},
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=1,
    )
    assert plan_single["status"] == "success"
    opt_total_single = 0.0
    for sched in plan_single["schedules"]:
        for r in sched["routes"]:
            opt_total_single += r.get("travel_minutes", 0) + r.get("return_travel_minutes", 0)

    # 3人解は1人解の1.3倍以内であることを期待
    assert opt_total_multi <= opt_total_single * 1.3, f"multi {opt_total_multi:.1f} vs single {opt_total_single:.1f}"


def test_single_driver_multi_day_returns_vs_single_unconstrained():
    """
    1人・5営業日・30件（必須、時間枠なし）で、毎日拠点に戻る解の総移動時間が、
    時間制限なし・拠点に戻らない1日解の1.3倍以内であること。
    """
    dates = [f"2025-11-{23 + i:02d}" for i in range(5)]
    branch = {"lat": 10.0, "lon": 123.0}
    targets = []
    tid = 1
    for i in range(5):
        for j in range(6):
            targets.append(
                {
                    "id": f"T{tid:03d}",
                    "lat": branch["lat"] + 0.15 * (i - 2),
                    "lon": branch["lon"] + 0.15 * (j - 3),
                    "stay_minutes": 5,
                    "required": True,
                    "time_window": None,
                    "datetime_window": None,
                }
            )
            tid += 1

    # 複数日・毎日戻る制約
    drivers_by_date = {d: [{"id": "A", "start_time": 8 * 60, "end_time": 19 * 60}] for d in dates}
    plan_multi = build_global_plan(
        dates=dates,
        branch=branch,
        drivers_by_date=drivers_by_date,
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=3,
    )
    assert plan_multi["status"] == "success"
    opt_total_multi = 0.0
    for sched in plan_multi["schedules"]:
        for r in sched["routes"]:
            opt_total_multi += r.get("travel_minutes", 0) + r.get("return_travel_minutes", 0)
    visited_ids = [s["target_id"] for sched in plan_multi["schedules"] for r in sched["routes"] for s in r.get("stops", [])]
    assert len(visited_ids) == len(set(visited_ids)) == len(targets)

    # 1日・時間無制限・拠点に戻らない（長い勤務時間）ベースライン
    long_horizon = 5 * 24 * 60
    plan_single = build_global_plan(
        dates=[dates[0]],
        branch=branch,
        drivers_by_date={dates[0]: [{"id": "A", "start_time": 0, "end_time": long_horizon}]},
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=1,
    )
    assert plan_single["status"] == "success"
    opt_total_single = 0.0
    for sched in plan_single["schedules"]:
        for r in sched["routes"]:
            opt_total_single += r.get("travel_minutes", 0) + r.get("return_travel_minutes", 0)

    assert opt_total_multi <= opt_total_single * 1.3, f"multi-day {opt_total_multi:.1f} vs single-unconstrained {opt_total_single:.1f}"


def test_three_drivers_multi_day_vs_single_unconstrained():
    """
    3人・5営業日・100件（必須、時間枠なし）で、毎日拠点に戻る総移動時間が、
    1人・時間無制限・拠点に戻らない最適解の1.3倍以内であること。
    """
    dates = [f"2025-11-{23 + i:02d}" for i in range(5)]
    branch = {"lat": 10.0, "lon": 123.0}
    targets = []
    tid = 1
    for i in range(10):
        for j in range(10):
            if tid > 100:
                break
            targets.append(
                {
                    "id": f"T{tid:03d}",
                    "lat": branch["lat"] + 0.8 * (i - 5) / 10.0,
                    "lon": branch["lon"] + 0.8 * (j - 5) / 10.0,
                    "stay_minutes": 5,
                    "required": True,
                    "time_window": None,
                    "datetime_window": None,
                }
            )
            tid += 1
        if tid > 100:
            break

    drivers_by_date = {
        d: [
            {"id": "A", "start_time": 8 * 60, "end_time": 19 * 60},
            {"id": "B", "start_time": 8 * 60, "end_time": 19 * 60},
            {"id": "C", "start_time": 8 * 60, "end_time": 19 * 60},
        ]
        for d in dates
    }
    plan_multi = build_global_plan(
        dates=dates,
        branch=branch,
        drivers_by_date=drivers_by_date,
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=10,
    )
    assert plan_multi["status"] == "success"
    opt_total_multi = 0.0
    visited_ids = []
    for sched in plan_multi["schedules"]:
        for r in sched["routes"]:
            opt_total_multi += r.get("travel_minutes", 0) + r.get("return_travel_minutes", 0)
            visited_ids.extend([s["target_id"] for s in r.get("stops", [])])
    assert len(visited_ids) == len(set(visited_ids)) == len(targets)

    long_horizon = 5 * 24 * 60
    plan_single = build_global_plan(
        dates=[dates[0]],
        branch=branch,
        drivers_by_date={dates[0]: [{"id": "A", "start_time": 0, "end_time": long_horizon}]},
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=1,
    )
    assert plan_single["status"] == "success"
    opt_total_single = 0.0
    visited_single = []
    for sched in plan_single["schedules"]:
        for r in sched["routes"]:
            opt_total_single += r.get("travel_minutes", 0) + r.get("return_travel_minutes", 0)
            visited_single.extend([s["target_id"] for s in r.get("stops", [])])
    assert len(visited_single) == len(set(visited_single)) == len(targets)

    assert opt_total_multi <= opt_total_single * 1.3, f"multi {opt_total_multi:.1f} vs single {opt_total_single:.1f}"


def test_single_driver_multi_day_vs_unconstrained_100_targets():
    """
    1人・5営業日・100件（必須、時間枠なし、毎日戻る）で、総移動時間が
    1人・時間無制限・戻らない最適解の1.3倍以内であること。
    """
    dates = [f"2025-11-{23 + i:02d}" for i in range(5)]
    branch = {"lat": 10.0, "lon": 123.0}
    targets = []
    tid = 1
    for i in range(10):
        for j in range(10):
            targets.append(
                {
                    "id": f"T{tid:03d}",
                    "lat": branch["lat"] + 0.8 * (i - 5) / 10.0,
                    "lon": branch["lon"] + 0.8 * (j - 5) / 10.0,
                    "stay_minutes": 5,
                    "required": True,
                    "time_window": None,
                    "datetime_window": None,
                }
            )
            tid += 1

    multi = build_global_plan(
        dates=dates,
        branch=branch,
        drivers_by_date={d: [{"id": "A", "start_time": 8 * 60, "end_time": 19 * 60}] for d in dates},
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=5,
    )
    assert multi["status"] == "success"
    opt_multi = sum(r.get("travel_minutes", 0) + r.get("return_travel_minutes", 0) for sched in multi["schedules"] for r in sched["routes"])
    visited_multi = [s["target_id"] for sched in multi["schedules"] for r in sched["routes"] for s in r.get("stops", [])]
    assert len(visited_multi) == len(set(visited_multi)) == len(targets)

    unconstrained = build_global_plan(
        dates=[dates[0]],
        branch=branch,
        drivers_by_date={dates[0]: [{"id": "A", "start_time": 0, "end_time": 5 * 24 * 60}]},
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=1,
    )
    assert unconstrained["status"] == "success"
    opt_single = sum(r.get("travel_minutes", 0) + r.get("return_travel_minutes", 0) for sched in unconstrained["schedules"] for r in sched["routes"])
    visited_single = [s["target_id"] for sched in unconstrained["schedules"] for r in sched["routes"] for s in r.get("stops", [])]
    assert len(visited_single) == len(set(visited_single)) == len(targets)

    assert opt_multi <= opt_single * 1.3, f"multi-day single-driver {opt_multi:.1f} vs unconstrained {opt_single:.1f}"


def test_three_drivers_multi_day_vs_single_unconstrained_100_targets():
    """
    3人・5営業日・100件（必須、時間枠なし、毎日戻る）で、総移動時間が
    1人・時間無制限・戻らない最適解の1.3倍以内であること。
    """
    dates = [f"2025-11-{23 + i:02d}" for i in range(5)]
    branch = {"lat": 10.0, "lon": 123.0}
    targets = []
    tid = 1
    for i in range(10):
        for j in range(10):
            targets.append(
                {
                    "id": f"T{tid:03d}",
                    "lat": branch["lat"] + 0.8 * (i - 5) / 10.0,
                    "lon": branch["lon"] + 0.8 * (j - 5) / 10.0,
                    "stay_minutes": 5,
                    "required": True,
                    "time_window": None,
                    "datetime_window": None,
                }
            )
            tid += 1

    multi = build_global_plan(
        dates=dates,
        branch=branch,
        drivers_by_date={
            d: [
                {"id": "A", "start_time": 8 * 60, "end_time": 19 * 60},
                {"id": "B", "start_time": 8 * 60, "end_time": 19 * 60},
                {"id": "C", "start_time": 8 * 60, "end_time": 19 * 60},
            ]
            for d in dates
        },
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=10,
    )
    assert multi["status"] == "success"
    opt_multi = sum(r.get("travel_minutes", 0) + r.get("return_travel_minutes", 0) for sched in multi["schedules"] for r in sched["routes"])
    visited_multi = [s["target_id"] for sched in multi["schedules"] for r in sched["routes"] for s in r.get("stops", [])]
    assert len(visited_multi) == len(set(visited_multi)) == len(targets)

    unconstrained = build_global_plan(
        dates=[dates[0]],
        branch=branch,
        drivers_by_date={dates[0]: [{"id": "A", "start_time": 0, "end_time": 5 * 24 * 60}]},
        targets=targets,
        speed_kmph=40.0,
        max_solve_seconds=1,
    )
    assert unconstrained["status"] == "success"
    opt_single = sum(r.get("travel_minutes", 0) + r.get("return_travel_minutes", 0) for sched in unconstrained["schedules"] for r in sched["routes"])
    visited_single = [s["target_id"] for sched in unconstrained["schedules"] for r in sched["routes"] for s in r.get("stops", [])]
    assert len(visited_single) == len(set(visited_single)) == len(targets)

    assert opt_multi <= opt_single * 1.3, f"multi-day 3-drivers {opt_multi:.1f} vs unconstrained {opt_single:.1f}"
