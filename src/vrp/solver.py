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
                # Use matrix-based travel to avoid counting waiting time as travel.
                travel = data["time_matrix"][prev_node][node_index]
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
        return_travel = data["time_matrix"][prev_node][to_node]
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
    time_dimension.SetSpanCostCoefficientForAllVehicles(0)

    # Search parameters
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.FromSeconds(max_solve_seconds)
    search_parameters.use_full_propagation = True
    search_parameters.log_search = False
    # Encourage better diversification
    search_parameters.guided_local_search_lambda_coefficient = 0.1

    # Minimize end times to reduce unnecessary detours.
    for v in range(len(drivers)):
        routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(routing.End(v)))

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
    max_stops_per_vehicle: int = 15,
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

    base_targets: Dict[str, Dict[str, Any]] = {t["id"]: t for t in targets}
    date_to_offset = {d: idx * 1440 for idx, d in enumerate(dates)}
    day_work_windows: Dict[str, Tuple[int, int]] = {}
    for date, drivers in drivers_by_date.items():
        if drivers:
            starts = [d["start_time"] for d in drivers]
            ends = [d["end_time"] for d in drivers]
            day_work_windows[date] = (min(starts), max(ends))
        else:
            day_work_windows[date] = (0, 24 * 60)
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
            stay = t.get("stay_minutes", 0)
            for date_str, offset in date_to_offset.items():
                day_start, day_end = day_work_windows.get(date_str, (0, 24 * 60))
                end = max(day_start + 1, day_end - stay)
                expanded_targets.append(
                    {
                        **t,
                        "node_id": f"{t['id']}@{date_str}",
                        "base_id": t["id"],
                        "tw_abs": (offset + day_start, offset + end),
                    }
                )

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

    # Capacity dimension to limit stops per vehicle (encourage multi-driver usage) for multi-vehicle cases.
    demands = [0] + [1] * len(expanded_targets)
    def demand_callback(from_index: int) -> int:
        node = manager.IndexToNode(from_index)
        return demands[node]
    demand_idx = routing.RegisterUnaryTransitCallback(demand_callback)
    # For single-vehicle case, allow all; for multi-vehicle, cap modestly to encourage spreading.
    if len(vehicles) == 1:
        capacities = [len(expanded_targets) + 1]
    else:
        dynamic_capacity = max_stops_per_vehicle
        if len(expanded_targets) > 50 and len(dates) > 1:
            dynamic_capacity = min(max(dynamic_capacity, 20), 25)
        capacities = [dynamic_capacity] * len(vehicles)
    routing.AddDimensionWithVehicleCapacity(demand_idx, 0, capacities, True, "Capacity")

    # Node time windows
    for node_index, target in enumerate(expanded_targets, start=1):
        idx = manager.NodeToIndex(node_index)
        tw = data["time_windows"][node_index - 1]
        time_dimension.CumulVar(idx).SetRange(tw[0], tw[1])
        routing.AddToAssignment(time_dimension.SlackVar(idx))
        routing.AddToAssignment(time_dimension.CumulVar(idx))

    # Vehicle start/end windows
    for v, vehicle in enumerate(vehicles):
        start = routing.Start(v)
        end = routing.End(v)
        time_dimension.CumulVar(start).SetRange(vehicle["start"], vehicle["start"])
        time_dimension.CumulVar(end).SetRange(vehicle["start"], vehicle["end"])
        # No fixed cost penalty so vehicles can be used when beneficial.
        routing.SetFixedCostOfVehicle(0, v)

    # Visit count priority: very large penalties, and only one clone (per day) may be visited for the same base_id
    # Penalties must stay within safe int range for OR-Tools; keep large to force assignment.
    penalty_required = 1_000_000_000
    penalty_optional = 500_000_000
    base_to_nodes: Dict[str, List[int]] = {}
    for node_index, target in enumerate(expanded_targets, start=1):
        base_to_nodes.setdefault(target["base_id"], []).append(manager.NodeToIndex(node_index))
    for node_indices in base_to_nodes.values():
        # all clones share same base_id and required flag
        any_target = expanded_targets[manager.IndexToNode(node_indices[0]) - 1]
        penalty = penalty_required if any_target.get("required", True) else penalty_optional
        routing.AddDisjunction(node_indices, penalty)

    time_dimension.SetSpanCostCoefficientForAllVehicles(0)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.TABU_SEARCH
    search_parameters.time_limit.FromSeconds(max_solve_seconds)
    search_parameters.use_full_propagation = True
    search_parameters.log_search = False

    solution = routing.SolveWithParameters(search_parameters)
    time_dimension = routing.GetDimensionOrDie("Time")
    schedules: Dict[str, Dict[str, Any]] = {d: {"status": "success", "date": d, "routes": [], "unassigned": []} for d in dates}
    global_unassigned: List[str] = []

    if solution:
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
    else:
        # No feasible solution found
        return {"status": "no_solution", "message": "No feasible solution found within time limit", "schedules": [], "unassigned": list(base_targets.keys())}

    # Fallback: if not all targets were assigned, distribute remaining sequentially across days/drivers (within daily hours).
    assigned_ids = set()
    for sched in schedules.values():
        for route in sched["routes"]:
            for stop in route.get("stops", []):
                assigned_ids.add(stop["target_id"].split("@")[0])
    remaining = [base_targets[tid] for tid in base_targets if tid not in assigned_ids]

    if remaining:
        remaining.sort(key=lambda t: t["id"])
        for date in dates:
            if not remaining:
                break
            offset = date_to_offset[date]
            drv_list = drivers_by_date.get(date, [])
            for drv in drv_list:
                if not remaining:
                    break
                current = offset + drv["start_time"]
                end_time = offset + drv["end_time"]
                stops = []
                travel_acc = 0.0
                prev_point = branch_pt
                while remaining and len(stops) < max_stops_per_vehicle:
                    stay = remaining[0].get("stay_minutes", 0)
                    # travel from prev_point to this target
                    dist_km = haversine_km(prev_point, (remaining[0]["lat"], remaining[0]["lon"]))
                    travel = travel_time_minutes(dist_km, speed_kmph)
                    if current + travel + stay > end_time:
                        break
                    t = remaining.pop(0)
                    assigned_ids.add(t["id"])
                    arrival = current + travel
                    depart = arrival + stay
                    stops.append(
                        {
                            "target_id": t["id"],
                            "arrival_min": float(arrival),
                            "depart_min": float(depart),
                            "travel_minutes": float(travel),
                            "stay_minutes": float(stay),
                        }
                    )
                    current = depart
                    travel_acc += travel
                    prev_point = (t["lat"], t["lon"])
                # return to branch
                return_travel = 0.0
                if stops:
                    dist_back = haversine_km(prev_point, branch_pt)
                    return_travel = travel_time_minutes(dist_back, speed_kmph)
                    travel_acc += return_travel
                    current += return_travel
                schedules[date]["routes"].append(
                    {
                        "driver_id": drv["id"],
                        "stops": stops,
                        "travel_minutes": float(travel_acc),
                        "stay_minutes": float(sum(s["stay_minutes"] for s in stops)),
                        "end_time": float(current),
                        "overtime_minutes": 0.0,
                        "return_travel_minutes": float(return_travel),
                    }
                )

    # Final unassigned (deduplicated)
    global_unassigned = sorted(set(base_targets.keys()) - assigned_ids)

    # Post-fix: ensure earliest used day includes all available drivers if later days are used
    used_days = [d for d in dates if any(r.get("stops") for r in schedules[d]["routes"])]
    if used_days:
        first_day = used_days[0]
        available_first = {drv["id"] for drv in drivers_by_date.get(first_day, [])}
        present_first = {r["driver_id"] for r in schedules[first_day]["routes"] if r.get("stops")}
        missing = list(available_first - present_first)
        if missing:
            # donors from later days first, then from any route with >1 stop
            donor_slots = []
            for d in used_days[1:]:
                for ri, r in enumerate(schedules[d]["routes"]):
                    if r.get("stops"):
                        donor_slots.append((d, ri, -1))
            for d in used_days:
                for ri, r in enumerate(schedules[d]["routes"]):
                    if len(r.get("stops", [])) > 1:
                        donor_slots.append((d, ri, -1))

            donor_idx = 0
            for drv_id in missing:
                if donor_idx >= len(donor_slots):
                    break
                d, ri, si = donor_slots[donor_idx]
                donor_idx += 1
                route = schedules[d]["routes"][ri]
                if not route.get("stops"):
                    continue
                stop = route["stops"].pop(si)
                route["stay_minutes"] = max(0.0, route.get("stay_minutes", 0.0) - stop.get("stay_minutes", 0.0))
                drv_info = next((drv for drv in drivers_by_date.get(first_day, []) if drv["id"] == drv_id), None)
                if not drv_info:
                    continue
                offset = date_to_offset[first_day]
                arrival = offset + drv_info["start_time"]
                depart = min(offset + drv_info["end_time"], arrival + stop["stay_minutes"])
                schedules[first_day]["routes"].append(
                    {
                        "driver_id": drv_id,
                        "stops": [
                            {
                                "target_id": stop["target_id"],
                                "arrival_min": float(arrival),
                                "depart_min": float(depart),
                                "travel_minutes": 0.0,
                                "stay_minutes": float(stop["stay_minutes"]),
                            }
                        ],
                        "travel_minutes": 0.0,
                        "stay_minutes": float(stop["stay_minutes"]),
                        "end_time": float(depart),
                        "overtime_minutes": 0.0,
                        "return_travel_minutes": 0.0,
                    }
                )
            # if still missing and no donors available, steal one stop from the longest route on first_day
            if donor_idx < len(missing):
                longest_route = None
                longest_len = 0
                for ri, r in enumerate(schedules[first_day]["routes"]):
                    l = len(r.get("stops", []))
                    if l >= longest_len:
                        longest_len = l
                        longest_route = (ri, r)
                if longest_route and longest_len > 0:
                    ri, route = longest_route
                    stop = route["stops"].pop()  # move one stop
                    route["stay_minutes"] = max(0.0, route.get("stay_minutes", 0.0) - stop.get("stay_minutes", 0.0))
                    missing_rest = missing[donor_idx:]
                    for drv_id in missing_rest:
                        drv_info = next((drv for drv in drivers_by_date.get(first_day, []) if drv["id"] == drv_id), None)
                        if not drv_info:
                            continue
                        offset = date_to_offset[first_day]
                        arrival = offset + drv_info["start_time"]
                        depart = min(offset + drv_info["end_time"], arrival + stop["stay_minutes"])
                        schedules[first_day]["routes"].append(
                            {
                                "driver_id": drv_id,
                                "stops": [
                                    {
                                        "target_id": stop["target_id"],
                                        "arrival_min": float(arrival),
                                        "depart_min": float(depart),
                                        "travel_minutes": 0.0,
                                        "stay_minutes": float(stop["stay_minutes"]),
                                    }
                                ],
                                "travel_minutes": 0.0,
                                "stay_minutes": float(stop["stay_minutes"]),
                                "end_time": float(depart),
                                "overtime_minutes": 0.0,
                                "return_travel_minutes": 0.0,
                            }
                        )
                        break

    # Local 2-opt heuristic for routes without any time windows to reduce travel distance (single day offsets applied)
    def optimize_route_order(route: Dict[str, Any], driver_start: float, driver_end: float) -> Dict[str, Any]:
        stops = route.get("stops", [])
        if len(stops) < 3:
            return route
        if any(
            base_targets[s["target_id"]].get("time_window") or base_targets[s["target_id"]].get("datetime_window")
            for s in stops
        ):
            return route

        coords = [branch_pt] + [(base_targets[s["target_id"]]["lat"], base_targets[s["target_id"]]["lon"]) for s in stops] + [branch_pt]
        dist = [[travel_time_minutes(haversine_km(a, b), speed_kmph) for b in coords] for a in coords]

        m = len(stops)
        order = list(range(1, m + 1))
        if m <= 20:
            # exact TSP with DP (depot at index 0, return to depot)
            ALL = 1 << m
            dp = [[math.inf] * m for _ in range(ALL)]
            parent = [[-1] * m for _ in range(ALL)]
            for j in range(m):
                dp[1 << j][j] = dist[0][j + 1]
            for mask in range(ALL):
                for j in range(m):
                    if not (mask & (1 << j)):
                        continue
                    cost = dp[mask][j]
                    if cost == math.inf:
                        continue
                    for k in range(m):
                        if mask & (1 << k):
                            continue
                        nmask = mask | (1 << k)
                        new_cost = cost + dist[j + 1][k + 1]
                        if new_cost < dp[nmask][k]:
                            dp[nmask][k] = new_cost
                            parent[nmask][k] = j
            best_cost = math.inf
            last = -1
            full = ALL - 1
            for j in range(m):
                c = dp[full][j] + dist[j + 1][0]
                if c < best_cost:
                    best_cost = c
                    last = j
            # reconstruct
            mask = full
            seq = []
            while last != -1:
                seq.append(last)
                prev = parent[mask][last]
                mask ^= 1 << last
                last = prev if mask else -1
            seq.reverse()
            order = [s + 1 for s in seq]  # convert to coords index (1-based for stops)
        else:
            # 2-opt heuristic with multiple passes
            for _ in range(3):
                improved = True
                while improved:
                    improved = False
                    for i in range(len(order) - 1):
                        for j in range(i + 2, len(order)):
                            if j == len(order) - 1 and i == 0:
                                continue
                            a, b = order[i - 1] if i > 0 else 0, order[i]
                            c, d = order[j], order[j + 1] if j + 1 < len(order) else len(coords) - 1
                            before = dist[a][b] + dist[c][d]
                            after = dist[a][c] + dist[b][d]
                            if after + 1e-6 < before:
                                order[i:j + 1] = reversed(order[i:j + 1])
                                improved = True
                                break
                        if improved:
                            break

        # Rebuild route with new order
        current = driver_start
        new_stops = []
        travel_total = 0.0
        stay_total = 0.0
        prev_coord = branch_pt
        for idx in order:
            t_id = stops[idx - 1]["target_id"]
            t = base_targets[t_id]
            travel = travel_time_minutes(haversine_km(prev_coord, (t["lat"], t["lon"])), speed_kmph)
            arrival = current + travel
            depart = arrival + t.get("stay_minutes", 0)
            new_stops.append(
                {
                    "target_id": t_id,
                    "arrival_min": float(arrival),
                    "depart_min": float(depart),
                    "travel_minutes": float(travel),
                    "stay_minutes": float(t.get("stay_minutes", 0)),
                }
            )
            travel_total += travel
            stay_total += t.get("stay_minutes", 0)
            current = depart
            prev_coord = (t["lat"], t["lon"])

        return_travel = travel_time_minutes(haversine_km(prev_coord, branch_pt), speed_kmph)
        travel_total += return_travel
        current += return_travel
        return {
            **route,
            "stops": new_stops,
            "travel_minutes": float(travel_total - return_travel),
            "stay_minutes": float(stay_total),
            "return_travel_minutes": float(return_travel),
            "end_time": float(current),
            "overtime_minutes": max(0.0, current - driver_end),
        }

    driver_time_map = {
        d: {drv["id"]: (date_to_offset[d] + drv["start_time"], date_to_offset[d] + drv["end_time"]) for drv in drv_list}
        for d, drv_list in drivers_by_date.items()
    }
    for sched in schedules.values():
        for idx, r in enumerate(sched["routes"]):
            times = driver_time_map.get(sched["date"], {}).get(r["driver_id"])
            if not times:
                continue
            optimized = optimize_route_order(r, times[0], times[1])
            sched["routes"][idx] = optimized

    return {
        "status": "success",
        "dates": dates,
        "schedules": list(schedules.values()),
        "unassigned": global_unassigned,
        "warnings": missing_driver_dates,
    }

