/**
 * Lightweight DOM tests for table rendering and status fallback.
 * Uses a minimal DOM to avoid loading external Leaflet assets.
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const sample = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "sample_data.json"), "utf8"));

const minimalHtml = `
<!doctype html><html><body>
  <div id="schedule"></div>
  <div id="coords"></div>
  <pre id="raw"></pre>
  <div id="dateToggles"></div>
  <button id="dateSelectAll"></button>
  <button id="dateSelectNone"></button>
  <div id="driverToggles"></div>
  <input id="speed" value="40" />
  <input id="targetCount" value="20" />
  <input id="startDate" type="date" value="2024-12-12" />
  <input id="singleDay" type="checkbox" />
  <input id="solveSeconds" value="1" />
  <button id="applyTargetCountBtn"></button>
  <button id="solveBtn"></button>
  <div id="status"></div>
  <input type="checkbox" id="labelsToggle" />
  <div id="spinnerOverlay"></div>
</body></html>`;

function buildDom() {
  const dom = new JSDOM(minimalHtml, { runScripts: "dangerously", resources: "usable", pretendToBeVisual: true });
  const { window } = dom;
  // Mock Leaflet
  const dummyMap = {
    setView: () => dummyMap,
    latLngToLayerPoint: () => ({ x: 0, y: 0 }),
    fitBounds: () => {},
    addLayer: () => {},
    removeLayer: () => {},
  };
  window.L = {
    map: () => dummyMap,
    tileLayer: () => ({ addTo: () => {} }),
    marker: () => ({ addTo: () => {}, bindPopup: () => ({ on: () => {} }), on: () => {}, bindTooltip: () => {}, setZIndexOffset: () => {} }),
    circleMarker: () => ({ addTo: () => {}, bindPopup: () => ({}) }),
    divIcon: () => ({}),
    polyline: () => ({ addTo: () => {} }),
    latLngBounds: () => ({}),
  };
  // Mock fetch
  const fetchMock = jest.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(sample) }));
  global.fetch = fetchMock;
  window.fetch = fetchMock;
  global.L = window.L;
  global.window = window;
  global.document = window.document;
  // Load app.js
  const appJs = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");
  window.eval(appJs);
  return window;
}

function makePlanWithWindows() {
  const targets = [
    { id: "A1", lat: 0, lon: 0, stay_minutes: 10, required: true, time_window: [480, 600] },
    { id: "A2", lat: 0, lon: 1, stay_minutes: 10, required: false, time_window: [600, 660] },
  ];
  return {
    targets,
    targets_by_id: Object.fromEntries(targets.map((t) => [t.id, t])),
    schedules: [
      {
        date: "2024-12-12",
        routes: [
          {
            driver_id: "A",
            stops: [
              { target_id: "A1", arrival_min: 500, depart_min: 510, travel_minutes: 20, stay_minutes: 10 },
              { target_id: "A2", arrival_min: 620, depart_min: 630, travel_minutes: 15, stay_minutes: 10 },
            ],
            travel_minutes: 35,
            stay_minutes: 20,
            end_time: 700,
            return_travel_minutes: 5,
          },
        ],
        unassigned: [],
      },
    ],
  };
}

test("renders schedule table rows for sample data (three_driver)", async () => {
  const window = buildDom();
  window.state.plan = sample.three_driver;
  window.state.plan.targets_by_id = sample.three_driver.targets_by_id;
  window.buildFilters(sample.three_driver);
  window.renderSchedule();
  const rows = window.document.querySelectorAll("#schedule tbody tr");
  expect(rows.length).toBeGreaterThan(0);
});

test("shows fallback status text when backend is unreachable", async () => {
  const window = buildDom();
  window.setStatus("Using local sample_data.json (backend unreachable)");
  const status = window.document.getElementById("status").textContent;
  expect(status).toContain("sample_data.json");
});

test("shows time window column and values when targets have time_window", () => {
  const window = buildDom();
  const plan = makePlanWithWindows();
  window.state.plan = plan;
  window.state.currentTargets = plan.targets;
  window.buildFilters(plan);
  window.renderSchedule();
  const cells = Array.from(window.document.querySelectorAll("#schedule tbody tr td:last-child")).map((el) => el.textContent);
  expect(cells).toContain("08:00-10:00");
  expect(cells).toContain("10:00-11:00");
});

test("renders travel/visit summaries", () => {
  const window = buildDom();
  const plan = makePlanWithWindows();
  window.state.plan = plan;
  window.state.currentTargets = plan.targets;
  window.buildFilters(plan);
  window.renderSchedule();
  const travelSummary = window.document.querySelector(".travel-summary").textContent;
  const visitSummary = window.document.querySelector(".visit-summary").textContent;
  expect(travelSummary).toContain("合計移動時間");
  expect(visitSummary).toContain("合計訪問数");
});

test("date filter hides other days", () => {
  const window = buildDom();
  const plan = makePlanWithWindows();
  plan.schedules.push({ date: "2024-12-13", routes: [], unassigned: [] });
  window.state.plan = plan;
  window.state.currentTargets = plan.targets;
  window.buildFilters(plan);
  const noneBtn = window.document.getElementById("dateSelectNone");
  noneBtn.click();
  window.renderSchedule();
  const rows = window.document.querySelectorAll("#schedule tbody tr");
  expect(rows.length).toBe(0);
});

test("driver filter hides other drivers", () => {
  const window = buildDom();
  const plan = makePlanWithWindows();
  // add another driver route to same day
  plan.schedules[0].routes.push({
    driver_id: "B",
    stops: [{ target_id: "A1", arrival_min: 550, depart_min: 560, travel_minutes: 10, stay_minutes: 10 }],
    travel_minutes: 10,
    stay_minutes: 10,
    end_time: 600,
    return_travel_minutes: 0,
  });
  window.state.plan = plan;
  window.state.currentTargets = plan.targets;
  window.buildFilters(plan);
  // uncheck driver B
  const bToggle = window.document.querySelector('input[data-driver="B"]');
  bToggle.checked = false;
  bToggle.dispatchEvent(new window.Event("change"));
  window.renderSchedule();
  const rows = Array.from(window.document.querySelectorAll("#schedule tbody tr")).filter((tr) =>
    tr.textContent.includes("B")
  );
  expect(rows.length).toBe(0);
});

test("applyTargetEditsFromTable updates currentTargets from coords table", () => {
  const window = buildDom();
  const plan = makePlanWithWindows();
  window.state.currentTargets = plan.targets.map((t) => ({ ...t }));
  window.renderCoords();
  // change stay and required and time_window
  const row = window.document.querySelector("#coords tbody tr");
  row.querySelector(".stay").value = "99";
  row.querySelector(".req").checked = false;
  row.querySelector(".tw-start").value = "07:30";
  row.querySelector(".tw-end").value = "08:30";
  window.applyTargetEditsFromTable();
  expect(window.state.currentTargets[0].stay_minutes).toBe(99);
  expect(window.state.currentTargets[0].required).toBe(false);
  expect(window.state.currentTargets[0].time_window).toEqual([450, 510]); // minutes
});

test("applyTargetCount limits number of currentTargets", () => {
  const window = buildDom();
  window.state.allTargets = Array.from({ length: 5 }, (_, i) => ({ id: `T${i}`, lat: 0, lon: 0, stay_minutes: 10 }));
  window.document.getElementById("targetCount").value = "2";
  window.applyTargetCount();
  expect(window.state.currentTargets.length).toBe(2);
});

test("calendar renders one column per driver per day", () => {
  const window = buildDom();
  window.state.plan = sample.three_driver;
  window.state.plan.targets_by_id = sample.three_driver.targets_by_id;
  window.buildFilters(sample.three_driver);
  window.state.scheduleView = "calendar";
  window.renderSchedule();
  const dayEls = Array.from(window.document.querySelectorAll(".cal-day"));
  expect(dayEls.length).toBeGreaterThan(0);
  dayEls.forEach((dayEl, idx) => {
    const cols = dayEl.querySelectorAll(".cal-driver-col");
    // unique drivers for that day
    const drivers = new Set(sample.three_driver.schedules[idx].routes.map((r) => r.driver_id));
    expect(cols.length).toBe(drivers.size);
  });
});

test("calendar groups multiple routes of the same driver into a single column", () => {
  const window = buildDom();
  const plan = {
    targets: [],
    targets_by_id: {},
    schedules: [
      {
        date: "2024-12-12",
        routes: [
          {
            driver_id: "A",
            stops: [{ target_id: "X1", arrival_min: 480, depart_min: 500, travel_minutes: 10, stay_minutes: 20 }],
            travel_minutes: 10,
            stay_minutes: 20,
            end_time: 500,
            return_travel_minutes: 5,
          },
          {
            driver_id: "A",
            stops: [{ target_id: "X2", arrival_min: 520, depart_min: 530, travel_minutes: 15, stay_minutes: 10 }],
            travel_minutes: 15,
            stay_minutes: 10,
            end_time: 530,
            return_travel_minutes: 5,
          },
          {
            driver_id: "B",
            stops: [{ target_id: "Y1", arrival_min: 600, depart_min: 610, travel_minutes: 12, stay_minutes: 10 }],
            travel_minutes: 12,
            stay_minutes: 10,
            end_time: 610,
            return_travel_minutes: 5,
          },
        ],
        unassigned: [],
      },
    ],
  };
  window.state.plan = plan;
  window.buildFilters(plan);
  window.state.scheduleView = "calendar";
  window.renderSchedule();
  const cols = window.document.querySelectorAll(".cal-day .cal-driver-col");
  const names = Array.from(window.document.querySelectorAll(".cal-driver-name")).map((el) => el.textContent.trim());
  expect(cols.length).toBe(2);
  expect(names).toEqual(["A", "B"]);
});
