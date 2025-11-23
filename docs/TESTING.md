# Testing Strategy

## Scope
- Backend: data generation, geospatial utilities, solver constraints (time windows, optional visits, driver availability, daily return to branch), reporting.
- UI: map/table rendering, controls for solver runs, rerun after updates.

## Tools
- `pytest` for unit/property/scenario tests.
- Optional: `hypothesis` for property-based checks (can be added later).
- UI: prefer component/integration tests with a mock map provider (e.g., stub Leaflet/Mapbox/Google wrapper) and table snapshots; E2E with Playwright/Cypress later.

## Backend Tests (current TODO)
- Data generation reproducibility with fixed seed, Cebu bounds, stay duration range.
- Haversine distance/time conversion correctness.
- Scenario tests for 1-driver / 3-driver weekday plans (Dec 12–18 weekdays); honor time windows, required visits, holidays, driver unavailability; solver time budget respected.

## UI Tests (planned)
- Component tests: table rendering of schedules, totals, and per-driver summaries; controls to trigger runs and reruns.
- Map rendering: snapshot or DOM assertions using mocked map provider and fixture GeoJSON/KML data.
- Integration/E2E: happy path for running solver with test fixtures, viewing routes, and rerunning after adding a target.

## Budget/Performance
- Default solver time cap: 10s per run. Tests should fail fast on overruns.

## Fixtures
- Reproducible Cebu dataset (seeded branch + 100 targets) stored/generated via helper functions; reused across backend and UI tests.
