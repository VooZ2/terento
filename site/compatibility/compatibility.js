(() => {
  const data = globalThis.TerentoCompatibilityData;
  const locale = globalThis.TerentoCompatibilityLocale;
  if (!data) throw new Error("compatibility_data_unavailable");
  if (!locale) throw new Error("compatibility_locale_unavailable");

  const API_ORIGIN = "https://api.terento.app";
  const FALLBACK_IMAGE_URL = "/assets/generic-garmin-watch.png?v=20260826-1";
  const isLocalPreview = ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
  const state = {
    rows: [],
    search: "",
    successfulRange: "ALL",
    family: "ALL",
    sort: "successful",
    loadState: "ready",
    hasLoaded: false,
    generatedAt: null,
  };

  const elements = {
    grid: document.querySelector("#watch-grid"),
    empty: document.querySelector("#compatibility-empty"),
    error: document.querySelector("#compatibility-error"),
    results: document.querySelector("#results-count"),
    search: document.querySelector("#watch-search"),
    successfulRange: document.querySelector("#successful-install-filter"),
    family: document.querySelector("#family-filter"),
    sort: document.querySelector("#sort-filter"),
    form: document.querySelector("#compatibility-filters"),
    summaryModels: document.querySelector('[data-summary="models"]'),
    summaryModelLabel: document.querySelector('[data-summary-model-label]'),
    summarySuccesses: document.querySelector('[data-summary="successes"]'),
    summaryUpdated: document.querySelector('[data-summary="updated"]'),
    summaryUpdatedLine: document.querySelector('[data-summary-updated]'),
    summary: document.querySelector("#compatibility-summary"),
    summaryContent: document.querySelector("[data-summary-content]"),
    evidenceNote: document.querySelector('[data-compatibility-evidence-note]'),
    freshnessLine: document.querySelector(".compatibility-freshness"),
    freshness: document.querySelector("#compatibility-freshness"),
    retry: document.querySelector("#compatibility-retry"),
    clear: document.querySelector("#compatibility-clear"),
  };

  const { normalize, canonicalFamilyKey, familyOptions, filterByFamily, exactVariantLabel, publicModelName } = data;

  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const formatDate = (value) => {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.valueOf())) return "";
    return new Intl.DateTimeFormat(locale.dateLocale, { dateStyle: "medium" }).format(date);
  };

  function parseStat(row) {
    const successful = Number(row.successfulInstallations ?? row.successful_install_count ?? row.successful ?? 0);
    return {
      model: String(row.model || "").trim(),
      compatibilityIdentity: String(row.compatibilityIdentity || row.compatibility_identity || row.model || "").trim(),
      variant: String(row.variant || "").trim(),
      caseSizeMm: Number.isFinite(Number(row.caseSizeMm ?? row.case_size_mm)) ? Number(row.caseSizeMm ?? row.case_size_mm) : null,
      displayType: String(row.displayType || row.display_type || "").trim(),
      screenTechnology: row.screenTechnology ?? row.screen_technology,
      solar: row.solar,
      inReach: row.inReach ?? row.inreach,
      successful: Number.isFinite(successful) ? successful : 0,
      lastSuccess: row.lastSuccess || row.last_success || row.lastSuccessfulInstallation || row.last_successful_installation || null,
      family: String(row.family || "other").trim(),
      familyName: String(row.familyName || row.family_name || row.family || "Other").trim(),
      imageUrl: row.imageUrl || row.image?.url || null,
    };
  }

  function normalizePublicRows(stats) {
    return stats
      .map(parseStat)
      .filter((row) => row.successful > 0)
      .map((row) => ({
        ...row,
        family: canonicalFamilyKey(row.family || row.familyName),
        variants: [exactVariantLabel(row)].filter(Boolean),
        imageUrl: row.imageUrl || FALLBACK_IMAGE_URL,
      }));
  }

  function hydrateImages() {
    [...elements.grid.querySelectorAll("img[data-remote-src]")].forEach((image) => {
      image.addEventListener("load", () => image.classList.add("is-ready"), { once: true });
      image.addEventListener("error", () => image.classList.add("is-ready"), { once: true });
      if (image.src !== image.dataset.remoteSrc) image.src = image.dataset.remoteSrc;
    });
  }

  function createCard(row) {
    const modelName = publicModelName(row.model);
    const variantLabel = row.variants[0] || exactVariantLabel(row) || locale.card.smartwatch;
    const latestInstallation = formatDate(row.lastSuccess);
    const latestInstallationMarkup = latestInstallation
      ? `<p class="watch-card-meta">${escapeHtml(locale.card.latest)} ${escapeHtml(latestInstallation)}</p>`
      : "";
    const installLabel = locale.successfulInstallLabel(row.successful);
    const accessibleName = [modelName, variantLabel, installLabel, latestInstallation && `${locale.card.latest} ${latestInstallation}`]
      .filter(Boolean)
      .join(", ");
    const imageUrl = row.imageUrl || FALLBACK_IMAGE_URL;
    return `<article class="watch-card" aria-label="${escapeHtml(accessibleName)}"><div class="watch-card-image"><img data-remote-src="${escapeHtml(imageUrl)}" src="${escapeHtml(imageUrl)}" alt="" loading="lazy"></div><div class="watch-card-body"><div class="watch-card-heading"><p class="watch-family">${escapeHtml(row.familyName || "Garmin")}</p><div class="watch-card-model-row"><h3>${escapeHtml(modelName)}</h3></div><p class="watch-variant">${escapeHtml(variantLabel)}</p></div><p class="watch-install-count">${escapeHtml(installLabel)}</p>${latestInstallationMarkup}</div></article>`;
  }

  function matchesSuccessfulRange(row) {
    if (state.successfulRange === "1_2") return row.successful >= 1 && row.successful <= 2;
    if (state.successfulRange === "3_4") return row.successful >= 3 && row.successful <= 4;
    if (state.successfulRange === "5_PLUS") return row.successful >= 5;
    return true;
  }

  function render() {
    const query = normalize(state.search);
    const filtered = state.rows
      .filter(matchesSuccessfulRange)
      .filter((row) => filterByFamily([row], state.family).length > 0)
      .filter((row) => !query || normalize(`${row.model} ${row.variants.join(" ")} ${row.familyName}`).includes(query))
      .sort((a, b) => {
        if (state.sort === "name") return publicModelName(a.model).localeCompare(publicModelName(b.model)) || a.model.localeCompare(b.model);
        return b.successful - a.successful || publicModelName(a.model).localeCompare(publicModelName(b.model)) || a.compatibilityIdentity.localeCompare(b.compatibilityIdentity);
      });

    elements.grid.innerHTML = filtered.map(createCard).join("");
    hydrateImages();
    const ready = state.loadState === "ready";
    elements.empty.hidden = !ready || filtered.length > 0;
    elements.empty.textContent = locale.freshness.noMatch;
    elements.results.textContent = !ready
      ? ""
      : filtered.length === state.rows.length
        ? `${filtered.length.toLocaleString(locale.dateLocale)} ${filtered.length === 1 ? locale.results.modelOne : locale.results.modelMany}`
        : `${filtered.length.toLocaleString(locale.dateLocale)} ${locale.results.of} ${state.rows.length.toLocaleString(locale.dateLocale)} ${locale.results.modelMany}`;
    elements.grid.setAttribute("aria-busy", "false");
  }

  function populateFamilies() {
    elements.family.querySelectorAll("option:not(:first-child)").forEach((option) => option.remove());
    const families = familyOptions(state.rows);
    elements.family.insertAdjacentHTML("beforeend", families.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join(""));
    const familyOption = [...elements.family.querySelectorAll("option")].find((option) => option.value === state.family);
    if (!familyOption) state.family = "ALL";
    elements.family.value = state.family;
  }

  function updateSummary() {
    const modelCount = state.rows.length;
    elements.summaryModels.textContent = modelCount.toLocaleString(locale.dateLocale);
    elements.summaryModelLabel.textContent = modelCount === 1 ? locale.summary.modelOne : locale.summary.modelMany;
    elements.summarySuccesses.textContent = state.rows.reduce((sum, row) => sum + row.successful, 0).toLocaleString(locale.dateLocale);
    const latest = state.rows.map((row) => row.lastSuccess).filter(Boolean).sort().at(-1);
    const formattedLatest = formatDate(latest);
    if (formattedLatest) {
      elements.summaryUpdated.textContent = formattedLatest;
      elements.summaryUpdated.dateTime = latest;
      elements.summaryUpdatedLine.hidden = false;
    } else {
      elements.summaryUpdatedLine.hidden = true;
    }
  }

  function setSettledState(loadState) {
    state.loadState = loadState;
    elements.summaryContent.hidden = false;
    elements.summary.setAttribute("aria-busy", "false");
    elements.grid.setAttribute("aria-busy", "false");
  }

  function setFreshnessMessage(message) {
    if (!elements.freshnessLine || !elements.freshness) return;
    elements.freshness.textContent = message;
    elements.freshnessLine.hidden = !message;
  }

  async function load({ quiet = false } = {}) {
    try {
      const refreshToken = Date.now();
      const response = await fetch(`${API_ORIGIN}/compatibility/public/models.json?limit=500&refresh=${refreshToken}`, { cache: "no-store", headers: { Accept: "application/json" }, signal: typeof AbortSignal !== "undefined" && AbortSignal.timeout ? AbortSignal.timeout(15000) : undefined });
      let stats = [];
      if (response.ok) {
        const payload = await response.json();
        if (!Array.isArray(payload.models)) throw new Error("invalid_compatibility_response");
        stats = payload.models;
        state.generatedAt = payload.generatedAt;
      } else if (isLocalPreview && !state.hasLoaded) {
        stats = [{ model: "fēnix 8", successfulInstallations: 1, lastSuccessfulInstallation: "2026-08-24T21:34:17Z", family: "fenix", familyName: "fēnix" }];
      } else {
        throw new Error(`compatibility_http_${response.status}`);
      }
      const publicRows = normalizePublicRows(stats);
      if (!publicRows.length && state.rows.length) throw new Error("empty_compatibility_response");
      state.rows = publicRows;
      state.hasLoaded = true;
      populateFamilies();
      updateSummary();
      elements.error.hidden = true;
      if (elements.retry) elements.retry.hidden = true;
      setFreshnessMessage("");
      setSettledState("ready");
      render();
    } catch (error) {
      const preserveExistingResults = state.hasLoaded || quiet;
      setFreshnessMessage(state.hasLoaded ? `${locale.freshness.stale} ${locale.freshness.lastLoaded}: ${formatDate(state.generatedAt)}` : locale.freshness.unavailable);
      if (elements.retry) elements.retry.hidden = false;
      if (!preserveExistingResults) {
        setSettledState("error");
        elements.error.hidden = false;
        render();
      }
      console.error("Terento compatibility results failed", error);
    }
  }

  function initializeSnapshot() {
    const snapshotElement = document.querySelector("#compatibility-snapshot");
    if (!snapshotElement) return;
    try {
      const snapshot = JSON.parse(snapshotElement.textContent || "{}");
      if (!Array.isArray(snapshot.models)) return;
      state.rows = normalizePublicRows(snapshot.models);
      state.generatedAt = snapshot.generatedAt || null;
      state.hasLoaded = true;
      populateFamilies();
      updateSummary();
      setSettledState("ready");
      render();
    } catch (error) {
      console.error("Terento compatibility snapshot failed", error);
    }
  }

  elements.retry?.addEventListener("click", () => load({ quiet: state.hasLoaded }));
  elements.clear?.addEventListener("click", () => {
    state.search = elements.search.value = "";
    state.successfulRange = elements.successfulRange.value = "ALL";
    state.family = elements.family.value = "ALL";
    state.sort = elements.sort.value = "successful";
    render();
    elements.search.focus();
  });
  elements.form.addEventListener("submit", (event) => event.preventDefault());
  elements.search.addEventListener("input", (event) => { state.search = event.target.value; render(); });
  elements.successfulRange.addEventListener("change", (event) => { state.successfulRange = event.target.value; render(); });
  elements.family.addEventListener("change", (event) => { state.family = event.target.value; render(); });
  elements.sort.addEventListener("change", (event) => { state.sort = event.target.value; render(); });
  if (elements.evidenceNote && locale.evidenceNote) elements.evidenceNote.textContent = locale.evidenceNote;
  initializeSnapshot();
  if (!state.hasLoaded) render();
  load({ quiet: state.hasLoaded });
  window.setInterval(() => load({ quiet: true }), 60_000);
})();
