const DATA_BASE = (() => {
  const params = new URLSearchParams(window.location.search);
  const client = params.get("cliente") || "CLIENTE_DEMO";
  const parcel = params.get("parcela") || "PARCELA_DEMO";
  return `data/${client}/${parcel}/`;
})();
const DATA_URL = DATA_BASE + "dashboard.json";

const SEVERITY_LABEL = {
  info: "Informativo",
  attention: "Atención",
  priority: "Prioritario",
};

let DASHBOARD = null;
let MAP = null;
let OVERLAY = null;
let BOUNDARY_LAYER = null;

init();

async function init() {
  const res = await fetch(DATA_URL);
  DASHBOARD = await res.json();

  document.getElementById("parcel-name").textContent = DASHBOARD.parcel_name;

  const steps = [
    ["hero", renderHero],
    ["cards", renderCards],
    ["map", renderMap],
    ["compare", renderCompare],
    ["chart", renderChart],
    ["bitacora", renderBitacora],
    ["harvest", renderHarvest],
    ["tech", renderTech],
  ];
  for (const [name, fn] of steps) {
    try {
      await fn();
    } catch (e) {
      console.error(`IX DRON: fallo al renderizar '${name}':`, e);
    }
  }

  document.getElementById("mode-parcela").addEventListener("click", () => setMode(false));
  document.getElementById("mode-tecnico").addEventListener("click", () => setMode(true));
}

function setMode(tech) {
  document.body.classList.toggle("tech", tech);
  document.getElementById("mode-parcela").classList.toggle("active", !tech);
  document.getElementById("mode-tecnico").classList.toggle("active", tech);
}

function fmtDate(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("es-MX", { day: "numeric", month: "long", year: "numeric" });
}

function verdict() {
  const flights = DASHBOARD.flights;
  const last = flights[flights.length - 1];
  if (!last.change) {
    return { label: "Vuelo de referencia", cls: "status-neutral",
             text: "Este es el primer vuelo registrado. Servirá como punto de comparación para los siguientes." };
  }
  const c = last.change;
  if (c.pct_area_decrease > 30) {
    return { label: "Requiere atención", cls: "status-attention",
             text: `Se observó disminución del verdor en ${c.pct_area_decrease.toFixed(0)}% del área respecto al vuelo anterior.` };
  }
  if (c.pct_area_increase > c.pct_area_decrease) {
    return { label: "Favorable", cls: "status-favorable",
             text: `El verdor de la parcela aumentó en ${c.pct_area_increase.toFixed(0)}% del área respecto al vuelo anterior.` };
  }
  return { label: "Estable", cls: "status-neutral",
           text: `La parcela se mantiene mayormente estable respecto al vuelo anterior (${c.pct_area_stable.toFixed(0)}% del área).` };
}

function renderHero() {
  const v = verdict();
  const last = DASHBOARD.flights[DASHBOARD.flights.length - 1];
  document.getElementById("hero-status").className = "status-pill " + v.cls;
  document.getElementById("hero-status").textContent = v.label;
  document.getElementById("hero-lede").textContent = v.text;
  document.getElementById("hero-date").textContent =
    `Última observación: ${fmtDate(last.date)} · ${DASHBOARD.n_flights} vuelo(s) registrados`;
}

function renderCards() {
  const grid = document.getElementById("card-grid");
  grid.innerHTML = "";
  const flights = DASHBOARD.flights;
  const last = flights[flights.length - 1];
  const first = flights[0];

  const cards = [];

  const trendDelta = last.vari_mean - first.vari_mean;
  cards.push({
    label: "Verdor (VARI)",
    value: last.vari_mean.toFixed(2),
    cls: trendDelta >= 0 ? "up" : "down",
    sub: "Índice de verdor derivado de imágenes RGB",
  });

  cards.push({
    label: "Cobertura vegetal",
    value: last.vegetation_cover_pct.toFixed(0) + "%",
    cls: "",
    sub: "Superficie con vegetación detectada",
  });

  if (last.change) {
    cards.push({
      label: "Cambio reciente",
      value: (last.change.mean_delta >= 0 ? "+" : "") + last.change.mean_delta.toFixed(3),
      cls: last.change.mean_delta >= 0 ? "up" : "down",
      sub: `vs. vuelo del ${fmtDate(last.change.flight_id_previous)}`,
    });
    cards.push({
      label: "Zona con disminución",
      value: last.change.pct_area_decrease.toFixed(0) + "%",
      cls: last.change.pct_area_decrease > 20 ? "down" : "",
      sub: "del área analizada",
    });
  } else {
    cards.push({ label: "Cambio reciente", value: "—", cls: "", sub: "Disponible desde el 2do vuelo" });
    cards.push({ label: "Serie temporal", value: "—", cls: "", sub: "Disponible desde el 3er vuelo" });
  }

  cards.forEach(c => {
    const el = document.createElement("div");
    el.className = "stat-card";
    el.innerHTML = `<div class="label">${c.label}</div>
                     <div class="value ${c.cls}">${c.value}</div>
                     <div class="sub">${c.sub}</div>`;
    grid.appendChild(el);
  });
}

