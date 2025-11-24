from vrp.solver import build_global_plan
from tests.test_solver_load_balance import make_dates

dates = make_dates(3)
targets = [{"id": f"T{i+1:03d}", "lat": 10.0, "lon": 123.0, "stay_minutes": 60, "required": True, "time_window": None, "datetime_window": None} for i in range(20)]
drivers_by_date = {d: [{"id": "A", "start_time": 8*60, "end_time": 19*60}] for d in dates}
plan = build_global_plan(dates=dates, branch={'lat':10,'lon':123}, drivers_by_date=drivers_by_date, targets=targets, speed_kmph=40.0, max_solve_seconds=30)
import json, pathlib
pathlib.Path('tmp_dbg.json').write_text(json.dumps(plan, indent=2))
