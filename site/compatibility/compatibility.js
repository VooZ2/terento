(() => {
  const data = globalThis.TerentoCompatibilityData;
  if (!data) throw new Error("compatibility_data_unavailable");
  const locale = globalThis.TerentoCompatibilityLocale;
  if (!locale) throw new Error("compatibility_locale_unavailable");
  const API_ORIGIN = "https://api.terento.app";
  const FALLBACK_IMAGE_URL = "/assets/generic-garmin-watch.png?v=20260826-1";
  const isLocalPreview = ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
  const previewStats = [
    {
      model: "fēnix 8",
      attempted: 3,
      successful: 3,
      failed: 0,
      status: "SUPPORTED",
      lastSuccess: "2026-08-24T21:34:17Z",
    },
  ];

  const state = {
    rows: [],
    search: "",
    status: "ALL",
    family: "ALL",
    sort: "attempts",
    loadState: "loading",
    hasLoaded: false,
  };
  const elements = {
    grid: document.querySelector("#watch-grid"),
    empty: document.querySelector("#compatibility-empty"),
    error: document.querySelector("#compatibility-error"),
    results: document.querySelector("#results-count"),
    search: document.querySelector("#watch-search"),
    status: document.querySelector("#status-filter"),
    family: document.querySelector("#family-filter"),
    sort: document.querySelector("#sort-filter"),
    form: document.querySelector("#compatibility-filters"),
    summaryModels: document.querySelector('[data-summary="models"]'),
    summaryModelLabel: document.querySelector('[data-summary-model-label]'),
    summarySuccesses: document.querySelector('[data-summary="successes"]'),
    summaryUpdated: document.querySelector('[data-summary="updated"]'),
    summaryUpdatedLine: document.querySelector('[data-summary-updated]'),
    summary: document.querySelector("#compatibility-summary"),
    summaryLoading: document.querySelector("[data-summary-loading]"),
    summaryContent: document.querySelector("[data-summary-content]"),
    evidenceNote: document.querySelector('[data-compatibility-evidence-note]'),
    statusList: document.querySelector("#compatibility-status-list"),
  };

  const { normalize, canonicalFamilyKey, familyOptions, filterByFamily, exactVariantLabel, publicModelName } = data;
  const statusCodes = ["VERIFIED", "SUPPORTED", "TESTED", "TESTING"];
  const statusOrder = statusCodes.reduce((result, status, index) => ({ ...result, [status]: index }), {});

  const statusLabel = (status) => locale.statuses[status]?.label || locale.card.unavailable;

  const statusDescription = (status) => locale.statuses[status]?.description || locale.card.unavailable;

  function createStatusBadge(status, ariaLabel = statusLabel(status)) {
    const statusClass = String(status).toLocaleLowerCase();
    return `<span class="status-badge status-${escapeHtml(statusClass)}" aria-label="${escapeHtml(ariaLabel)}"><span>${escapeHtml(statusLabel(status))}</span></span>`;
  }

  function renderStatusExplanations() {
    elements.statusList.innerHTML = statusCodes.map((status) => `
      <div class="compatibility-status-row">
        ${createStatusBadge(status)}
        <p>${escapeHtml(statusDescription(status))}</p>
      </div>`).join("");
  }

  const formatDate = (value) => {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.valueOf())) return "";
    return new Intl.DateTimeFormat(locale.dateLocale, { dateStyle: "medium" }).format(date);
  };

  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  function parseStat(row) {
    const attempted = Number(row.attemptedInstallations ?? row.attempted_install_count ?? row.attempted ?? 0);
    const successful = Number(row.successfulInstallations ?? row.successful_install_count ?? row.successful ?? 0);
    const failed = Number(row.failedInstallations ?? row.failed_install_count ?? row.failed ?? Math.max(0, attempted - successful));
    const rawStatus = String(row.status || row.evidenceStatus || row.calculated_status || "").toUpperCase();
    const status = ["TESTING", "TESTED", "SUPPORTED", "VERIFIED"].includes(rawStatus)
      ? rawStatus
      : null;
    return {
      model: String(row.model || "").trim(),
      compatibilityIdentity: String(row.compatibilityIdentity || row.compatibility_identity || row.model || "").trim(),
      variant: String(row.variant || "").trim(),
      caseSizeMm: Number.isFinite(Number(row.caseSizeMm ?? row.case_size_mm)) ? Number(row.caseSizeMm ?? row.case_size_mm) : null,
      displayType: String(row.displayType || row.display_type || "").trim(),
      attempted: Number.isFinite(attempted) ? attempted : 0,
      successful: Number.isFinite(successful) ? successful : 0,
      failed: Number.isFinite(failed) ? failed : 0,
      status,
      lastSuccess: row.lastSuccess || row.last_success || row.lastSuccessfulInstallation || row.last_successful_installation || null,
      family: String(row.family || "other").trim(),
      familyName: String(row.familyName || row.family_name || row.family || "Other").trim(),
      imageUrl: row.image?.url || row.imageUrl || null,
    };
  }

  function hydrateImages() {
    const images = [...elements.grid.querySelectorAll("img[data-remote-src]")];
    images.forEach((image) => {
      image.addEventListener("load", () => image.classList.add("is-ready"), { once: true });
      image.addEventListener("error", () => image.classList.add("is-ready"), { once: true });
      image.src = image.dataset.remoteSrc;
    });
  }

  function createCard(row) {
    const modelName = publicModelName(row.model);
    const variantLabel = row.variants[0] || exactVariantLabel(row) || "Smartwatch";
    const latestInstallation = formatDate(row.lastSuccess);
    const latestInstallationMarkup = latestInstallation
      ? `<p class="watch-card-meta">${escapeHtml(locale.card.latest)} ${escapeHtml(latestInstallation)}</p>`
      : "";
    const imageUrl = row.imageUrl || FALLBACK_IMAGE_URL;
    const installLabel = locale.successfulInstallLabel(row.successful);
    const accessibleName = [modelName, variantLabel, statusLabel(row.status), installLabel, latestInstallation && `${locale.card.latest} ${latestInstallation}`]
      .filter(Boolean)
      .join(", ");
    const imageMarkup = `<img data-remote-src="${escapeHtml(imageUrl)}" alt="" loading="lazy">`;
    return `
      <article class="watch-card" aria-label="${escapeHtml(accessibleName)}">
        <div class="watch-card-image">
          ${imageMarkup}
        </div>
        <div class="watch-card-body">
          <div class="watch-card-heading">
            <p class="watch-family">${escapeHtml(row.familyName || "Garmin")}</p>
            <div class="watch-card-model-row">
              <h3>${escapeHtml(modelName)}</h3>
              ${createStatusBadge(row.status, `${statusLabel(row.status)}: ${statusDescription(row.status)}`)}
            </div>
            <p class="watch-variant">${escapeHtml(variantLabel)}</p>
          </div>
          <p class="watch-install-count">${escapeHtml(installLabel)}</p>
          ${latestInstallationMarkup}
        </div>
      </article>`;
  }

  function render() {
    const query = normalize(state.search);
    const filtered = state.rows
      .filter((row) => state.status === "ALL" || row.status === state.status)
      .filter((row) => filterByFamily([row], state.family).length > 0)
      .filter((row) => !query || normalize(`${row.model} ${row.variants.join(" ")} ${row.familyName}`).includes(query))
      .sort((a, b) => {
        if (state.sort === "name") return a.model.localeCompare(b.model);
        if (state.sort === "successes") return b.successful - a.successful || b.attempted - a.attempted || a.model.localeCompare(b.model);
        if (state.sort === "status") return (statusOrder[a.status] ?? Number.MAX_SAFE_INTEGER) - (statusOrder[b.status] ?? Number.MAX_SAFE_INTEGER) || a.model.localeCompare(b.model);
        return b.attempted - a.attempted || b.successful - a.successful || a.model.localeCompare(b.model);
      });

    elements.grid.innerHTML = filtered.map(createCard).join("");
    hydrateImages();
    const ready = state.loadState === "ready";
    elements.empty.hidden = !ready || filtered.length > 0;
    elements.results.textContent = !ready
      ? ""
      : filtered.length === state.rows.length
        ? `${filtered.length.toLocaleString(locale.dateLocale)} ${filtered.length === 1 ? locale.results.modelOne : locale.results.modelMany}`
        : `${filtered.length.toLocaleString(locale.dateLocale)} ${locale.results.of} ${state.rows.length.toLocaleString(locale.dateLocale)} ${locale.results.modelMany}`;
    elements.grid.setAttribute("aria-busy", state.loadState === "loading" ? "true" : "false");
  }

  function populateFamilies() {
    elements.family.querySelectorAll("option:not(:first-child)").forEach((option) => option.remove());
    const families = familyOptions(state.rows);
    elements.family.insertAdjacentHTML("beforeend", families.map(([value, label]) =>
      `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`
    ).join(""));
  }

  function updateSummary() {
    const modelCount = state.rows.length;
    elements.summaryModels.textContent = modelCount.toLocaleString(locale.dateLocale);
    elements.summaryModelLabel.textContent = modelCount === 1 ? locale.summary.modelOne : locale.summary.modelMany;
    elements.summarySuccesses.textContent = state.rows.reduce((sum, row) => sum + row.successful, 0).toLocaleString(locale.dateLocale);
    const latest = state.rows
      .map((row) => row.lastSuccess)
      .filter(Boolean)
      .sort()
      .at(-1);
    const formattedLatest = formatDate(latest);
    if (formattedLatest) {
      elements.summaryUpdated.textContent = formattedLatest;
      elements.summaryUpdatedLine.hidden = false;
    } else {
      elements.summaryUpdatedLine.hidden = true;
    }
  }

  function mergeRows(stats) {
    return stats
      .filter((row) => row.attempted > 0)
      .map((row) => ({
        ...row,
        family: canonicalFamilyKey(row.family || row.familyName),
        variants: [exactVariantLabel(row)].filter(Boolean),
        imageUrl: row.imageUrl || FALLBACK_IMAGE_URL,
      }))
      .filter((row) => row.status);
  }

  function setSettledState(loadState) {
    state.loadState = loadState;
    elements.summaryLoading.hidden = true;
    elements.summaryLoading.style.display = "none";
    elements.summaryContent.hidden = loadState !== "ready";
    elements.summaryContent.style.display = loadState === "ready" ? "" : "none";
    elements.summary.setAttribute("aria-busy", "false");
    elements.grid.setAttribute("aria-busy", "false");
  }

  function readSnapshot() {
    const snapshotElement = document.querySelector("#compatibility-snapshot");
    if (!snapshotElement) return null;
    try {
      const payload = JSON.parse(snapshotElement.textContent || "{}");
      return payload.schemaVersion === 1 && Array.isArray(payload.models) ? payload : null;
    } catch {
      return null;
    }
  }

  function initializeSnapshot() {
    const snapshot = readSnapshot();
    if (!snapshot) return false;
    try {
      state.rows = mergeRows(snapshot.models.map(parseStat));
      state.hasLoaded = true;
      populateFamilies();
      updateSummary();
      elements.error.hidden = true;
      setSettledState("ready");
      render();
      return true;
    } catch {
      return false;
    }
  }

  async function load({ quiet = false } = {}) {
    try {
      const refreshToken = Date.now();
      const publicStatsResponse = await fetch(`${API_ORIGIN}/compatibility/public/models.json?limit=500&refresh=${refreshToken}`, { cache: "no-store", headers: { Accept: "application/json" } });
      let stats = [];
      if (publicStatsResponse.ok) {
        const payload = await publicStatsResponse.json();
        if (!Array.isArray(payload.models)) throw new Error("invalid_compatibility_response");
        stats = payload.models.map(parseStat);
      } else if (isLocalPreview) {
        stats = previewStats.map(parseStat);
      } else {
        throw new Error(`compatibility_http_${publicStatsResponse.status}`);
      }
      state.rows = mergeRows(stats);
      state.hasLoaded = true;
      populateFamilies();
      updateSummary();
      elements.error.hidden = true;
      setSettledState("ready");
      render();
    } catch (error) {
      const preserveExistingResults = quiet && state.hasLoaded;
      if (!preserveExistingResults) {
        setSettledState("error");
        elements.error.hidden = false;
        render();
      }
      console.error("Terento compatibility results failed", error);
    }
  }

  elements.form.addEventListener("submit", (event) => event.preventDefault());
  elements.search.addEventListener("input", (event) => { state.search = event.target.value; render(); });
  elements.status.addEventListener("change", (event) => { state.status = event.target.value; render(); });
  elements.family.addEventListener("change", (event) => { state.family = event.target.value; render(); });
  elements.sort.addEventListener("change", (event) => { state.sort = event.target.value; render(); });
  if (elements.evidenceNote && locale.evidenceNote) elements.evidenceNote.textContent = locale.evidenceNote;
  renderStatusExplanations();
  const hasSnapshot = initializeSnapshot();
  if (!hasSnapshot) render();
  load({ quiet: hasSnapshot });
  // Public evidence is deliberately cached at the API edge, so a quiet
  // refresh uses a cache-busting query and keeps model counts/statuses current
  // while the page remains open. Existing filters stay in the local state.
  window.setInterval(() => load({ quiet: true }), 60_000);
})();