async function renderMap() {
  const b = DASHBOARD.flights[0].bounds_4326;
  const bounds = [[b.miny, b.minx], [b.maxy, b.maxx]];

  MAP = L.map("map", { scrollWheelZoom: false }).fitBounds(bounds);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap",
    maxZoom: 19,
  }).addTo(MAP);

  try {
    const res = await fetch(`${DATA_BASE}parcel_boundary.geojson`);
    const geo = await res.json();
    BOUNDARY_LAYER = L.geoJSON(geo, { style: { color: "#2F5233", weight: 2, fillOpacity: 0 } }).addTo(MAP);
  } catch (e) { /* boundary opcional */ }

  const zoneNote = document.getElementById("map-zone-note");
  if (DASHBOARD.has_separate_analysis_zone) {
    try {
      const res = await fetch(`${DATA_BASE}analysis_zone.geojson`);
      const geo = await res.json();
      L.geoJSON(geo, {
        style: { color: "#9A6B45", weight: 2, dashArray: "6 4", fillOpacity: 0 },
      }).addTo(MAP);
      zoneNote.innerHTML = `Línea sólida verde: límite del predio. `
        + `<span class="zone-dash"></span> línea punteada café: zona usada `
        + `para el análisis (excluye construcción/arbolado).`;
    } catch (e) { /* zona opcional */ }
  }

  showLayer("rgb");

  document.querySelectorAll(".map-controls button").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".map-controls button").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      showLayer(btn.dataset.layer);
    });
  });
}

function showLayer(kind) {
  const last = DASHBOARD.flights[DASHBOARD.flights.length - 1];
  const b = last.bounds_4326;
  const bounds = [[b.miny, b.minx], [b.maxy, b.maxx]];
  const path = last.previews && last.previews[kind];
  if (OVERLAY) MAP.removeLayer(OVERLAY);
  renderMapLegend(kind, last);
  if (!path) return;
  OVERLAY = L.imageOverlay(DATA_BASE + path, bounds, { opacity: 0.95 }).addTo(MAP);
}

function renderMapLegend(kind, flight) {
  const el = document.getElementById("map-legend");
  if (kind === "vari" && flight.vari_display_range) {
    const [lo, hi] = flight.vari_display_range;
    el.innerHTML = `
      <div class="gradient-bar">
        <div class="gradient-track" style="--gradient: linear-gradient(to right, rgb(255,0,0), rgb(255,128,0), rgb(128,255,0), rgb(0,255,0));"></div>
        <div class="gradient-ticks"><span>${lo.toFixed(2)} (menos verdor)</span><span>${hi.toFixed(2)} (más verdor)</span></div>
      </div>`;
  } else if (kind === "change" && flight.change) {
    const [lo, hi] = flight.change_display_range || [-0.2, 0.2];
    el.innerHTML = `
      <div class="gradient-bar">
        <div class="gradient-track" style="--gradient: linear-gradient(to right, rgb(255,0,0), rgb(255,128,128), rgb(255,255,255), rgb(128,255,128), rgb(0,255,0));"></div>
        <div class="gradient-ticks"><span>${lo} disminuyó</span><span>estable</span><span>${hi} aumentó</span></div>
      </div>`;
  } else if (kind === "change") {
    el.innerHTML = `<p class="map-zone-note">El mapa de cambio estará disponible a partir del segundo vuelo.</p>`;
  } else {
    el.innerHTML = "";
  }
}

