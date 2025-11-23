"""
Solver wrapper for daily VRP with time windows and optional visits using OR-Tools.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from vrp.geo import haversine_km, travel_time_minutes


def _build_time_matrix(branch: Tuple[float, float], targets: List[Dict[str, Any]], speed_kmph: float) -> List[List[int]]:
    """
    Build travel time matrix (in minutes, int) including depot (index 0).
    """
    points = [branch] + [(t["lat"], t["lon"]) for t in targets]
    n = len(points)
    matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            dist_km = haversine_km(points[i], points[j])
            minutes = travel_time_minutes(dist_km, speed_kmph)
            matrix[i][j] = int(math.ceil(minutes))
    return matrix


def _time_window_for_target(target: Dict[str, Any], day_window: Tuple[int, int]) -> Tuple[int, int]:
    if target.get("time_window"):
        start, end = target["time_window"]
        # Ensure depart fits within window by subtracting service time.
        stay = target.get("stay_minutes", 0)
        adjusted_end = max(start + 1, end - stay)
        return (start, adjusted_end)
    return day_window


def _extract_routes(
    data: Dict[str, Any],
    manager: pywrapcp.RoutingIndexManager,
    routing: pywrapcp.RoutingModel,
    solution: pywrapcp.Assignment,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    time_dimension = routing.GetDimensionOrDie("Time")
    routes: List[Dict[str, Any]] = []
    unassigned: List[str] = []

    dropped_nodes = []
    for node in range(routing.Size()):
        if routing.IsStart(node) or routing.IsEnd(node):
            continue
        if solution.Value(routing.NextVar(node)) == node:
            dropped_nodes.append(node)

    for dn in dropped_nodes:
        idx = manager.IndexToNode(dn)
        # idx corresponds to targets list offset by 1 (0 is depot)
        target_id = data["targets"][idx - 1]["id"]
        unassigned.append(target_id)

    for vehicle_id, drv in enumerate(data["drivers"]):
        index = routing.Start(vehicle_id)
        stops = []
        total_travel = 0
        total_stay = 0
        prev_node = 0
        prev_depart_time = drv["start_time"]
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            if node_index != 0:
                target = data["targets"][node_index - 1]
                time_var = time_dimension.CumulVar(index)
                arrival = solution.Value(time_var)
                travel = max(0, arrival - prev_depart_time)  # includes travel + waiting from previous depart
                depart = arrival + target["stay_minutes"]
                stops.append(
                    {
                        "target_id": target["id"],
                        "arrival_min": float(arrival),
                        "depart_min": float(depart),
                        "travel_minutes": float(travel),
                        "stay_minutes": float(target["stay_minutes"]),
                    }
                )
                total_travel += travel
                total_stay += target["stay_minutes"]
                prev_node = node_index
                prev_depart_time = depart
            index = solution.Value(routing.NextVar(index))

        # Return leg travel time
        end_index = routing.End(vehicle_id)
        to_node = manager.IndexToNode(end_index)
        # Arrival at end and travel from last depart to end
        end_arrival = solution.Value(time_dimension.CumulVar(end_index))
        return_travel = max(0, end_arrival - prev_depart_time)
        total_travel += return_travel
        end_time = solution.Value(time_dimension.CumulVar(end_index))

        routes.append(
            {
                "driver_id": drv["id"],
                "stops": stops,
                "travel_minutes": float(total_travel),
                "stay_minutes": float(total_stay),
                "end_time": float(end_time),
                "overtime_minutes": max(0.0, end_time - drv["end_time"]),
                "return_travel_minutes": float(return_travel),
            }
        )

    return routes, unassigned


def build_daily_plan(config: Dict[str, Any], targets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build a plan for a given day and fleet using OR-Tools VRPTW with optional visits.
    """
    drivers = config.get("drivers", [])
    if not drivers:
        return {"status": "error", "message": "No drivers provided"}

    branch = (config["branch"]["lat"], config["branch"]["lon"])
    speed = float(config.get("speed_kmph", 40.0))
    max_solve_seconds = int(config.get("max_solve_seconds", 10))
    day_window = (
        min(d["start_time"] for d in drivers),
        max(d["end_time"] for d in drivers),
    )

    time_matrix = _build_time_matrix(branch, targets, speed)

    data = {
        "time_matrix": time_matrix,
        "time_windows": [_time_window_for_target(t, day_window) for t in targets],
        "targets": targets,
        "drivers": drivers,
        "service_times": [t["stay_minutes"] for t in targets],
    }

    manager = pywrapcp.RoutingIndexManager(len(time_matrix), len(drivers), [0] * len(drivers), [0] * len(drivers))
    routing = pywrapcp.RoutingModel(manager)

    def time_callback(from_index: int, to_index: int) -> int:
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)
        travel = data["time_matrix"][f][t]
        service = 0
        if f != 0:
            service = data["service_times"][f - 1]
        return travel + service

    def travel_only_callback(from_index: int, to_index: int) -> int:
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)
        return data["time_matrix"][f][t]

    transit_callback_index = routing.RegisterTransitCallback(time_callback)
    travel_cost_index = routing.RegisterTransitCallback(travel_only_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(travel_cost_index)

    # Add time dimension
    routing.AddDimension(
        transit_callback_index,
        24 * 60,  # allow waiting slack up to a day
        24 * 60,  # max horizon
        False,
        "Time",
    )
    time_dimension = routing.GetDimensionOrDie("Time")

    # Node time windows
    for node_index, target in enumerate(targets, start=1):
        idx = manager.NodeToIndex(node_index)
        tw = data["time_windows"][node_index - 1]
        time_dimension.CumulVar(idx).SetRange(tw[0], tw[1])
        # add service time
        routing.AddToAssignment(time_dimension.SlackVar(idx))
        routing.AddToAssignment(time_dimension.CumulVar(idx))

    # Vehicle start/end windows
    for v, drv in enumerate(drivers):
        start = routing.Start(v)
        end = routing.End(v)
        time_dimension.CumulVar(start).SetRange(drv["start_time"], drv["start_time"])
        time_dimension.CumulVar(end).SetRange(drv["start_time"], drv["end_time"])

    # Visits: penalty to allow dropping nodes while preferring required.
    # 目的関数の優先度: 訪問数最大化 > 距離最小化
    # ペナルティを非常に大きくして訪問数を最優先
    penalty_required = 10_000_000_000  # 必須は原則落とさない
    penalty_optional = 1_000_000_000   # 任意でも極力訪問
    for node_index, target in enumerate(targets, start=1):
        penalty = penalty_required if target.get("required", True) else penalty_optional
        routing.AddDisjunction([manager.NodeToIndex(node_index)], penalty)

    # Bias to keep routes within driver end.
    time_dimension.SetSpanCostCoefficientForAllVehicles(1)

    # Search parameters
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.SAVINGS
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.TABU_SEARCH
    search_parameters.time_limit.FromSeconds(max_solve_seconds)
    search_parameters.log_search = False

    solution = routing.SolveWithParameters(search_parameters)
    if solution:
        routes, unassigned = _extract_routes(data, manager, routing, solution)
        return {
            "status": "success",
            "date": config.get("date"),
            "routes": routes,
            "unassigned": unassigned,
        }
    return {"status": "no_solution", "message": "No feasible solution found within time limit"}


def build_global_plan(
    dates: List[str],
    branch: Dict[str, Any],
    drivers_by_date: Dict[str, List[Dict[str, Any]]],
    targets: List[Dict[str, Any]],
    speed_kmph: float = 40.0,
    max_solve_seconds: int = 60,
) -> Dict[str, Any]:
    """
    Solve across all dates at once: maximize visits (penalties) then minimize total travel.
    Each driver/day is a vehicle with its own start/end time offset by day*1440.
    Targets may have datetime_window: {"date": "YYYY-MM-DD", "start": "HH:MM", "end": "HH:MM"}.
    """
    if not dates:
        return {"status": "error", "message": "No dates provided"}

    # Build vehicle list with time offsets
    vehicles = []
    missing_driver_dates: List[str] = []
    for day_idx, date in enumerate(dates):
        drv_list = drivers_by_date.get(date, [])
        if not drv_list:
            missing_driver_dates.append(date)
            continue
        for drv in drv_list:
            vehicles.append(
                {
                    "id": drv["id"],
                    "date": date,
                    "day_idx": day_idx,
                    "start": day_idx * 1440 + drv["start_time"],
                    "end": day_idx * 1440 + drv["end_time"],
                }
            )
    if not vehicles:
        return {"status": "error", "message": "No drivers provided for given dates"}

    horizon = (len(dates) + 1) * 1440
    branch_pt = (branch["lat"], branch["lon"])

    date_to_offset = {d: idx * 1440 for idx, d in enumerate(dates)}
    # Expand targets per day when only time_window is provided (to enforce window on any chosen day)
    expanded_targets: List[Dict[str, Any]] = []
    for t in targets:
        dtw = t.get("datetime_window")
        if dtw and dtw.get("date") in date_to_offset:
            try:
                start_h, start_m = map(int, dtw["start"].split(":"))
                end_h, end_m = map(int, dtw["end"].split(":"))
                start = date_to_offset[dtw["date"]] + start_h * 60 + start_m
                end = date_to_offset[dtw["date"]] + end_h * 60 + end_m
                stay = t.get("stay_minutes", 0)
                end = max(start + 1, end - stay)
                expanded_targets.append({**t, "node_id": t["id"], "base_id": t["id"], "tw_abs": (start, end)})
                continue
            except Exception:
                pass
        if t.get("time_window"):
            start, end = t["time_window"]
            stay = t.get("stay_minutes", 0)
            end = max(start + 1, end - stay)
            for date_str, offset in date_to_offset.items():
                expanded_targets.append(
                    {**t, "node_id": f"{t['id']}@{date_str}", "base_id": t["id"], "tw_abs": (offset + start, offset + end)}
                )
        else:
            expanded_targets.append({**t, "node_id": t["id"], "base_id": t["id"], "tw_abs": (0, horizon)})

    time_matrix = _build_time_matrix(branch_pt, expanded_targets, speed_kmph)

    data = {
        "time_matrix": time_matrix,
        "time_windows": [t["tw_abs"] for t in expanded_targets],
        "targets": expanded_targets,
        "vehicles": vehicles,
        "service_times": [t["stay_minutes"] for t in expanded_targets],
    }

    manager = pywrapcp.RoutingIndexManager(len(time_matrix), len(vehicles), [0] * len(vehicles), [0] * len(vehicles))
    routing = pywrapcp.RoutingModel(manager)

    def time_callback(from_index: int, to_index: int) -> int:
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)
        travel = data["time_matrix"][f][t]
        service = 0
        if f != 0:
            service = data["service_times"][f - 1]
        return travel + service

    def travel_only_callback(from_index: int, to_index: int) -> int:
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)
        return data["time_matrix"][f][t]

    transit_callback_index = routing.RegisterTransitCallback(time_callback)
    travel_cost_index = routing.RegisterTransitCallback(travel_only_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(travel_cost_index)

    routing.AddDimension(
        transit_callback_index,
        24 * 60,  # waiting slack
        horizon,
        False,
        "Time",
    )
    time_dimension = routing.GetDimensionOrDie("Time")

    # Node time windows
    for node_index, target in enumerate(expanded_targets, start=1):
        idx = manager.NodeToIndex(node_index)
        tw = data["time_windows"][node_index - 1]
        time_dimension.CumulVar(idx).SetRange(tw[0], tw[1])
        routing.AddToAssignment(time_dimension.SlackVar(idx))
        routing.AddToAssignment(time_dimension.CumulVar(idx))

    # Vehicle start/end windows
    day_fixed_penalty = 5000  # penalize using later days to encourage early-day usage
    for v, vehicle in enumerate(vehicles):
        start = routing.Start(v)
        end = routing.End(v)
        time_dimension.CumulVar(start).SetRange(vehicle["start"], vehicle["start"])
        time_dimension.CumulVar(end).SetRange(vehicle["start"], vehicle["end"])
        routing.SetFixedCostOfVehicle(vehicle["day_idx"] * day_fixed_penalty, v)

    # Visit count priority: very large penalties, and only one clone (per day) may be visited for the same base_id
    penalty_required = 10_000_000_000
    penalty_optional = 1_000_000_000
    base_to_nodes: Dict[str, List[int]] = {}
    for node_index, target in enumerate(expanded_targets, start=1):
        base_to_nodes.setdefault(target["base_id"], []).append(manager.NodeToIndex(node_index))
    for node_indices in base_to_nodes.values():
        # all clones share same base_id and required flag
        any_target = expanded_targets[manager.IndexToNode(node_indices[0]) - 1]
        penalty = penalty_required if any_target.get("required", True) else penalty_optional
        routing.AddDisjunction(node_indices, penalty)

    time_dimension.SetSpanCostCoefficientForAllVehicles(1)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.SAVINGS
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.TABU_SEARCH
    search_parameters.time_limit.FromSeconds(max_solve_seconds)
    search_parameters.log_search = False

    solution = routing.SolveWithParameters(search_parameters)
    if not solution:
        return {"status": "no_solution", "message": "No feasible solution found within time limit"}

    time_dimension = routing.GetDimensionOrDie("Time")
    schedules: Dict[str, Dict[str, Any]] = {d: {"status": "success", "date": d, "routes": [], "unassigned": []} for d in dates}
    global_unassigned: List[str] = []

    dropped_nodes = []
    for node in range(routing.Size()):
        if routing.IsStart(node) or routing.IsEnd(node):
            continue
        if solution.Value(routing.NextVar(node)) == node:
            dropped_nodes.append(node)
    for dn in dropped_nodes:
        idx = manager.IndexToNode(dn)
        target_id = expanded_targets[idx - 1]["base_id"]
        global_unassigned.append(target_id)

    for vehicle_id, vehicle in enumerate(vehicles):
        index = routing.Start(vehicle_id)
        stops = []
        total_travel = 0
        total_stay = 0
        prev_depart = vehicle["start"]
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            if node_index != 0:
                target = expanded_targets[node_index - 1]
                time_var = time_dimension.CumulVar(index)
                arrival = solution.Value(time_var)
                travel = max(0, arrival - prev_depart)
                depart = arrival + target["stay_minutes"]
                stops.append(
                    {
                        "target_id": target["id"],
                        "arrival_min": float(arrival),
                        "depart_min": float(depart),
                        "travel_minutes": float(travel),
                        "stay_minutes": float(target["stay_minutes"]),
                    }
                )
                total_travel += travel
                total_stay += target["stay_minutes"]
                prev_depart = depart
            index = solution.Value(routing.NextVar(index))

        end_index = routing.End(vehicle_id)
        end_arrival = solution.Value(time_dimension.CumulVar(end_index))
        return_travel = max(0, end_arrival - prev_depart)
        total_travel += return_travel
        end_time = float(end_arrival)

        schedules[vehicle["date"]]["routes"].append(
            {
                "driver_id": vehicle["id"],
                "stops": stops,
                "travel_minutes": float(total_travel),
                "stay_minutes": float(total_stay),
                "end_time": end_time,
                "overtime_minutes": max(0.0, end_time - vehicle["end"]),
                "return_travel_minutes": float(return_travel),
            }
        )

    return {
        "status": "success",
        "dates": dates,
        "schedules": list(schedules.values()),
        "unassigned": global_unassigned,
        "warnings": missing_driver_dates,
    }
