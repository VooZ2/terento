(() => {
  "use strict";

  const D = window.TerentoMapStylesData;
  const dataNode = document.getElementById("map-styles-data");
  const viewer = document.getElementById("map-styles");
  if (!D || !window.L || !dataNode || !viewer) return;

  const L = window.L;
  const data = JSON.parse(dataNode.textContent);
  const copy = data.copy;
  const locale = data.locale;
  const styles = data.styles;
  const styleIds = styles.map((style) => style.id);
  const styleById = Object.fromEntries(styles.map((style) => [style.id, style]));
  const areas = data.areas.map((area) => ({...area, bbox: D.bbox(area)}));
  const areaById = Object.fromEntries(areas.map((area) => [area.id, area]));
  const $ = (id) => document.getElementById(id);
  const stage = $("map-styles-stage");
  const narrow = window.matchMedia("(max-width: 720px)");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[char]));
  const icon = (paths) => `<svg class="map-styles-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${paths}</svg>`;
  const ICON_PIN = icon('<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11Z"/><circle cx="12" cy="10" r="2.3"/>');
  const ICON_STAR = icon('<path d="m12 4 2.4 5 5.4.6-4 3.7 1.1 5.3L12 16l-4.9 2.6 1.1-5.3-4-3.7 5.4-.6Z"/>');
  const ICON_MINUS = icon('<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>');
  const ICON_CLOCK = icon('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>');
  const ICON_CHEVRON = icon('<path d="m9 6 6 6-6 6"/>');

  let regionNames = null;
  try { regionNames = new Intl.DisplayNames([locale], {type: "region"}); } catch (error) { regionNames = null; }
  const countryName = (code) => {
    try { return (regionNames && regionNames.of(code)) || code; } catch (error) { return code; }
  };

  const fromHash = D.parseHash(window.location.hash);
  const state = {
    area: areaById[fromHash.area] ? fromHash.area : "dolomites-tre-cime",
    a: styleIds.includes(fromHash.style) ? fromHash.style : "opentopomap",
    b: styleIds.includes(fromHash.compare) ? fromHash.compare : "bbbike",
    mode: fromHash.mode || "swipe",
    tab: "places",
    query: "",
    split: 50,
  };
  if (state.b === state.a) state.b = styleIds.find((id) => id !== state.a);
  if (narrow.matches && state.mode === "split") state.mode = "swipe";

  let manifest = null;
  let best = D.bestAreas(areas, null);
  let catalogFacts = null;

  // Maps ----------------------------------------------------------------------
  const mapOptions = {
    zoomControl: false,
    attributionControl: false,
    zoomSnap: 1,
    keyboard: true,
    maxBoundsViscosity: 1,
    fadeAnimation: !reduceMotion.matches,
    zoomAnimation: !reduceMotion.matches,
    markerZoomAnimation: false,
  };
  const mapA = L.map("map-styles-map-a", mapOptions);
  const mapB = L.map("map-styles-map-b", mapOptions);
  const leftPane = mapA.createPane("terento-left");
  const rightPane = mapA.createPane("terento-right");
  leftPane.style.zIndex = "210";
  rightPane.style.zIndex = "200";
  const layers = {a: null, b: null, split: null};
  let syncing = false;

  function linkViews(source, target) {
    source.on("move", () => {
      if (syncing || state.mode !== "split") return;
      syncing = true;
      target.setView(source.getCenter(), source.getZoom(), {animate: false});
      syncing = false;
    });
  }
  linkViews(mapA, mapB);
  linkViews(mapB, mapA);

  const area = () => areaById[state.area];
  const boundsOf = (item) => L.latLngBounds([item.bbox[1], item.bbox[0]], [item.bbox[3], item.bbox[2]]);
  const status = (styleId) => D.layerStatus(manifest, state.area, styleId);

  function tileLayer(styleId, pane) {
    const url = D.tileUrl(manifest, state.area, styleId);
    if (!url) return null;
    const current = area();
    return L.tileLayer(url, {
      pane,
      minZoom: current.zoom[0],
      maxZoom: current.zoom[1],
      bounds: boundsOf(current),
      noWrap: true,
      keepBuffer: 2,
    });
  }

  function rebuildLayers() {
    Object.keys(layers).forEach((key) => {
      if (layers[key]) layers[key].remove();
      layers[key] = null;
    });
    if (status(state.a) === "AVAILABLE") {
      layers.a = tileLayer(state.a, state.mode === "swipe" ? "terento-left" : "tilePane");
      if (layers.a) layers.a.addTo(mapA);
    }
    if (state.mode === "swipe" && status(state.b) === "AVAILABLE") {
      layers.b = tileLayer(state.b, "terento-right");
      if (layers.b) layers.b.addTo(mapA);
    }
    if (state.mode === "split" && status(state.b) === "AVAILABLE") {
      layers.split = tileLayer(state.b, "tilePane");
      if (layers.split) layers.split.addTo(mapB);
    }
    updateClip();
  }

  function updateClip() {
    if (state.mode !== "swipe") {
      leftPane.style.clip = "";
      rightPane.style.clip = "";
      return;
    }
    const size = mapA.getSize();
    const topLeft = mapA.containerPointToLayerPoint([0, 0]);
    const bottomRight = mapA.containerPointToLayerPoint(size);
    const x = topLeft.x + size.x * state.split / 100;
    leftPane.style.clip = `rect(${topLeft.y}px, ${x}px, ${bottomRight.y}px, ${topLeft.x}px)`;
    rightPane.style.clip = `rect(${topLeft.y}px, ${bottomRight.x}px, ${bottomRight.y}px, ${x}px)`;
  }
  mapA.on("move zoom resize viewreset", updateClip);
  mapA.on("zoomend", updateZoom);

  function frameArea() {
    const current = area();
    const bounds = boundsOf(current);
    [mapA, mapB].forEach((map) => {
      map.setMinZoom(current.zoom[0]);
      map.setMaxZoom(current.zoom[1]);
      map.setMaxBounds(bounds.pad(0.05));
      map.setView([current.center[1], current.center[0]], D.defaultZoom(current), {animate: false});
    });
  }

  // Rendering -----------------------------------------------------------------
  function announce(message) {
    const live = $("map-styles-live");
    if (live) live.textContent = message;
  }

  function renderPlace() {
    const current = area();
    $("map-styles-place-kind").textContent = copy.kind[current.kind];
    $("map-styles-area-title").textContent = current.name;
    const countries = current.countryCodes.map(countryName).join(", ");
    const tags = current.tags.filter((tag) => copy.tags[tag]).slice(0, 2)
      .map((tag) => `<span class="map-styles-tag">${escapeHtml(copy.tags[tag])}</span>`).join("");
    const covered = D.coveredCount(manifest, current.id, styleIds);
    const badge = best.has(current.id) ? `<span class="map-styles-best">${ICON_STAR}${escapeHtml(copy.best)}</span>` : "";
    $("map-styles-area-meta").innerHTML = `${ICON_PIN}<span>${escapeHtml(countries)}</span>${tags}<span>· ${escapeHtml(D.format(copy.styles_of, {n: covered}))}</span>${badge}`;
  }

  function styleOption(styleId, selected, other) {
    const covered = status(styleId) !== "NOT_COVERED";
    const label = styleById[styleId].name + (covered ? "" : ` (${copy.not_here})`);
    return `<option value="${styleId}"${styleId === selected ? " selected" : ""}${covered && styleId !== other ? "" : " disabled"}>${escapeHtml(label)}</option>`;
  }

  function renderStyles() {
    const pills = $("map-styles-pills");
    pills.innerHTML = styles.map((style) => {
      const covered = status(style.id) !== "NOT_COVERED";
      const checked = style.id === state.a;
      return `<button type="button" class="map-styles-pill" role="radio" data-style="${style.id}" aria-checked="${checked}" tabindex="${checked ? 0 : -1}"${covered ? "" : ' aria-disabled="true"'} title="${escapeHtml(covered ? style.summary : copy.not_here)}">${covered ? "" : ICON_MINUS}${escapeHtml(style.name)}${covered ? "" : `<span class="sr-only"> (${escapeHtml(copy.not_here)})</span>`}</button>`;
    }).join("");
    $("map-styles-style-a").innerHTML = styleIds.map((id) => styleOption(id, state.a, state.b)).join("");
    $("map-styles-style-b").innerHTML = styleIds.map((id) => styleOption(id, state.b, state.a)).join("");
    pills.hidden = state.mode !== "single";
    $("map-styles-compare").hidden = state.mode === "single";
    const style = styleById[state.a];
    $("map-styles-caption").innerHTML = state.mode === "single"
      ? `<b>${escapeHtml(style.name)}</b> · ${escapeHtml(style.summary)}`
      : escapeHtml(state.mode === "split" ? copy.split_caption : copy.swipe_caption);
    $("map-styles-label-a").textContent = styleById[state.a].name;
    $("map-styles-label-b").textContent = styleById[state.b].name;
    renderNotices();
    renderAttribution();
  }

  function renderNotices() {
    const current = area();
    [["map-styles-notice-a", state.a, true], ["map-styles-notice-b", state.b, state.mode !== "single"]].forEach(([id, styleId, visible]) => {
      const node = $(id);
      const value = status(styleId);
      if (!visible || value === "AVAILABLE") {
        node.hidden = true;
        return;
      }
      const values = {style: styleById[styleId].name, place: current.name};
      const title = value === "NOT_COVERED" ? D.format(copy.not_covered, values) : D.format(copy.pending, values);
      const detail = value === "NOT_COVERED" ? copy.not_covered_detail : copy.pending_detail;
      const short = value === "NOT_COVERED" ? copy.not_covered_short : copy.pending_short;
      node.innerHTML = `<div>${value === "NOT_COVERED" ? ICON_MINUS : ICON_CLOCK}<p><strong>${escapeHtml(title)}</strong><span>${escapeHtml(detail)}</span></p><p class="map-styles-notice-short">${escapeHtml(short)}</p></div>`;
      node.dataset.status = value === "NOT_COVERED" ? "not-covered" : "pending";
      node.hidden = false;
    });
  }

  function renderAttribution() {
    const active = state.mode === "single" ? [state.a] : [state.a, state.b];
    const credits = active
      .map((id) => manifest && Array.isArray(manifest.styles) ? manifest.styles.find((style) => style.id === id) : null)
      .filter(Boolean)
      .map((style) => /^https:\/\//.test(style.attributionUrl || "")
        ? `<a href="${escapeHtml(style.attributionUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(style.attribution)}</a>`
        : escapeHtml(style.attribution));
    $("map-styles-attribution").innerHTML = ['© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a>', ...credits].join(" · ");
  }

  function updateZoom() {
    const current = area();
    const zoom = mapA.getZoom();
    $("map-styles-zoom-level").textContent = `${D.zoomPercent(current, zoom)}%`;
    $("map-styles-zoom-in").disabled = zoom >= current.zoom[1];
    $("map-styles-zoom-out").disabled = zoom <= current.zoom[0];
  }

  function renderMode() {
    viewer.dataset.mode = state.mode;
    stage.dataset.mode = state.mode;
    stage.style.setProperty("--map-styles-split", `${state.split}%`);
    $("map-styles-knob").setAttribute("aria-valuenow", String(Math.round(state.split)));
    document.querySelectorAll(".map-styles-tools [data-mode]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.mode === state.mode));
    });
    mapA.invalidateSize({pan: false});
    mapB.invalidateSize({pan: false});
    if (state.mode === "split") mapB.setView(mapA.getCenter(), mapA.getZoom(), {animate: false});
  }

  function updateHash() {
    const hash = D.serializeHash(state);
    if (window.location.hash !== hash) history.replaceState(null, "", hash);
  }

  function refresh({frame = false} = {}) {
    renderMode();
    if (frame) frameArea();
    rebuildLayers();
    renderPlace();
    renderStyles();
    updateZoom();
    updateHash();
  }

  // Place list ------------------------------------------------------------------
  function areaButton(item) {
    const covered = D.coveredCount(manifest, item.id, styleIds);
    const meta = item.kind === "route" && item.routeName ? item.routeName : (copy.tags[item.tags[0]] || copy.kind[item.kind]);
    return `<li><button type="button" class="map-styles-area" data-area="${item.id}" aria-pressed="${item.id === state.area}">`
      + `<span class="map-styles-area-name">${escapeHtml(item.name)}${best.has(item.id) ? `<span class="map-styles-area-best" title="${escapeHtml(copy.best)}">${ICON_STAR}<span class="sr-only">${escapeHtml(copy.best)}</span></span>` : ""}</span>`
      + `<span class="map-styles-area-meta">${escapeHtml(item.countryCodes.map(countryName).join(", "))} · ${escapeHtml(meta)}</span>`
      + `<span class="map-styles-area-styles"><b>${covered}</b>${escapeHtml(copy.styles_short)}</span></button></li>`;
  }

  function renderList() {
    const list = $("map-styles-list");
    const matching = areas.filter((item) => D.matches(item, state.query, countryName));
    let markup = "";
    let shown = 0;
    if (state.tab === "country") {
      const continents = ["europe", "north-america", "south-america", "africa", "asia", "oceania"];
      continents.forEach((continent) => {
        const byCountry = {};
        matching.filter((item) => item.continent === continent).forEach((item) => {
          const name = countryName(item.countryCodes[0]);
          (byCountry[name] = byCountry[name] || []).push(item);
        });
        const names = Object.keys(byCountry).sort((a, b) => a.localeCompare(b, locale));
        if (!names.length) return;
        markup += `<p class="map-styles-group">${escapeHtml(copy.continents[continent])}</p>`;
        names.forEach((name) => {
          const items = byCountry[name];
          shown += items.length;
          const open = state.query || items.some((item) => item.id === state.area);
          markup += `<details class="map-styles-country"${open ? " open" : ""}><summary><span>${escapeHtml(name)}</span><span class="map-styles-country-count">${items.length}${ICON_CHEVRON}</span></summary><ul>${items.map(areaButton).join("")}</ul></details>`;
        });
      });
    } else {
      // A search looks across places, trails and cities; the tab only narrows browsing.
      const kind = state.query.trim() ? null : {places: "place", routes: "route", cities: "city"}[state.tab];
      const items = kind ? matching.filter((item) => item.kind === kind) : matching;
      shown = items.length;
      const featured = kind ? items.filter((item) => best.has(item.id)) : [];
      const rest = kind ? items.filter((item) => !best.has(item.id)) : items;
      if (featured.length) markup += `<p class="map-styles-group">${escapeHtml(copy.best)}</p><ul>${featured.map(areaButton).join("")}</ul>`;
      if (rest.length) markup += `${featured.length ? `<p class="map-styles-group">${escapeHtml(copy.all[state.tab])}</p>` : ""}<ul>${rest.map(areaButton).join("")}</ul>`;
    }
    if (!shown) markup = `<p class="map-styles-empty">${escapeHtml(D.format(copy.no_match, {q: state.query}))}</p>`;
    list.innerHTML = markup;
    const unit = state.query.trim() ? "place" : ({routes: "route", cities: "city"}[state.tab] || "place");
    $("map-styles-count").textContent = D.plural(locale, copy.count[unit], shown);
  }

  function openPlaces() {
    $("map-styles-place").dataset.open = "true";
    $("map-styles-place-card").hidden = true;
    $("map-styles-browser").hidden = false;
    $("map-styles-open-places").setAttribute("aria-expanded", "true");
    renderList();
    const current = document.querySelector('.map-styles-area[aria-pressed="true"]');
    if (current) current.scrollIntoView({block: "center"});
    $("map-styles-search").focus();
  }

  function closePlaces(focusBack) {
    $("map-styles-place").dataset.open = "false";
    $("map-styles-place-card").hidden = false;
    $("map-styles-browser").hidden = true;
    $("map-styles-open-places").setAttribute("aria-expanded", "false");
    if (focusBack) $("map-styles-open-places").focus();
  }

  function selectArea(id) {
    if (!areaById[id]) return;
    state.area = id;
    if (status(state.a) === "NOT_COVERED") state.a = styleIds.find((styleId) => status(styleId) !== "NOT_COVERED") || state.a;
    if (status(state.b) === "NOT_COVERED" || state.b === state.a) {
      state.b = styleIds.find((styleId) => styleId !== state.a && status(styleId) !== "NOT_COVERED") || state.b;
    }
    closePlaces(true);
    refresh({frame: true});
    announce(D.format(copy.showing, {style: styleById[state.a].name, place: area().name}));
  }

  function selectStyle(styleId, focus) {
    if (status(styleId) === "NOT_COVERED") return;
    state.a = styleId;
    if (state.b === state.a) state.b = styleIds.find((id) => id !== state.a && status(id) !== "NOT_COVERED") || state.b;
    refresh();
    announce(D.format(copy.showing, {style: styleById[state.a].name, place: area().name}));
    if (focus) {
      const button = document.querySelector(`.map-styles-pill[data-style="${styleId}"]`);
      if (button) button.focus();
    }
  }

  // Events ------------------------------------------------------------------------
  $("map-styles-open-places").addEventListener("click", openPlaces);
  $("map-styles-close-places").addEventListener("click", () => closePlaces(true));
  $("map-styles-place").addEventListener("keydown", (event) => {
    if (event.key === "Escape" && $("map-styles-place").dataset.open === "true") closePlaces(true);
  });
  document.querySelectorAll(".map-styles-tabs [role=tab]").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.tab = tab.dataset.tab;
      document.querySelectorAll(".map-styles-tabs [role=tab]").forEach((item) => item.setAttribute("aria-selected", String(item === tab)));
      renderList();
    });
  });
  $("map-styles-search").addEventListener("input", (event) => {
    state.query = event.target.value;
    renderList();
  });
  $("map-styles-list").addEventListener("click", (event) => {
    const button = event.target.closest("[data-area]");
    if (button) selectArea(button.dataset.area);
  });
  $("map-styles-pills").addEventListener("click", (event) => {
    const button = event.target.closest("[data-style]");
    if (button) selectStyle(button.dataset.style);
  });
  $("map-styles-pills").addEventListener("keydown", (event) => {
    if (!["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)) return;
    event.preventDefault();
    const usable = styleIds.filter((id) => status(id) !== "NOT_COVERED");
    const index = usable.indexOf(state.a);
    const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1;
    selectStyle(usable[(index + step + usable.length) % usable.length], true);
  });
  $("map-styles-style-a").addEventListener("change", (event) => { state.a = event.target.value; refresh(); });
  $("map-styles-style-b").addEventListener("change", (event) => { state.b = event.target.value; refresh(); });
  $("map-styles-swap").addEventListener("click", () => {
    [state.a, state.b] = [state.b, state.a];
    refresh();
  });
  document.querySelectorAll(".map-styles-tools [data-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      state.mode = button.dataset.mode;
      if (state.b === state.a) state.b = styleIds.find((id) => id !== state.a) || state.b;
      refresh();
      announce(copy.modes[state.mode]);
    });
  });
  $("map-styles-zoom-in").addEventListener("click", () => mapA.zoomIn());
  $("map-styles-zoom-out").addEventListener("click", () => mapA.zoomOut());

  const knob = $("map-styles-knob");
  let dragging = false;
  function setSplit(value) {
    state.split = Math.max(5, Math.min(95, value));
    stage.style.setProperty("--map-styles-split", `${state.split}%`);
    knob.setAttribute("aria-valuenow", String(Math.round(state.split)));
    updateClip();
  }
  knob.addEventListener("pointerdown", (event) => {
    dragging = true;
    knob.setPointerCapture(event.pointerId);
    event.preventDefault();
    event.stopPropagation();
  });
  knob.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    const rect = stage.getBoundingClientRect();
    setSplit((event.clientX - rect.left) / rect.width * 100);
  });
  const stopDrag = () => { dragging = false; };
  knob.addEventListener("pointerup", stopDrag);
  knob.addEventListener("pointercancel", stopDrag);
  knob.addEventListener("keydown", (event) => {
    const moves = {ArrowLeft: -2, ArrowDown: -2, ArrowRight: 2, ArrowUp: 2};
    if (event.key in moves) setSplit(state.split + moves[event.key]);
    else if (event.key === "Home") setSplit(5);
    else if (event.key === "End") setSplit(95);
    else return;
    event.preventDefault();
  });

  let toastTimer = 0;
  function toast(markup) {
    const node = $("map-styles-toast");
    node.innerHTML = markup;
    node.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { node.hidden = true; }, 3200);
  }
  $("map-styles-copy-link").addEventListener("click", () => {
    const url = window.location.origin + window.location.pathname + D.serializeHash(state);
    const fallback = () => toast(`${escapeHtml(copy.copy_fallback)} <code>${escapeHtml(url)}</code>`);
    try {
      navigator.clipboard.writeText(url).then(() => toast(escapeHtml(copy.copied)), fallback);
    } catch (error) {
      fallback();
    }
  });

  window.addEventListener("hashchange", () => {
    const next = D.parseHash(window.location.hash);
    if (next.area && areaById[next.area] && next.area !== state.area) {
      state.area = next.area;
      refresh({frame: true});
    }
  });
  narrow.addEventListener("change", () => {
    if (narrow.matches && state.mode === "split") {
      state.mode = "swipe";
      refresh();
    }
  });
  if (window.ResizeObserver) new ResizeObserver(() => { mapA.invalidateSize({pan: false}); mapB.invalidateSize({pan: false}); updateClip(); }).observe(stage);

  // Data ------------------------------------------------------------------------
  async function fetchJson(url) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(url, {signal: controller.signal, credentials: "omit"});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } finally {
      clearTimeout(timer);
    }
  }

  async function loadManifest() {
    $("map-styles-error").hidden = true;
    try {
      const document = await fetchJson(data.manifestUrl);
      if (!document || document.schemaVersion !== 1 || !Array.isArray(document.areas)) throw new Error("invalid manifest");
      manifest = document;
      best = D.bestAreas(areas, manifest);
      if (status(state.a) === "NOT_COVERED") state.a = styleIds.find((id) => status(id) !== "NOT_COVERED") || state.a;
      refresh();
    } catch (error) {
      $("map-styles-error").hidden = false;
    }
  }
  $("map-styles-retry").addEventListener("click", loadManifest);

  async function loadCatalogFacts() {
    if (catalogFacts) return;
    try {
      catalogFacts = D.catalogFacts(await fetchJson(data.catalogUrl), styles);
    } catch (error) {
      return;
    }
    document.querySelectorAll("[data-style-card]").forEach((card) => {
      const facts = catalogFacts[card.dataset.styleCard];
      const style = styleById[card.dataset.styleCard];
      if (!facts || !style) return;
      const count = card.querySelector("[data-style-count]");
      count.textContent = D.format(style.countTemplate, {count: new Intl.NumberFormat(locale).format(facts.count)});
      count.hidden = false;
      const size = D.formatSize(facts.medianBytes, locale);
      const sizeNode = card.querySelector("[data-style-size]");
      if (size && sizeNode) {
        sizeNode.querySelector("strong").textContent = size;
        sizeNode.hidden = false;
      }
    });
  }
  const about = $("map-styles-about");
  if (about) about.addEventListener("toggle", () => { if (about.open) loadCatalogFacts(); });

  viewer.classList.add("is-ready");
  refresh({frame: true});
  loadManifest();
})();