function renderCompare() {
  const flights = DASHBOARD.flights;
  const selA = document.getElementById("compare-a");
  const selB = document.getElementById("compare-b");
  selA.innerHTML = "";
  selB.innerHTML = "";
  flights.forEach((f, i) => {
    const optA = new Option(fmtDate(f.date), i);
    const optB = new Option(fmtDate(f.date), i);
    selA.add(optA);
    selB.add(optB);
  });
  selA.value = 0;
  selB.value = flights.length - 1;

  const imgA = document.getElementById("compare-img-a");
  const imgB = document.getElementById("compare-img-b");
  const clip = document.getElementById("compare-clip");
  const handle = document.getElementById("compare-handle");
  const wrap = document.getElementById("compare-wrap");

  function update() {
    const fa = flights[selA.value];
    const fb = flights[selB.value];
    imgA.src = DATA_BASE + fa.previews.rgb;
    imgB.src = DATA_BASE + fb.previews.rgb;
    document.getElementById("compare-label-left").textContent = fmtDate(fa.date);
    document.getElementById("compare-label-right").textContent = fmtDate(fb.date);
  }
  selA.addEventListener("change", update);
  selB.addEventListener("change", update);
  update();

  let dragging = false;
  function setSplit(clientX) {
    const rect = wrap.getBoundingClientRect();
    let pct = ((clientX - rect.left) / rect.width) * 100;
    pct = Math.max(2, Math.min(98, pct));
    clip.style.width = pct + "%";
    handle.style.left = pct + "%";
    imgB.style.width = (10000 / pct) + "%";
  }
  handle.addEventListener("mousedown", () => dragging = true);
  window.addEventListener("mouseup", () => dragging = false);
  window.addEventListener("mousemove", e => { if (dragging) setSplit(e.clientX); });
  wrap.addEventListener("click", e => setSplit(e.clientX));
  handle.addEventListener("touchstart", () => dragging = true);
  window.addEventListener("touchend", () => dragging = false);
  window.addEventListener("touchmove", e => { if (dragging) setSplit(e.touches[0].clientX); });
}

function renderChart() {
  const flights = DASHBOARD.flights;
  if (flights.length < 3) {
    document.getElementById("chart-section").style.display = "none";
    return;
  }
  const dates = flights.map(f => f.date);
  const vari = flights.map(f => f.vari_mean);
  const cover = flights.map(f => f.vegetation_cover_pct);

  Plotly.newPlot("chart-vari", [
    { x: dates, y: vari, name: "Verdor (VARI)", mode: "lines+markers",
      line: { color: "#2F5233" }, yaxis: "y1" },
    { x: dates, y: cover, name: "Cobertura vegetal (%)", mode: "lines+markers",
      line: { color: "#3E6E85", dash: "dot" }, yaxis: "y2" },
  ], {
    margin: { t: 20, r: 50, l: 50, b: 40 },
    font: { family: "Source Sans 3, sans-serif", color: "#1E2A1F" },
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    xaxis: { title: "" },
    yaxis: { title: "VARI" },
    yaxis2: { title: "Cobertura %", overlaying: "y", side: "right" },
    legend: { orientation: "h", y: -0.2 },
  }, { displayModeBar: false, responsive: true });
}

function renderBitacora() {
  const container = document.getElementById("bitacora");
  container.innerHTML = "";
  const flights = [...DASHBOARD.flights].reverse();

  flights.forEach(f => {
    const hasAttention = (f.recommendations || []).some(r => r.severity === "attention");
    const entry = document.createElement("div");
    entry.className = "entry" + (hasAttention ? " attention" : "");

    let title, body = "";

    if (!f.change) {
      title = "Vuelo de referencia";
      body = `<p>Primer vuelo registrado para esta parcela. A partir del segundo vuelo se activará la comparación automática.</p>`;
    } else {
      title = hasAttention ? "Cambio detectado" : "Sin cambios relevantes";
      (f.recommendations || []).forEach(r => {
        body += `
          <p><span class="entry-tag">Observación</span>${r.observation}</p>
          <p><span class="entry-tag">Interpretación</span>${r.interpretation}</p>
          <p><span class="entry-tag">Recomendación</span>${r.recommendation}</p>`;
      });
      if (!(f.recommendations || []).length) {
        body = `<p>Vuelo procesado sin observaciones que requieran atención.</p>`;
      }
    }

    if ((f.warnings || []).length) {
      body += `<div class="warning-box tech-only">${f.warnings.join(" · ")}</div>`;
    }

    entry.innerHTML = `
      <div class="entry-date">${fmtDate(f.date)}</div>
      <div class="entry-title">${title}</div>
      <div class="entry-body">${body}</div>`;
    container.appendChild(entry);
  });
}

