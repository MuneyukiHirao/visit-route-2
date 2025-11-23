//marker
/* eslint-disable no-undef */
const state = {
  branch: null,
  allTargets: [],
  currentTargets: [],
  plan: null,
  filterDate: "ALL",
  driverFilter: new Set(),
  showLabelsAlways: false,
};

let map;
let layers = [];
let tileLayer;
let markerById = new Map();
let arrows = [];

const driverColors = ["#ef4444", "#3b82f6", "#f59e0b"];
const dateColors = ["#14b8a6", "#f59e0b", "#a855f7", "#ec4899", "#06b6d4", "#84cc16", "#eab308"];
const dateVisibility = {};

function setStartDateToday() {
  const startInput = document.getElementById("startDate");
  if (startInput) {
    const today = new Date();
    const iso = today.toISOString().slice(0, 10);
    startInput.value = iso;
  }
}

function minutesToHHMM(mins) {
  if (mins == null || Number.isNaN(mins)) return "-";
  const h = Math.floor(mins / 60) % 24;
  const m = Math.round(mins % 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function hhmmToMinutes(val) {
  if (!val) return null;
  const parts = val.split(":");
  if (parts.length !== 2) return null;
  const h = parseInt(parts[0], 10);
  const m = parseInt(parts[1], 10);
  if (Number.isNaN(h) || Number.isNaN(m)) return null;
  return h * 60 + m;
}

function rebaseTargetWindows(startDateStr) {
  if (!startDateStr) return;
  const baseNew = new Date(startDateStr);
  if (Number.isNaN(baseNew.getTime())) return;
  // find earliest datetime_window among current targets
  const dates = state.currentTargets
    .map((t) => t.datetime_window?.date)
    .filter(Boolean)
    .map((d) => new Date(d));
  if (!dates.length) return;
  const baseOld = dates.reduce((min, d) => (d < min ? d : min), dates[0]);
  const deltaDays = Math.round((baseNew - baseOld) / (1000 * 60 * 60 * 24));
  state.currentTargets = state.currentTargets.map((t) => {
    if (t.datetime_window?.date) {
      const oldDate = new Date(t.datetime_window.date);
      if (!Number.isNaN(oldDate.getTime())) {
        const shifted = new Date(oldDate);
        shifted.setDate(oldDate.getDate() + deltaDays);
        t.datetime_window = {
          ...t.datetime_window,
          date: shifted.toISOString().slice(0, 10),
        };
      }
    }
    return t;
  });
}

function setStatus(text) {
  const el = document.getElementById("status");
  if (el) el.textContent = text;
}

function setLoading(isLoading) {
  const overlay = document.getElementById("spinnerOverlay");
  const btn = document.getElementById("solveBtn");
  if (overlay) overlay.classList.toggle("active", isLoading);
  if (btn) btn.disabled = isLoading;
}

function clearLayers() {
  layers.forEach((l) => map.removeLayer(l));
  layers = [];
  arrows.forEach((a) => map.removeLayer(a));
  arrows = [];
}

function renderMap() {
  if (!state.branch) return;
  markerById.clear();
  if (!map) {
    map = L.map("map").setView([state.branch.lat, state.branch.lon], 9);
    tileLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: "© OpenStreetMap",
      errorTileUrl:
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAukB9X7FKXwAAAAASUVORK5CYII=",
    });
    tileLayer.addTo(map);
  }
  clearLayers();
  const branchMarker = L.marker([state.branch.lat, state.branch.lon], { title: "Branch" }).addTo(map);
  layers.push(branchMarker);

  const dateColorMap = {};
  if (state.plan) {
    state.plan.schedules.forEach((d, idx) => {
      dateColorMap[d.date] = dateColors[idx % dateColors.length];
      if (dateVisibility[d.date] === undefined) dateVisibility[d.date] = true;
    });
  }

  state.currentTargets.forEach((t) => {
    const icon = L.divIcon({
      className: t.required ? "target-marker req" : "target-marker opt",
      iconSize: [12, 12],
    });
    const m = L.marker([t.lat, t.lon], {
      icon,
      draggable: true,
      title: t.id,
    }).bindPopup(`${t.id} (stay ${t.stay_minutes}m)`);
    m.on("dragend", (evt) => {
      const pos = evt.target.getLatLng();
      t.lat = Number(pos.lat.toFixed(6));
      t.lon = Number(pos.lng.toFixed(6));
      updateCoordRow(t.id, t.lat, t.lon);
    });
    m.bindTooltip(`${t.id}${t.required ? " (必須)" : ""}`, {
      permanent: state.showLabelsAlways,
      direction: "top",
      className: "leaflet-label",
    });
    m.on("click", () => highlightFromMap(t.id));
    m.addTo(map);
    layers.push(m);
    markerById.set(t.id, m);
  });

  if (state.plan) {
    const filteredSchedules =
      state.filterDate === "ALL"
        ? state.plan.schedules
        : state.plan.schedules.filter((d) => d.date === state.filterDate);
    filteredSchedules.forEach((day, dayIdx) => {
      if (state.filterDate === "ALL" && dateVisibility[day.date] === false) return;
      const dayColor = state.filterDate === "ALL" ? dateColorMap[day.date] : dateColors[dayIdx % dateColors.length];
      day.routes.forEach((route) => {
        if (!state.driverFilter.has(route.driver_id)) return;
        if (!route.stops || route.stops.length === 0) return;
        const points = [[state.branch.lat, state.branch.lon]];
        route.stops.forEach((s) => {
          const t = state.plan.targets_by_id[s.target_id];
          points.push([t.lat, t.lon]);
        });
        points.push([state.branch.lat, state.branch.lon]);
        const line = L.polyline(points, {
          color: dayColor,
          weight: 3,
          opacity: 0.7,
        });
        line.addTo(map);
        layers.push(line);
        addArrows(points, dayColor);
        const bounds = L.latLngBounds(points);
        map.fitBounds(bounds, { padding: [40, 40] });
      });
    });
  }
}

