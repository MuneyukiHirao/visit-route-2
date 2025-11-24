# VRP Route Planner (Frontend + Backend)

This project is a demo web app to build 1-week visit plans (VRP/VRPTW) with a Python/Flask backend and a Leaflet-based frontend. It optimizes required visits first, then maximizes visit count, then minimizes total travel time, while respecting time windows when provided.

## Features
- **Solver (OR-Tools VRPTW)**  
  - Priority: required targets → visit count max → travel time min.  
  - Time windows (date/time) strictly enforced when present; optional targets can be dropped with penalties.  
  - Multi-day, multi-driver: each day/driver is a vehicle with its own working hours.  
  - Fallback + local improvements: route-level TSP optimization (exact DP for small routes, 2-opt heuristic otherwise).
- **Data generation**  
  - Targets randomly generated inside Cebu island polygon, stay time randomized, required/time-window ratios configurable.  
  - Start date auto-shift to next weekday; 5 business-day range when multi-day.  
  - Time windows can be date-attached; rebase to chosen start date.
- **Frontend (Leaflet + vanilla JS)**  
  - Map with draggable targets, label always/hover toggle, colored routes with arrows, per-day/driver visibility toggles.  
  - Schedule view: list (time-window reference) and calendar (driver × day columns, work/full-day toggle).  
  - Target table: edit stay/required/time-window, clear all time windows, target count adjust, start-date shift.  
  - RAW JSON view; status and spinner for solve progress.  
  - All UI labels centralized in `frontend/labels.js` (for easy localization), bound via `data-label` in HTML.

## Setup
```bash
# Backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

## Run
```bash
# API server (Flask)
python scripts/api_server.py

# Frontend: open frontend/index.html (e.g., with VSCode Live Server)
```
- Default solver seconds = 1 (editable in UI).  
- Start date defaults to today; if weekend, shift to the next weekday; multi-day uses 5 business days.  
- `/api/targets?count=<n>&start_date=YYYY-MM-DD` to generate targets.

## Tests
```bash
# All (backend then frontend)
npm test

# Backend only
python -m pytest

# Frontend only
cd frontend && npm test
```
- Some regression/load-balance tests use large scenarios (up to 100 targets) and can take a couple of minutes.  
- Solver search time is capped by `max_solve_seconds` (typically 5–10 seconds in tests).

## Project Structure
- `src/vrp/` – solver, geo utilities, data generation  
- `scripts/api_server.py` – Flask API server  
- `frontend/` – UI code (Leaflet, vanilla JS), Jest tests, `labels.js` for centralized labels  
- `tests/` – Python tests (load-balance, regression, scenarios)

## Notes
- Network-restricted environments may block `git push` or npm registry access; run in an allowed environment.  
- Cache folders like `.pytest_cache` should be excluded from commits.  
- UI labels are managed in `frontend/labels.js`; HTML uses `data-label` to bind text.  
- Solver tuning: adjust `max_solve_seconds`, capacities, and search strategies in `src/vrp/solver.py` as needed for performance vs. quality. 