// ---------------------------------------------------------------------
// Estimador de cosecha: conteo preliminar de plantas + calculadora de
// rendimiento/ingreso. Los supuestos agronómicos (mazorcas/planta,
// granos/mazorca, peso de mil granos) son EDITABLES por el productor —
// el sistema solo aporta la población de plantas (conteo) y el área.
// ---------------------------------------------------------------------

function harvestStorageKey() {
  return `ixdron_harvest_calc_${DASHBOARD.client_id}_${DASHBOARD.parcel_id}`;
}

function renderHarvest() {
  const section = document.getElementById("harvest-section");
  const last = DASHBOARD.flights[DASHBOARD.flights.length - 1];
  const pc = last.plant_counting;

  if (!pc || !pc.plant_count_estimate || pc.plant_count_estimate <= 0) {
    section.style.display = "none";
    return;
  }
  section.style.display = "";

  const areaHa = last.analysis_area_ha || null;
  const plantsHa = areaHa ? pc.plant_count_estimate / areaHa : null;

  const cardsEl = document.getElementById("harvest-cards");
  cardsEl.innerHTML = "";
  const cards = [
    { label: "Plantas detectadas", value: pc.plant_count_estimate.toLocaleString("es-MX"),
      sub: "conteo preliminar por imagen" },
    { label: "Densidad estimada", value: plantsHa ? Math.round(plantsHa).toLocaleString("es-MX") : "—",
      sub: "plantas por hectárea" },
    { label: "Área analizada", value: areaHa ? areaHa.toFixed(2) : "—",
      sub: "hectáreas (zona de siembra)" },
  ];
  cards.forEach(c => {
    const el = document.createElement("div");
    el.className = "stat-card";
    el.innerHTML = `<div class="label">${c.label}</div><div class="value">${c.value}</div><div class="sub">${c.sub}</div>`;
    cardsEl.appendChild(el);
  });

  // Prefill: valores guardados por el usuario tienen prioridad; si no hay,
  // se usan los calculados/por defecto.
  const plantsHaEl = document.getElementById("calc-plants-ha");
  const earsEl = document.getElementById("calc-ears");
  const kernelsEl = document.getElementById("calc-kernels");
  const pmgEl = document.getElementById("calc-pmg");
  const areaEl = document.getElementById("calc-area");
  const priceEl = document.getElementById("calc-price");
  const savedNote = document.getElementById("calc-saved-note");

  let saved = null;
  try {
    const raw = localStorage.getItem(harvestStorageKey());
    if (raw) saved = JSON.parse(raw);
  } catch (e) { /* localStorage no disponible; se continúa sin persistencia */ }

  plantsHaEl.value = saved?.plantsHa ?? (plantsHa ? Math.round(plantsHa) : "");
  earsEl.value = saved?.ears ?? earsEl.value;
  kernelsEl.value = saved?.kernels ?? kernelsEl.value;
  pmgEl.value = saved?.pmg ?? pmgEl.value;
  areaEl.value = saved?.area ?? (areaHa ? areaHa.toFixed(2) : "");
  priceEl.value = saved?.price ?? "";

  if (saved) {
    savedNote.textContent = "Mostrando tus valores guardados.";
  }

  function recompute() {
    const plantsHaVal = parseFloat(plantsHaEl.value) || 0;
    const ears = parseFloat(earsEl.value) || 0;
    const kernels = parseFloat(kernelsEl.value) || 0;
    const pmg = parseFloat(pmgEl.value) || 0;
    const area = parseFloat(areaEl.value) || 0;
    const price = parseFloat(priceEl.value) || 0;

    // ton/ha = plantas/ha × mazorcas/planta × granos/mazorca × (peso de mil
    // granos en g) ÷ 1,000,000,000  (ver nota al pie en el HTML)
    const yieldHa = (plantsHaVal * ears * kernels * pmg) / 1e9;
    const totalProd = yieldHa * area;
    const revenue = totalProd * price;

    document.getElementById("calc-yield-ha").textContent = yieldHa ? yieldHa.toFixed(2) : "—";
    document.getElementById("calc-total-prod").textContent = totalProd ? totalProd.toFixed(1) : "—";
    document.getElementById("calc-revenue").textContent = revenue
      ? "$" + revenue.toLocaleString("es-MX", { maximumFractionDigits: 0 })
      : "—";
  }

  [plantsHaEl, earsEl, kernelsEl, pmgEl, areaEl, priceEl].forEach(el => {
    el.addEventListener("input", recompute);
  });
  recompute();

  document.getElementById("calc-save").addEventListener("click", () => {
    const payload = {
      plantsHa: plantsHaEl.value, ears: earsEl.value, kernels: kernelsEl.value,
      pmg: pmgEl.value, area: areaEl.value, price: priceEl.value,
    };
    try {
      localStorage.setItem(harvestStorageKey(), JSON.stringify(payload));
      savedNote.textContent = "Guardado en este navegador ✓";
    } catch (e) {
      savedNote.textContent = "No se pudo guardar (almacenamiento del navegador no disponible).";
    }
  });

  document.getElementById("calc-reset").addEventListener("click", () => {
    try { localStorage.removeItem(harvestStorageKey()); } catch (e) { /* noop */ }
    savedNote.textContent = "";
    plantsHaEl.value = plantsHa ? Math.round(plantsHa) : "";
    earsEl.value = 1;
    kernelsEl.value = 500;
    pmgEl.value = 300;
    areaEl.value = areaHa ? areaHa.toFixed(2) : "";
    priceEl.value = "";
    recompute();
  });
}