function findTargetById(id) {
  const fromCurrent = (state.currentTargets || []).find((t) => t.id === id);
  const fromPlanById = state.plan?.targets_by_id?.[id];
  const fromPlanList = (state.plan?.targets || []).find((t) => t.id === id);
  const base = fromPlanById || fromPlanList || fromCurrent;
  if (!base) return undefined;
  if (!fromCurrent) return base;
  // 優先して currentTargets の time_window を使う（計算前の指定を保持するため）
  return {
    ...base,
    ...fromCurrent,
    time_window: fromCurrent.time_window || base.time_window,
  };
}

function formatWindow(target) {
  if (!target) return "-";
  if (target.datetime_window) {
    const dw = target.datetime_window;
    return `${dw.date} ${dw.start}-${dw.end}`;
  }
  if (target.time_window && target.time_window.length === 2) {
    return `${minutesToHHMM(target.time_window[0])}-${minutesToHHMM(target.time_window[1])}`;
  }
  return "-";
}

function renderSchedule() {
  const container = document.getElementById("schedule");
  if (!container || !state.plan) return;
  const filteredSchedules = state.plan.schedules.filter((d) => dateVisibility[d.date] !== false);

  const days = filteredSchedules
    .map((d) => {
      const rows = d.routes
        .map((r) => {
          if (!state.driverFilter.has(r.driver_id)) return "";
          if (!r.stops || r.stops.length === 0) return "";
          const stopRows = r.stops
            .map((s, i) => {
              const t = findTargetById(s.target_id);
              const tw = formatWindow(t);
              return `<tr data-target="${s.target_id}">
        <td>${d.date}</td><td>${r.driver_id}</td><td>${i + 1}</td><td>${s.target_id}</td>
        <td>${minutesToHHMM(s.arrival_min)}</td><td>${minutesToHHMM(s.depart_min)}</td>
        <td>${s.travel_minutes.toFixed(1)}</td><td>${s.stay_minutes.toFixed(1)}</td><td>${tw}</td>
      </tr>`;
            })
            .join("");
          const returnRow = `<tr class="return-row">
        <td>${d.date}</td><td>${r.driver_id}</td><td>-</td><td>Return</td>
        <td>${minutesToHHMM(r.end_time)}</td><td>-</td><td>${(r.return_travel_minutes || 0).toFixed(1)}</td><td>0</td><td>-</td>
      </tr>`;
          return stopRows + returnRow;
        })
        .join("");
      return rows;
    })
    .join("");

  container.innerHTML = `<table>
    <thead><tr><th>Date</th><th>Driver</th><th>Seq</th><th>Target</th><th>Arrival</th><th>Departure</th><th>Travel</th><th>Stay</th><th>Time Window</th></tr></thead>
    <tbody>${days}</tbody>
  </table>`;

  const allUnassigned = filteredSchedules.flatMap((d) => d.unassigned || []);
  if (allUnassigned.length) {
    container.innerHTML += `<div class="unassigned">Unassigned: ${allUnassigned.join(", ")}</div>`;
  }

  const totalTravelMinutes = filteredSchedules.reduce(
    (accDay, d) =>
      accDay +
      d.routes.reduce((accRoute, r) => accRoute + (r.travel_minutes || 0) + (r.return_travel_minutes || 0), 0),
    0
  );
  const driverTravelTotals = filteredSchedules.reduce((acc, d) => {
    d.routes.forEach((r) => {
      const dist = (r.travel_minutes || 0) + (r.return_travel_minutes || 0);
      acc[r.driver_id] = (acc[r.driver_id] || 0) + dist;
    });
    return acc;
  }, {});
  const travelSummary = Object.entries(driverTravelTotals)
    .map(([id, m]) => `${id}: ${m.toFixed(1)}分`)
    .join(" / ");
  container.innerHTML += `<div class="travel-summary">合計移動時間: ${totalTravelMinutes.toFixed(1)}分${travelSummary ? `（${travelSummary}）` : ""}</div>`;

  const totalVisits = filteredSchedules.reduce(
    (acc, d) => acc + d.routes.reduce((accR, r) => accR + (r.stops?.length || 0), 0),
    0
  );
  const driverVisits = filteredSchedules.reduce((acc, d) => {
    d.routes.forEach((r) => {
      acc[r.driver_id] = (acc[r.driver_id] || 0) + (r.stops?.length || 0);
    });
    return acc;
  }, {});
  const visitSummary = Object.entries(driverVisits)
    .map(([id, n]) => `${id}: ${n}件`)
    .join(" / ");
  container.innerHTML += `<div class="visit-summary">合計訪問数: ${totalVisits}件${visitSummary ? `（${visitSummary}）` : ""}</div>`;
}

