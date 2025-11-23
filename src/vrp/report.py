"""
Reporting utilities for schedules and coordinate exports.
"""

from typing import Any, Dict, List


def format_schedule(schedule: Dict[str, Any]) -> str:
    """
    Render a human-readable schedule summary.
    """
    lines = []
    lines.append(f"Date: {schedule.get('date')}")
    for route in schedule.get("routes", []):
        lines.append(
            f"- Driver {route['driver_id']}: travel {route['travel_minutes']:.1f} min, stay {route['stay_minutes']:.1f} min, overtime {route.get('overtime_minutes',0):.1f} min"
        )
        for idx, stop in enumerate(route.get("stops", []), start=1):
            lines.append(
                f"  {idx}. {stop['target_id']} arrival {stop['arrival_min']:.1f} depart {stop['depart_min']:.1f} travel {stop['travel_minutes']:.1f} stay {stop['stay_minutes']}"
            )
    if schedule.get("unassigned"):
        lines.append(f"Unassigned: {schedule['unassigned']}")
    return "\n".join(lines)


def format_coordinates(branch: Dict[str, Any], targets: List[Dict[str, Any]], limit: int = 10) -> str:
    """
    Format coordinate table for branch and targets (preview limited to `limit` rows).
    """
    lines = []
    lines.append("Branch:")
    lines.append(f"  lat: {branch['lat']}, lon: {branch['lon']}")
    lines.append("")
    lines.append("Targets (preview):")
    lines.append("ID\tLat\tLon\tStay(min)\tRequired\tTimeWindow")
    for t in targets[:limit]:
        tw = t["time_window"]
        tw_str = f"{tw[0]}-{tw[1]} min" if tw else "-"
        lines.append(f"{t['id']}\t{t['lat']}\t{t['lon']}\t{t['stay_minutes']}\t{t['required']}\t{tw_str}")
    if len(targets) > limit:
        lines.append(f"... ({len(targets) - limit} more)")
    return "\n".join(lines)
