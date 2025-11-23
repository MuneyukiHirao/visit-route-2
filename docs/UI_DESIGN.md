# Demo UI Design (VRP Scheduler)

## Goals
- Let users load/generate a weekly plan (1名/3名など) and visualize routes per day/driver.
- Show coordinates in a table and on a map; allow rerun after target updates.
- Keep it lightweight: static HTML/JS with Leaflet for map + simple tables.

## Layout
- Header: title + controls (date range selector, driver preset 1名/3名, speed km/h, solve button).
- Main split (desktop): left map, right tabs.
  - Map: Leaflet with markers for branch (star) and targets (required=red, optional=blue). Polylines per driver, toggle by driver checkbox.
  - Tabs: 
    1) Schedule table: date, driver, seq, target ID, arrival/ depart, travel, stay, daily totals.
    2) Coordinates: branch + target table (sortable).
    3) Logs/Config: raw JSON of plan, config summary.
- Mobile: stack vertically, map first, then tabs.

## Interaction flow
1) Load sample data (branch + targets) and pick preset (1 driver or 3 drivers).
2) Click “Solve” → call backend endpoint (or run local solver stub); show spinner and time budget.
3) Render map + tables; unassigned list shown per day.
4) Allow “Add target” (lat/lon/stay/time window/required) and rerun; new points appear on map/table.

## Visual design
- Color: neutral base, accent teal/amber (required red markers, optional blue).
- Typography: use “Inter”/“Noto Sans JP” via CDN (fallback: sans-serif).
- Motion: fade-in for map layers/table rows on update.

## Testing approach (UI)
- Component/integration: table rendering with sample_data.json; driver toggle filtering; unassigned list rendering.
- Snapshot: map layer list (mock Leaflet), table HTML.
- E2E (later): solve flow happy path with mocked backend response; add-target + rerun.

## Files (planned/added)
- `frontend/index.html` — static layout, pulls `style.css`, `app.js`.
- `frontend/style.css` — layout/responsive styles, color tokens.
- `frontend/app.js` — loads `sample_data.json`, renders map/tables, handles driver toggles.
- `frontend/sample_data.json` — small fixture (branch + 2 days plan for 1人/3人).
