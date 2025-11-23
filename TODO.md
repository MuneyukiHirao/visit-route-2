# TODO

## Backend / Solver
- [x] Set up project structure and dependency notes (Python + OR-Tools); document run modes (Haversine vs Google) and config defaults.
- [x] Implement data model + generators: branch + 100 Cebu points (reproducible seed), time windows/required flags, stay durations 30–90 minutes.
- [x] Implement solver wrapper: daily VRP with time windows, per-vehicle availability/holidays, start/end at branch, optional visits, max solve time, Haversine travel time with assumed speed, re-run after updates.
- [x] Output/reporting: coordinate tables, Google Maps/KML/GeoJSON hints, schedules per day/person with totals; sample runs for 1-driver and 3-driver cases (Dec 12–18 weekdays).

## Testing
- [x] Unit/property tests: data generation reproducibility, Haversine travel time vs assumed speed, time-window feasibility checks.
- [x] Scenario tests: 1-driver and 3-driver cases (Dec 12–18 weekdays) complete without violating time windows/required visits; respects holidays/availability.
- [x] Regression hooks: rerun after target updates; budgeted solver time (<=10s) honored.
- [x] UI test strategy: component/integration tests for tables and controls; map rendering/snapshot strategy (mock map provider); e2e happy path for scheduling + rerun. (Jest setup + basic DOM/fallback tests running)

## Demo UI
- [x] Design proposal: layout/flows, map + data presentation.
- [x] Review and adjust design based on feedback.
- [x] Implement frontend: trigger solver, visualize routes/results (map + tables), allow rerun after target updates.
- [x] Hook frontend to backend API; add offline/sample fallback; add status/error UI.
- [x] Add UI tests (component/snapshot) for table rendering and backend fallback.
- [x] Add filters (date/driver) and unassigned display with map fit; consider offline tile fallback behavior.
- [x] Fix start date default/override to always use today; ensure date input editable.
- [x] Fix mojibake in UI labels/headers (Japanese text).
- [x] Improve route arrows（arrow glyphで向きを描画）.
- [x] Add day-level toggles/layers to reduce clutter in All Days view.
- [x] Fix unassigned handling in global plan (avoid duplicating per day).
- [x] Handle missing drivers per date gracefully (skip or warn).
- [x] Optimize day assignment: allow cross-day swaps/relocate; increase solve time (e.g., 60s).
- [x] Tests/CI: stabilize npm/jest execution path (scripts/run_all_tests.ps1 added).
- [x] Pre-solve controls: target count selector (default 20), edit required/time window per target, show targets and map points before Solve.
- [x] Schedule display: use hh:mm 24h for arrival/depart.