function renderTech() {
  const tbody = document.querySelector("#tech-table tbody");
  tbody.innerHTML = "";
  DASHBOARD.flights.forEach(f => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${f.flight_id}</td>
      <td>${f.status}</td>
      <td>${f.vari_mean?.toFixed(4) ?? "—"}</td>
      <td>${f.vari_median?.toFixed(4) ?? "—"}</td>
      <td>${f.vegetation_cover_pct?.toFixed(1) ?? "—"}%</td>
      <td>${f.valid_area_pct?.toFixed(1) ?? "—"}%</td>
      <td>${f.pipeline_version ?? "—"}</td>
      <td>${(f.warnings || []).join("; ") || "—"}</td>`;
    tbody.appendChild(tr);
  });

  document.getElementById("data-maturity").textContent = DASHBOARD.data_maturity;
  renderEducation();
}

// ---------------------------------------------------------------------
// Sección educativa: fórmulas de los índices RGB, leyendas de color y
// explorador interactivo. Los "colormaps" replican exactamente los que
// usa el pipeline Python (raster_utils.apply_colormap) para que la barra
// de color coincida con lo que se ve en el mapa.
// ---------------------------------------------------------------------

function variColor(norm) {
  const r = Math.min(Math.max(1.5 - 2 * norm, 0), 1);
  const g = Math.min(Math.max(2 * norm, 0), 1);
  return [Math.round(r * 255), Math.round(g * 255), 0];
}

function computeIndices(r, g, b) {
  const rn = r, gn = g, bn = b; // escala 0-255, igual que el pipeline
  const vari = (gn - rn) / (gn + rn - bn);
  const exg = 2 * (gn / 255) - (rn / 255) - (bn / 255);
  const gli = (2 * gn - rn - bn) / (2 * gn + rn + bn);
  return { vari, exg, gli };
}

const EDU_INDEX_DEFS = [
  {
    key: "vari", label: "VARI", full: "Visible Atmospherically Resistant Index",
    formula: "(G − R) / (G + R − B)",
    domain: [-0.2, 0.4],
    text: "El índice principal del sistema. Compara qué tan verde se ve un "
        + "píxel frente a rojo y azul, y es poco sensible a cambios de "
        + "iluminación entre vuelos. Valores altos = más verdor relativo.",
    gradientCss: "linear-gradient(to right, rgb(255,0,0), rgb(255,128,0), rgb(128,255,0), rgb(0,255,0))",
  },
  {
    key: "exg", label: "ExG", full: "Excess Green Index",
    formula: "2G − R − B  (canales normalizados 0–1)",
    domain: [-0.5, 1.0],
    text: "Resalta directamente el exceso de verde sobre rojo y azul "
        + "combinados. Se calcula y se guarda para cada vuelo, aunque el "
        + "dashboard usa VARI como referencia principal.",
    gradientCss: "linear-gradient(to right, rgb(120,90,60), rgb(190,190,90), rgb(60,160,60))",
  },
  {
    key: "gli", label: "GLI", full: "Green Leaf Index",
    formula: "(2G − R − B) / (2G + R + B)",
    domain: [-0.2, 0.4],
    text: "Similar a ExG pero normalizado, lo que facilita comparar su "
        + "magnitud entre distintas condiciones de brillo.",
    gradientCss: "linear-gradient(to right, rgb(120,90,60), rgb(190,190,90), rgb(60,160,60))",
  },
];

function markerPct(value, domain) {
  const [lo, hi] = domain;
  const pct = ((value - lo) / (hi - lo)) * 100;
  return Math.min(98, Math.max(2, pct));
}

function renderEducation() {
  const last = DASHBOARD.flights[DASHBOARD.flights.length - 1];
  const container = document.getElementById("edu-index-cards");
  container.innerHTML = "";

  const values = {
    vari: last.vari_mean,
    exg: last.indices_extra?.exg?.mean,
    gli: last.indices_extra?.gli?.mean,
  };

  EDU_INDEX_DEFS.forEach(def => {
    const val = values[def.key];
    const card = document.createElement("div");
    card.className = "edu-card";
    const markerHtml = (val !== undefined && val !== null)
      ? `<div class="gradient-bar">
           <div class="gradient-track" style="--gradient:${def.gradientCss}">
             <div class="marker" style="left:${markerPct(val, def.domain)}%"></div>
           </div>
           <div class="gradient-ticks"><span>${def.domain[0]}</span><span>${def.domain[1]}</span></div>
         </div>
         <p class="edu-current">En tu parcela hoy: <strong>${val.toFixed(3)}</strong></p>`
      : "";
    card.innerHTML = `
      <h3>${def.label} <span style="font-weight:400;font-size:0.75rem;color:var(--ink-soft)">— ${def.full}</span></h3>
      <div class="edu-formula">${def.formula}</div>
      <p>${def.text}</p>
      ${markerHtml}
    `;
    container.appendChild(card);
  });

  // Mapa de cambio: umbral configurado + marcador si hay comparación
  const thresholdEl = document.getElementById("edu-threshold-current");
  if (last.change) {
    thresholdEl.innerHTML = `Umbral usado en esta parcela: <strong>±${last.change.threshold_used}</strong> `
      + `de VARI · último resultado: ${last.change.pct_area_increase.toFixed(0)}% aumentó, `
      + `${last.change.pct_area_stable.toFixed(0)}% estable, ${last.change.pct_area_decrease.toFixed(0)}% disminuyó.`;
  } else {
    thresholdEl.textContent = "Disponible a partir del segundo vuelo.";
  }

  setupExplorer();
}

function setupExplorer() {
  const rEl = document.getElementById("exp-r");
  const gEl = document.getElementById("exp-g");
  const bEl = document.getElementById("exp-b");
  const swatch = document.getElementById("exp-swatch");
  const variOut = document.getElementById("exp-vari");
  const exgOut = document.getElementById("exp-exg");
  const gliOut = document.getElementById("exp-gli");

  function update() {
    const r = +rEl.value, g = +gEl.value, b = +bEl.value;
    document.getElementById("exp-r-val").textContent = r;
    document.getElementById("exp-g-val").textContent = g;
    document.getElementById("exp-b-val").textContent = b;
    swatch.style.background = `rgb(${r},${g},${b})`;
    const { vari, exg, gli } = computeIndices(r, g, b);
    variOut.textContent = Number.isFinite(vari) ? vari.toFixed(3) : "indefinido";
    exgOut.textContent = exg.toFixed(3);
    gliOut.textContent = Number.isFinite(gli) ? gli.toFixed(3) : "indefinido";
  }
  [rEl, gEl, bEl].forEach(el => el.addEventListener("input", update));
  update();
}