function renderCoords() {
  const container = document.getElementById("coords");
  if (!container) return;
  const clearBtn = `<button id="clearTimeWindows" class="chip-btn small">時間枠クリア</button>`;
  const rows = state.currentTargets.map((t, idx) => `<tr data-id="${t.id}">
    <td>${t.id}</td><td class="lat">${t.lat}</td><td class="lon">${t.lon}</td>
    <td><input type="number" class="stay" value="${t.stay_minutes}" min="1" max="240" /></td>
    <td><input type="checkbox" class="req" ${t.required ? "checked" : ""}></td>
    <td>
      <div class="tw-inline">
        <input type="time" class="tw-start" value="${t.time_window ? minutesToHHMM(t.time_window[0]) : ""}" />
        <span class="tw-sep">-</span>
        <input type="time" class="tw-end" value="${t.time_window ? minutesToHHMM(t.time_window[1]) : ""}" />
        <span class="tw-date">${t.datetime_window ? t.datetime_window.date : ""}</span>
      </div>
    </td>
  </tr>`).join("");
  container.innerHTML = `${clearBtn}<table>
    <thead><tr><th>ID</th><th>Lat</th><th>Lon</th><th>滞在</th><th>必須</th><th>時間枠（日付付き）</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
  const clearTwBtn = container.querySelector("#clearTimeWindows");
  if (clearTwBtn) {
    clearTwBtn.addEventListener("click", () => {
      state.currentTargets = state.currentTargets.map((t) => ({
        ...t,
        time_window: null,
        datetime_window: null,
      }));
      renderCoords();
      setStatus("時間枠をクリアしました");
    });
  }
}


function renderRaw() {
  const raw = document.getElementById("raw");
  if (!raw) return;
  raw.textContent = state.plan ? JSON.stringify(state.plan, null, 2) : "No plan yet";
}

function buildFilters(plan) {
  const dateToggleWrap = document.getElementById("dateToggles");
  if (dateToggleWrap) {
    dateToggleWrap.innerHTML = plan.schedules
      .map((d) => `<label class="driver-chip"><input type="checkbox" data-date="${d.date}" ${dateVisibility[d.date] !== false ? "checked" : ""}/> ${d.date}</label>`)
      .join("");
    const dateCbs = Array.from(dateToggleWrap.querySelectorAll("input[type=checkbox]"));
    const syncCb = () => {
      dateCbs.forEach((cb) => {
        const d = cb.dataset.date;
        cb.checked = dateVisibility[d] !== false;
      });
    };
    dateCbs.forEach((cb) => {
      cb.onchange = () => {
        dateVisibility[cb.dataset.date] = cb.checked;
        rerender();
      };
    });
    const setAllDates = (value) => {
      plan.schedules.forEach((d) => {
        dateVisibility[d.date] = value;
      });
      syncCb();
      rerender();
    };
    const btnAll = document.getElementById("dateSelectAll");
    const btnNone = document.getElementById("dateSelectNone");
    if (btnAll) btnAll.onclick = () => setAllDates(true);
    if (btnNone) btnNone.onclick = () => setAllDates(false);
    syncCb();
  }

  const driverIds = Array.from(new Set(plan.schedules.flatMap((d) => d.routes.map((r) => r.driver_id))));
  state.driverFilter = new Set(driverIds);
  const wrap = document.getElementById("driverToggles");
  wrap.innerHTML = driverIds
    .map((id) => `<label class="driver-chip"><input type="checkbox" data-driver="${id}" checked />${id}</label>`)
    .join("");
  wrap.querySelectorAll("input[type=checkbox]").forEach((cb) => {
    cb.onchange = () => {
      const id = cb.dataset.driver;
      if (cb.checked) state.driverFilter.add(id);
      else state.driverFilter.delete(id);
      rerender();
    };
  });
}

function applyTargetCount() {
  const input = document.getElementById("targetCount");
  const total = Array.isArray(state.allTargets) ? state.allTargets.length : 0;
  if (total === 0) {
    state.currentTargets = [];
    renderCoords();
    renderMap();
    setStatus("Targets: 0");
    return;
  }
  const n = Math.max(1, Math.min(parseInt(input.value, 10) || 20, total));
  state.currentTargets = state.allTargets.slice(0, n).map((t) => ({ ...t }));
  renderCoords();
  renderMap();
  setStatus(`Targets: ${n} (from ${total})`);
}

function applyTargetEditsFromTable() {
  const rows = document.querySelectorAll("#coords tbody tr");
  rows.forEach((row, idx) => {
    const req = row.querySelector(".req").checked;
    const stay = parseInt(row.querySelector(".stay").value, 10) || state.currentTargets[idx].stay_minutes;
    const twStart = row.querySelector(".tw-start").value;
    const twEnd = row.querySelector(".tw-end").value;
    const startMin = hhmmToMinutes(twStart);
    const endMin = hhmmToMinutes(twEnd);
    const hasTw = startMin != null && endMin != null && endMin > startMin;
    state.currentTargets[idx].required = req;
    state.currentTargets[idx].stay_minutes = stay;
    state.currentTargets[idx].time_window = hasTw ? [startMin, endMin] : null;
    if (!hasTw) state.currentTargets[idx].datetime_window = null;
  });
}

async function loadTargets() {
  setStatus("Loading targets...");
  try {
    const startDate = document.getElementById("startDate")?.value || new Date().toISOString().slice(0, 10);
    const resp = await fetch(`/api/targets?count=100&start_date=${startDate}`);
    if (!resp.ok) throw new Error("API error");
    const data = await resp.json();
    state.branch = data.branch;
    state.allTargets = data.targets;
    applyTargetCount();
    setStatus("Targets loaded");
  } catch (err) {
    console.error("Failed to load targets", err);
    setStatus("Failed to load targets");
  }
}

async function solve() {
  applyTargetEditsFromTable();
  const preset = document.getElementById("preset").value;
  const speed = Number(document.getElementById("speed").value) || 40;
  const targetCount = state.currentTargets.length;
  const startDate = document.getElementById("startDate").value || new Date().toISOString().slice(0, 10);
  const singleDay = document.getElementById("singleDay").checked;
  const dates = singleDay ? [startDate] : buildWeekDates(startDate);
  const solveSeconds = Number(document.getElementById("solveSeconds").value) || 1;
  rebaseTargetWindows(startDate);
  setLoading(true);
  setStatus(`Solving... (max ${solveSeconds}s)`);
  try {
    const resp = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        preset,
        speed_kmph: speed,
        targets: state.currentTargets,
        branch: state.branch,
        target_count: targetCount,
        dates,
        max_solve_seconds: solveSeconds,
      }),
    });
    if (!resp.ok) throw new Error("API error");
    const plan = await resp.json();
    state.plan = plan;
    state.plan.targets_by_id = Object.fromEntries(state.currentTargets.map((t) => [t.id, t]));
    buildFilters(plan);
    rerender();
    const warn = plan.warnings && plan.warnings.length ? ` Missing drivers on: ${plan.warnings.join(", ")}` : "";
    setStatus(`Done (backend).${warn}`);
  } catch (err) {
    console.warn("Backend solve failed, falling back to sample", err);
    const sample = await fetch("sample_data.json").then((r) => r.json());
    const data = preset === "one" ? sample.one_driver : sample.three_driver;
    state.plan = data;
    state.plan.targets_by_id = data.targets_by_id;
    state.branch = data.branch;
    state.currentTargets = data.targets;
    buildFilters(data);
    rerender();
    setStatus("Using local sample_data.json (backend unreachable)");
  } finally {
    setLoading(false);
  }
}

  function setupTabs() {
  const buttons = document.querySelectorAll(".tab-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const tabId = btn.dataset.tab;
      document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
      document.getElementById(`tab-${tabId}`).classList.add("active");
    });
  });
}

function rerender() {
  renderMap();
  renderSchedule();
  renderCoords();
  renderRaw();
}

document.addEventListener("DOMContentLoaded", () => {
  setStartDateToday();
  setupTabs();
  document.getElementById("solveBtn").addEventListener("click", () => {
    solve();
  });
  document.getElementById("targetCount").addEventListener("change", applyTargetCount);
    document.getElementById("applyTargetCountBtn").addEventListener("click", applyTargetCount);
    const clearTwBtn = document.getElementById("clearTimeWindows");
    if (clearTwBtn) {
      clearTwBtn.addEventListener("click", () => {
        state.currentTargets = state.currentTargets.map((t) => ({
          ...t,
          time_window: null,
          datetime_window: null,
        }));
        renderCoords();
        setStatus("時間枠をクリアしました");
      });
    }
    const labelToggle = document.getElementById("labelsToggle");
    if (labelToggle) {
      state.showLabelsAlways = labelToggle.checked;
      labelToggle.addEventListener("change", () => {
        state.showLabelsAlways = labelToggle.checked;
      renderMap();
    });
  }
  loadTargets().catch(console.error);

  document.addEventListener("click", (e) => {
    const row = e.target.closest("#schedule tbody tr");
    if (row && row.dataset.target) {
      highlightTarget(row.dataset.target);
    }
  });
});

function updateCoordRow(id, lat, lon) {
  const row = document.querySelector(`#coords tbody tr[data-id="${id}"]`);
  if (row) {
    const latCell = row.querySelector(".lat");
    const lonCell = row.querySelector(".lon");
    if (latCell) latCell.textContent = lat;
    if (lonCell) lonCell.textContent = lon;
  }
}

