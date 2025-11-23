import datetime
import os
import sys
from typing import Any, Dict, List

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# Ensure src/ is on path when running as a script
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from vrp.data import generate_branch, generate_targets
from vrp.solver import build_global_plan

app = Flask(__name__, static_folder="../frontend", static_url_path="/")
CORS(app)


def _next_weekdays(start: datetime.date, n: int = 5) -> List[str]:
    dates: List[str] = []
    cursor = start
    # shift to weekday if weekend
    while cursor.weekday() >= 5:
        cursor += datetime.timedelta(days=1)
    while len(dates) < n:
        if cursor.weekday() < 5:
            dates.append(str(cursor))
        cursor += datetime.timedelta(days=1)
    return dates


def default_dates() -> List[str]:
    return _next_weekdays(datetime.date.today(), n=5)


def drivers_for_preset(preset: str) -> List[Dict[str, Any]]:
    if preset == "three":
        return [
            {"id": "A", "start_time": 8 * 60, "end_time": 19 * 60},
            {"id": "B", "start_time": 8 * 60, "end_time": 19 * 60},
            {"id": "C", "start_time": 8 * 60, "end_time": 19 * 60},
        ]
    return [{"id": "A", "start_time": 8 * 60, "end_time": 19 * 60}]


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/plan", methods=["POST"])
def api_plan():
    body = request.get_json(force=True, silent=True) or {}
    preset = body.get("preset", "three")
    speed_kmph = float(body.get("speed_kmph", 40.0))
    max_solve_seconds = int(body.get("max_solve_seconds", 60))
    dates = body.get("dates") or default_dates()

    branch = body.get("branch") or generate_branch(seed=123)
    # Accept targets from client; otherwise generate count (default 100 or provided) near branch within 30km
    target_count = int(body.get("target_count", 100))
    targets = body.get("targets") or generate_targets(
        seed=999,
        n=target_count,
        center=(branch["lat"], branch["lon"]),
        cluster_radius_km=30,
        dates=dates,
    )

    drivers_by_date = {}
    for d in dates:
        drivers_by_date[d] = body.get("drivers", drivers_for_preset(preset))

    plan = build_global_plan(
        dates=dates,
        branch=branch,
        drivers_by_date=drivers_by_date,
        targets=targets,
        speed_kmph=speed_kmph,
        max_solve_seconds=max_solve_seconds,
    )

    # attach branch/targets for map rendering convenience
    plan["branch"] = branch
    plan["targets"] = targets
    plan["targets_by_id"] = {
        t["id"]: {
            "lat": t["lat"],
            "lon": t["lon"],
            "stay_minutes": t["stay_minutes"],
            "time_window": t.get("time_window"),
            "datetime_window": t.get("datetime_window"),
            "required": t.get("required", False),
        }
        for t in targets
    }
    return jsonify(plan)


@app.route("/api/targets", methods=["GET"])
def api_targets():
    count = int(request.args.get("count", 100))
    branch = generate_branch(seed=123)
    start_str = request.args.get("start_date")
    if start_str:
        try:
            base = datetime.date.fromisoformat(start_str)
        except ValueError:
            base = datetime.date.today()
    else:
        base = datetime.date.today()
    dates = _next_weekdays(base, n=5)
    targets = generate_targets(seed=999, n=count, center=(branch["lat"], branch["lon"]), cluster_radius_km=30, dates=dates)
    return jsonify({"branch": branch, "targets": targets})


@app.route("/<path:path>")
def static_proxy(path):
    # serve other static assets (css/js/json)
    full_path = os.path.join(app.static_folder, path)
    if os.path.exists(full_path):
        return send_from_directory(app.static_folder, path)
    return "Not found", 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
