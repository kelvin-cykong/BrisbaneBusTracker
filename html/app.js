const BRISBANE = [-27.4698, 153.0251];
const REFRESH_MS = 10000;

const map = L.map("map", {
  zoomControl: true,
  preferCanvas: true,
}).setView(BRISBANE, 13);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

const markers = L.layerGroup().addTo(map);
const routeInput = document.querySelector("#routeInput");
const routeOptions = document.querySelector("#routeOptions");
const directionSelect = document.querySelector("#directionSelect");
const refreshButton = document.querySelector("#refreshButton");
const statusEl = document.querySelector("#status");
const countEl = document.querySelector("#count");

let vehicles = [];
function markerIcon(vehicle) {
  const rotation = Number.isFinite(vehicle.bearing) ? `rotate(${vehicle.bearing}deg)` : "";
  return L.divIcon({
    className: "",
    html: `<span style="font-size: 18px;">&#x1F68D;</span>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    popupAnchor: [0, -14],
  });
}

function formatTime(value) {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat("en-AU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  }).format(new Date(value));
}

function formatElapsedTime(value) {
  if (!value) return "Unknown";

  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (elapsedSeconds < 60) return `${elapsedSeconds}s ago`;

  const minutes = Math.floor(elapsedSeconds / 60);
  const seconds = elapsedSeconds % 60;
  if (minutes < 60) return `${minutes}m ${seconds}s ago`;

  return `${Math.floor(minutes / 60)}h ${minutes % 60}m ago`;
}

function updateElapsedTimes() {
  document.querySelectorAll(".elapsed-time").forEach((element) => {
    element.textContent = formatElapsedTime(element.dataset.timestamp);
  });
}

function popupHtml(vehicle) {
  const currentStopSequence = vehicle.current_stop_sequence === null ? "Unknown" : vehicle.current_stop_sequence;
  const currentStatus = vehicle.current_status || "Unknown";
  const currentStatusInText = currentStatus === 1 ? "Stopped at" : currentStatus === 2 ? "In transit to" : "Unknown";
  return `
    <div class="popup-title">Route ${vehicle.route || "Unknown"}</div>
    <div class="popup-row"><span>Vehicle</span><strong>${vehicle.label || vehicle.id}</strong></div>
    <div class="popup-row"><span>Direction</span><strong>${vehicle.trip_headsign || "Unknown"}</strong></div>
    <div class="popup-row"><span>Current Status</span><strong>${currentStatusInText}</strong></div>
    <div class="popup-row"><span>Current Stop Sequence</span><strong>${currentStopSequence}</strong></div>
    <div class="popup-row"><span>Current Stop Sequence Stop Name</span><strong>${vehicle.stop_name || "Unknown"}</strong></div>
    <div class="popup-row"><span>Updated</span><strong class="elapsed-time" data-timestamp="${vehicle.timestamp || ""}">${formatElapsedTime(vehicle.timestamp)}</strong></div>
  `;
}

function updateSelectOptions(select, values, allLabel) {
  const current = select.value;
  select.replaceChildren(new Option(allLabel, ""));
  values.forEach((value) => select.add(new Option(value, value)));
  select.value = values.includes(current) ? current : "";
}

function updateRouteOptions(values) {
  routeOptions.replaceChildren(...values.map((value) => new Option(value, value)));
}

function filteredVehicles() {
  const route = routeInput.value.trim();
  const direction = directionSelect.value;

  return vehicles.filter((vehicle) => {
    const routeMatches = route && vehicle.route === route;
    const directionMatches = !direction || vehicle.trip_headsign === direction;
    return routeMatches && directionMatches;
  });
}

function updateDirectionOptions() {
  const availableDirections = [...new Set(
    vehicles
      .filter((vehicle) => vehicle.route === routeInput.value.trim())
      .map((vehicle) => vehicle.trip_headsign)
      .filter(Boolean),
  )].sort();

  updateSelectOptions(directionSelect, availableDirections, "All directions");
}

function renderMarkers(fitMap = false) {
  markers.clearLayers();

  const route = routeInput.value.trim();
  if (!route) {
    countEl.textContent = "Enter a route ID to show buses";
    return;
  }

  const filtered = filteredVehicles();

  filtered.forEach((vehicle) => {
    L.marker([vehicle.latitude, vehicle.longitude], { icon: markerIcon(vehicle) })
      .bindPopup(popupHtml(vehicle))
      .addTo(markers);
  });

  const routeText = ` on route ${route}`;
  const directionText = directionSelect.value ? `, direction ${directionSelect.value}` : "";
  countEl.textContent = `${filtered.length} of ${vehicles.length} buses${routeText}${directionText}`;

  if (fitMap && filtered.length) {
    const bounds = L.latLngBounds(filtered.map((vehicle) => [vehicle.latitude, vehicle.longitude]));
    map.fitBounds(bounds.pad(0.05), { maxZoom: 20 });
  }
}

async function loadVehicles() {
  statusEl.className = "status";
  statusEl.textContent = "Refreshing";
  refreshButton.disabled = true;

  try {
    const response = await fetch("/api/vehicles", { cache: "no-store" });
    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.detail || payload.error || "Translink feed request failed");
    }

    vehicles = payload.vehicles || [];
    updateRouteOptions(payload.routes || []);
    updateDirectionOptions();
    renderMarkers();

    

    statusEl.className = "status ok";
    statusEl.textContent = `Updated ${formatTime(payload.fetchedAt)}`;
  } catch (error) {
    statusEl.className = "status error";
    statusEl.textContent = "Feed unavailable";
    countEl.textContent = error.message;
  } finally {
    refreshButton.disabled = false;
  }
}

routeInput.addEventListener("input", () => {
  updateDirectionOptions();
  renderMarkers(true);
});
directionSelect.addEventListener("change", renderMarkers);
refreshButton.addEventListener("click", loadVehicles);

loadVehicles();
setInterval(loadVehicles, REFRESH_MS);
setInterval(updateElapsedTimes, 1000);
