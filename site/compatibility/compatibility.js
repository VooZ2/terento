(() => {
  const data = globalThis.TerentoCompatibilityData;
  const locale = globalThis.TerentoCompatibilityLocale;
  if (!data) throw new Error("compatibility_data_unavailable");
  if (!locale) throw new Error("compatibility_locale_unavailable");

  const API_ORIGIN = "https://api.terento.app";
  const FALLBACK_IMAGE_URL = "/assets/generic-garmin-watch.png?v=20260826-1";
  // Font Awesome Free 7.3.1 solid `laptop` and `globe`: unchanged viewBox and path
  // data with the attribution comment. Keep in sync with scripts/build-compatibility-pages.py.
  const SOURCE_ICONS = {
    app: '<svg class="watch-install-source-icon" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" d="M128 32C92.7 32 64 60.7 64 96l0 240 64 0 0-240 384 0 0 240 64 0 0-240c0-35.3-28.7-64-64-64L128 32zM19.2 384C8.6 384 0 392.6 0 403.2 0 445.6 34.4 480 76.8 480l486.4 0c42.4 0 76.8-34.4 76.8-76.8 0-10.6-8.6-19.2-19.2-19.2L19.2 384z"/></svg>',
    web: '<svg class="watch-install-source-icon" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><!--! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2026 Fonticons, Inc. --><path fill="currentColor" d="M351.9 280l-190.9 0c2.9 64.5 17.2 123.9 37.5 167.4 11.4 24.5 23.7 41.8 35.1 52.4 11.2 10.5 18.9 12.2 22.9 12.2s11.7-1.7 22.9-12.2c11.4-10.6 23.7-28 35.1-52.4 20.3-43.5 34.6-102.9 37.5-167.4zM160.9 232l190.9 0C349 167.5 334.7 108.1 314.4 64.6 303 40.2 290.7 22.8 279.3 12.2 268.1 1.7 260.4 0 256.4 0s-11.7 1.7-22.9 12.2c-11.4 10.6-23.7 28-35.1 52.4-20.3 43.5-34.6 102.9-37.5 167.4zm-48 0C116.4 146.4 138.5 66.9 170.8 14.7 78.7 47.3 10.9 131.2 1.5 232l111.4 0zM1.5 280c9.4 100.8 77.2 184.7 169.3 217.3-32.3-52.2-54.4-131.7-57.9-217.3L1.5 280zm398.4 0c-3.5 85.6-25.6 165.1-57.9 217.3 92.1-32.7 159.9-116.5 169.3-217.3l-111.4 0zm111.4-48C501.9 131.2 434.1 47.3 342 14.7 374.3 66.9 396.4 146.4 399.9 232l111.4 0z"/></svg>',
  };
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

  const sourceCount = (value) => {
    const count = Number(value);
    return value !== null && value !== undefined && Number.isFinite(count) && count >= 0 ? Math.floor(count) : null;
  };

  function parseStat(row) {
    const successful = Number(row.successfulInstallations ?? row.successful_install_count ?? row.successful ?? 0);
    const total = Number.isFinite(successful) ? successful : 0;
    // Older snapshots and payloads have no app/web split: count everything as app.
    let app = sourceCount(row.appSuccessfulInstallations);
    let web = sourceCount(row.webSuccessfulInstallations);
    if (app === null && web === null) [app, web] = [total, 0];
    else if (app === null) app = Math.max(total - web, 0);
    else if (web === null) web = Math.max(total - app, 0);
    return {
      model: String(row.model || "").trim(),
      compatibilityIdentity: String(row.compatibilityIdentity || row.compatibility_identity || row.model || "").trim(),
      variant: String(row.variant || "").trim(),
      caseSizeMm: Number.isFinite(Number(row.caseSizeMm ?? row.case_size_mm)) ? Number(row.caseSizeMm ?? row.case_size_mm) : null,
      displayType: String(row.displayType || row.display_type || "").trim(),
      screenTechnology: row.screenTechnology ?? row.screen_technology,
      solar: row.solar,
      inReach: row.inReach ?? row.inreach,
      successful: total,
      appSuccessful: app,
      webSuccessful: web,
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
    const sources = [["app", row.appSuccessful], ["web", row.webSuccessful]]
      .filter(([, count]) => count > 0)
      .map(([source, count]) => ({ source, text: locale.cardCount(count) }));
    const sourcesMarkup = sources.length
      ? `<p class="watch-install-sources">${sources.map(({ source, text }) => `<span class="watch-install-source">${SOURCE_ICONS[source]}${escapeHtml(locale.sources[source])} ${escapeHtml(text)}</span>`).join(" ")}</p>`
      : "";
    const sourcesLabel = sources.map(({ source, text }) => locale.sources[`${source}Label`](text)).join(", ");
    const accessibleName = [modelName, variantLabel, installLabel, sourcesLabel, latestInstallation && `${locale.card.latest} ${latestInstallation}`]
      .filter(Boolean)
      .join(", ");
    const imageUrl = row.imageUrl || FALLBACK_IMAGE_URL;
    return `<article class="watch-card" aria-label="${escapeHtml(accessibleName)}"><div class="watch-card-image"><img data-remote-src="${escapeHtml(imageUrl)}" src="${escapeHtml(imageUrl)}" alt="" loading="lazy"></div><div class="watch-card-body"><div class="watch-card-heading"><p class="watch-family">${escapeHtml(row.familyName || "Garmin")}</p><div class="watch-card-model-row"><h3>${escapeHtml(modelName)}</h3></div><p class="watch-variant">${escapeHtml(variantLabel)}</p></div><p class="watch-install-count">${escapeHtml(installLabel)}</p>${sourcesMarkup}${latestInstallationMarkup}</div></article>`;
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