function buildWeekDates(startDateStr) {
  const base = new Date(startDateStr);
  if (Number.isNaN(base.getTime())) {
    return [];
  }
  // Shift start to next weekday if it falls on weekend.
  while (base.getDay() === 0 || base.getDay() === 6) {
    base.setDate(base.getDate() + 1);
  }
  const dates = [];
  let cursor = new Date(base);
  while (dates.length < 5) {
    if (cursor.getDay() !== 0 && cursor.getDay() !== 6) {
      dates.push(cursor.toISOString().slice(0, 10));
    }
    cursor.setDate(cursor.getDate() + 1);
  }
  return dates;
}

function clearRowHighlights() {
  document.querySelectorAll("#schedule tbody tr").forEach((tr) => tr.classList.remove("row-highlight"));
}

function highlightTarget(targetId) {
  clearRowHighlights();
  const row = document.querySelector(`#schedule tbody tr[data-target="${targetId}"]`);
  if (row) row.classList.add("row-highlight");
  const marker = markerById.get(targetId);
  if (marker) {
    marker.openTooltip();
    marker.setZIndexOffset(1000);
    setTimeout(() => marker.setZIndexOffset(0), 1000);
  }
}

function highlightFromMap(targetId) {
  highlightTarget(targetId);
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
  const schedBtn = document.querySelector('[data-tab="schedule"]');
  const schedTab = document.getElementById("tab-schedule");
  if (schedBtn) schedBtn.classList.add("active");
  document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
  if (schedTab) schedTab.classList.add("active");
}

function addArrows(points, color) {
  for (let i = 0; i < points.length - 1; i++) {
    const p1 = points[i];
    const p2 = points[i + 1];
    const lat = (p1[0] + p2[0]) / 2;
    const lon = (p1[1] + p2[1]) / 2;
    const pt1 = map.latLngToLayerPoint([p1[0], p1[1]]);
    const pt2 = map.latLngToLayerPoint([p2[0], p2[1]]);
    const angle = (Math.atan2(pt2.y - pt1.y, pt2.x - pt1.x) * 180) / Math.PI;
    const icon = L.divIcon({
      className: "",
      html: `<div class="arrow-text" style="color:${color}; transform: rotate(${angle}deg);">&#10148;</div>`,
      iconSize: [16, 16],
    });
    const m = L.marker([lat, lon], { icon, interactive: false });
    m.addTo(map);
    arrows.push(m);
  }
}

// Expose for tests and inline scripts
if (typeof window !== "undefined") {
  Object.assign(window, {
    state,
    renderSchedule,
    renderCoords,
    renderRaw,
    buildFilters,
    applyTargetCount,
    setStatus,
    rerender,
  });
}
