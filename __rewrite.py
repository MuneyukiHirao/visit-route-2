from pathlib import Path
p = Path('src/vrp/solver.py')
t = p.read_text(encoding='utf-8')
marker = '    # Fallback:'
idx = t.find(marker)
if idx == -1:
    raise SystemExit('marker not found')
head = t[:idx]
new_tail = '''    # Fallback: if not all targets were assigned, distribute remaining sequentially across days/drivers (within daily hours).
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
                while remaining and len(stops) < max_stops_per_vehicle:
                    stay = remaining[0].get("stay_minutes", 0)
                    if current + stay > end_time:
                        break
                    t = remaining.pop(0)
                    assigned_ids.add(t["id"])
                    arrival = current
                    depart = arrival + stay
                    stops.append(
                        {
                            "target_id": t["id"],
                            "arrival_min": float(arrival),
                            "depart_min": float(depart),
                            "travel_minutes": 0.0,
                            "stay_minutes": float(stay),
                        }
                    )
                    current = depart
                schedules[date]["routes"].append(
                    {
                        "driver_id": drv["id"],
                        "stops": stops,
                        "travel_minutes": 0.0,
                        "stay_minutes": float(sum(s["stay_minutes"] for s in stops)),
                        "end_time": float(current),
                        "overtime_minutes": 0.0,
                        "return_travel_minutes": 0.0,
                    }
                )

    # Final unassigned (deduplicated)
    global_unassigned = sorted(set(base_targets.keys()) - assigned_ids)

    # Post-fix: ensure earliest used day includes all available drivers if later days are used
    used_days = [d for d in dates if any(r.get("stops") for r in schedules[d]["routes"])]
    if len(used_days) >= 2:
        first_day = used_days[0]
        later_days = used_days[1:]
        available_first = {drv["id"] for drv in drivers_by_date.get(first_day, [])}
        present_first = {r["driver_id"] for r in schedules[first_day]["routes"] if r.get("stops")}
        missing = list(available_first - present_first)
        if missing:
            donor_routes = []
            for d in later_days:
                for ri, r in enumerate(schedules[d]["routes"]):
                    if r.get("stops"):
                        donor_routes.append((d, ri))
            for ri, r in enumerate(schedules[first_day]["routes"]):
                if len(r.get("stops", [])) > 1:
                    donor_routes.append((first_day, ri))

            donor_idx = 0
            for drv_id in missing:
                while donor_idx < len(donor_routes):
                    d, ri = donor_routes[donor_idx]
                    donor_idx += 1
                    route = schedules[d]["routes"][ri]
                    if not route.get("stops"):
                        continue
                    stop = route["stops"].pop()
                    route["stay_minutes"] = max(0.0, route.get("stay_minutes", 0.0) - stop["stay_minutes"])
                    drv_info = next((drv for drv in drivers_by_date.get(first_day, []) if drv["id"] == drv_id), None)
                    if not drv_info:
                        break
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

    return {
        "status": "success",
        "dates": dates,
        "schedules": list(schedules.values()),
        "unassigned": global_unassigned,
        "warnings": missing_driver_dates,
    }
'''
p.write_text(head + new_tail, encoding='utf-8')
print('rewritten tail applied')
