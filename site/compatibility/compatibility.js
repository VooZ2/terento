(() => {
  const API_ORIGIN = "https://api.terento.app";
  const isLocalPreview = ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
  const previewStats = [
    {
      model: "fēnix 8",
      attempted: 2,
      successful: 2,
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
  };
  const transparentImageCache = new Map();

  // A small, reviewed source fallback keeps a newly verified model visible
  // while its normalized API asset is going through the separate asset review
  // workflow. The browser downloads this official Garmin media directly; the
  // API never proxies or hosts it.
  const officialImageFallbacks = new Map([
    ["garmin-fenix-8-51-amoled", "https://res.garmin.com/en/products/010-02905-10/v/cf-lg.jpg"],
  ]);

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
  };

  const normalize = (value) => String(value || "")
    .trim()
    .toLocaleLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");

  const statusLabel = (status) => ({
    VERIFIED: "Verified",
    SUPPORTED: "Supported",
    TESTED: "Tested",
    TESTING: "Testing",
    UNKNOWN: "Unknown",
  }[status] || "Unknown");

  const statusDescription = (status) => ({
    TESTED: "Real hardware evidence exists for this model, but it is not yet a full support claim.",
    SUPPORTED: "A real map installation completed successfully for this exact model.",
    VERIFIED: "Confirmed across multiple physical devices and firmware versions.",
    TESTING: "This exact device is currently under validation or has only partial evidence.",
    UNKNOWN: "This exact device is known, but Terento does not have enough real hardware evidence yet.",
  }[status] || "Compatibility evidence is not available yet.");

  const formatDate = (value) => {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.valueOf())) return "";
    return new Intl.DateTimeFormat("en", { dateStyle: "medium" }).format(date);
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
    return {
      model: String(row.model || "").trim(),
      compatibilityIdentity: String(row.compatibilityIdentity || row.compatibility_identity || row.model || "").trim(),
      variant: String(row.variant || "").trim(),
      caseSizeMm: Number.isFinite(Number(row.caseSizeMm ?? row.case_size_mm)) ? Number(row.caseSizeMm ?? row.case_size_mm) : null,
      displayType: String(row.displayType || row.display_type || "").trim(),
      attempted: Number.isFinite(attempted) ? attempted : 0,
      successful: Number.isFinite(successful) ? successful : 0,
      failed: Number.isFinite(failed) ? failed : 0,
      status: String(row.status || row.evidenceStatus || row.calculated_status || (successful > 0 ? "SUPPORTED" : attempted > 0 ? "TESTING" : "UNKNOWN")).toUpperCase(),
      lastSuccess: row.lastSuccess || row.last_success || row.lastSuccessfulInstallation || row.last_successful_installation || null,
    };
  }

  function parseModelIdentity(value) {
    const normalized = normalize(value).replace(/^garmin\s+/, "");
    const sizeMatch = normalized.match(/\b(\d{2})\s*mm\b/);
    const displayMatch = normalized.match(/\b(amoled|solar|microled)\b/);
    const base = normalized
      .replace(/\b\d{2}\s*mm\b/g, " ")
      .replace(/\b(?:amoled|solar|microled)\b/g, " ")
      .replace(/[·–—-]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    return {
      base,
      size: sizeMatch ? Number(sizeMatch[1]) : null,
      display: displayMatch ? displayMatch[1] : "",
    };
  }

  function catalogKey(identity, size = identity.size, display = identity.display) {
    return [identity.base, size || "", display || ""].join("|");
  }

  function catalogEntry(device, imageUrl) {
    return {
      model: device.model,
      family: device.family || "other",
      familyName: device.familyName || device.family || "Other",
      variants: device.variant ? [device.variant] : [],
      caseSizeMm: device.caseSizeMm ?? null,
      displayType: device.displayType || "",
      imageUrl,
    };
  }

  function metricText(row) {
    if (row.successful < 1) return "No successful installs yet";
    return `${row.successful} successful install${row.successful === 1 ? "" : "s"}`;
  }

  async function transparentImageData(url) {
    if (transparentImageCache.has(url)) return transparentImageCache.get(url);
    const response = await fetch(url, { mode: "cors" });
    if (!response.ok) throw new Error("image_unavailable");
    const bitmap = await createImageBitmap(await response.blob());
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) throw new Error("canvas_unavailable");
    context.drawImage(bitmap, 0, 0);
    bitmap.close();
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
    for (let index = 0; index < pixels.data.length; index += 4) {
      const pixelY = Math.floor(index / 4 / canvas.width);
      const red = pixels.data[index];
      const green = pixels.data[index + 1];
      const blue = pixels.data[index + 2];
      const minimum = Math.min(red, green, blue);
      const maximum = Math.max(red, green, blue);
      const neutral = maximum - minimum < 18;
      const lowerShadow = pixelY > canvas.height * 0.84 && neutral && minimum > 130;
      if (lowerShadow) {
        pixels.data[index + 3] = 0;
      } else if (neutral && minimum > 224) {
        pixels.data[index + 3] = Math.max(0, Math.min(255, (238 - minimum) * 18));
      }
    }
    context.putImageData(pixels, 0, 0);
    const dataUrl = canvas.toDataURL("image/png");
    transparentImageCache.set(url, dataUrl);
    return dataUrl;
  }

  function hydrateImages() {
    const images = [...elements.grid.querySelectorAll("img[data-remote-src]")];
    images.forEach(async (image) => {
      try {
        image.src = await transparentImageData(image.dataset.remoteSrc);
      } catch (error) {
        image.src = image.dataset.remoteSrc;
      } finally {
        image.classList.add("is-ready");
      }
    });
  }

  function createCard(row) {
    const variantLabel = row.variants.length > 3
      ? `${row.variants.length} variants`
      : (row.variants.join(" · ") || "Smartwatch");
    const statusClass = row.status.toLocaleLowerCase();
    const lastTested = formatDate(row.lastSuccess);
    const lastTestedMarkup = lastTested
      ? `<p class="watch-card-meta">Last tested ${escapeHtml(lastTested)}</p>`
      : "";
    return `
      <article class="watch-card">
        <div class="watch-card-image">
          <img data-remote-src="${escapeHtml(row.imageUrl)}" alt="${escapeHtml(row.model)}" loading="lazy">
        </div>
        <div class="watch-card-body">
          <div class="watch-card-heading">
            <div>
              <p class="watch-family">${escapeHtml(row.familyName || "Garmin")}</p>
              <h3>${escapeHtml(row.model)}</h3>
              <p class="watch-variant">${escapeHtml(variantLabel)}</p>
            </div>
            <span class="status-badge status-${escapeHtml(statusClass)}" aria-label="${escapeHtml(statusLabel(row.status))}: ${escapeHtml(statusDescription(row.status))}"><span>${statusLabel(row.status)}</span></span>
          </div>
          <p class="watch-install-count">${escapeHtml(metricText(row))}</p>
          ${lastTestedMarkup}
        </div>
      </article>`;
  }

  function render() {
    const query = normalize(state.search);
    const filtered = state.rows
      .filter((row) => state.status === "ALL" || row.status === state.status)
      .filter((row) => state.family === "ALL" || row.family === state.family)
      .filter((row) => !query || normalize(`${row.model} ${row.variants.join(" ")} ${row.familyName}`).includes(query))
      .sort((a, b) => {
        if (state.sort === "name") return a.model.localeCompare(b.model);
        if (state.sort === "successes") return b.successful - a.successful || b.attempted - a.attempted || a.model.localeCompare(b.model);
        if (state.sort === "status") return statusLabel(a.status).localeCompare(statusLabel(b.status)) || a.model.localeCompare(b.model);
        return b.attempted - a.attempted || b.successful - a.successful || a.model.localeCompare(b.model);
      });

    elements.grid.innerHTML = filtered.map(createCard).join("");
    hydrateImages();
    elements.empty.hidden = filtered.length > 0;
    elements.results.textContent = filtered.length === state.rows.length
      ? `${filtered.length} ${filtered.length === 1 ? "model" : "models"}`
      : `${filtered.length} of ${state.rows.length} models`;
    elements.grid.setAttribute("aria-busy", "false");
  }

  function populateFamilies() {
    elements.family.querySelectorAll("option:not(:first-child)").forEach((option) => option.remove());
    const families = [...new Map(state.rows.map((row) => [row.family, row.familyName])).entries()]
      .sort((a, b) => a[1].localeCompare(b[1]));
    elements.family.insertAdjacentHTML("beforeend", families.map(([value, label]) =>
      `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`
    ).join(""));
  }

  function updateSummary() {
    const modelCount = state.rows.length;
    elements.summaryModels.textContent = modelCount.toLocaleString("en");
    elements.summaryModelLabel.textContent = modelCount === 1 ? "model with evidence" : "models with evidence";
    elements.summarySuccesses.textContent = state.rows.reduce((sum, row) => sum + row.successful, 0).toLocaleString("en");
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

  function catalogImages(devices) {
    const models = new Map();
    for (const device of devices) {
      const imageUrl = device.asset?.status === "AVAILABLE" && device.asset.url
        ? device.asset.url
        : device.sourceAsset?.url || officialImageFallbacks.get(device.id);
      if (!imageUrl) continue;
      const identity = parseModelIdentity(device.model || device.canonicalModel);
      if (!identity.base) continue;
      const exactKey = catalogKey(identity, device.caseSizeMm, normalize(device.displayType));
      const sizeKey = catalogKey(identity, device.caseSizeMm, "");
      const modelKey = catalogKey(identity, null, "");
      const entry = catalogEntry(device, imageUrl);
      // Exact variant and size keys are intentionally never overwritten by a
      // less-specific catalog record. The model key remains a fallback only
      // for evidence that did not include a size.
      if (!models.has(exactKey)) models.set(exactKey, entry);
      if (device.caseSizeMm && !models.has(sizeKey)) models.set(sizeKey, entry);
      if (!models.has(modelKey)) models.set(modelKey, entry);
    }
    return models;
  }

  function mergeRows(devices, stats) {
    const images = catalogImages(devices);
    return stats
      .filter((row) => row.attempted > 0)
      .map((row) => {
        const identity = parseModelIdentity(row.compatibilityIdentity || row.model);
        if (!identity.base) return null;
        const size = row.caseSizeMm || identity.size;
        const display = normalize(row.displayType || identity.display);
        const exactKey = catalogKey(identity, size, display);
        const sizeKey = catalogKey(identity, size, "");
        const modelKey = catalogKey(identity, null, "");
        const catalog = images.get(exactKey)
          || (identity.size ? images.get(sizeKey) : images.get(modelKey));
        if (!catalog) return null;
        return {
          ...row,
          ...catalog,
          model: catalog.model || row.model,
          variants: row.variant ? [row.variant] : catalog.variants,
        };
      })
      .filter(Boolean);
  }

  async function load({ quiet = false } = {}) {
    try {
      const refreshToken = Date.now();
      const [catalogResponse, publicStatsResponse] = await Promise.all([
        fetch(`${API_ORIGIN}/devices/catalog.json?refresh=${refreshToken}`, { cache: "no-store", headers: { Accept: "application/json" } }),
        fetch(`${API_ORIGIN}/compatibility/public/top-models.json?limit=500&refresh=${refreshToken}`, { cache: "no-store", headers: { Accept: "application/json" } }),
      ]);
      if (!catalogResponse.ok) throw new Error("catalog_unavailable");
      const catalog = await catalogResponse.json();
      let stats = [];
      if (publicStatsResponse.ok) {
        const payload = await publicStatsResponse.json();
        stats = Array.isArray(payload.models) ? payload.models.map(parseStat) : [];
      } else if (isLocalPreview) {
        stats = previewStats.map(parseStat);
      }
      const devices = Array.isArray(catalog.devices) ? catalog.devices : [];
      state.rows = mergeRows(devices, stats);
      populateFamilies();
      updateSummary();
      render();
    } catch (error) {
      if (!quiet) {
        elements.grid.setAttribute("aria-busy", "false");
        elements.error.hidden = false;
      }
      console.error("Terento compatibility results failed", error);
    }
  }

  elements.form.addEventListener("submit", (event) => event.preventDefault());
  elements.search.addEventListener("input", (event) => { state.search = event.target.value; render(); });
  elements.status.addEventListener("change", (event) => { state.status = event.target.value; render(); });
  elements.family.addEventListener("change", (event) => { state.family = event.target.value; render(); });
  elements.sort.addEventListener("change", (event) => { state.sort = event.target.value; render(); });
  load();
  // Public evidence is deliberately cached at the API edge, so a quiet
  // refresh uses a cache-busting query and keeps model counts/statuses current
  // while the page remains open. Existing filters stay in the local state.
  window.setInterval(() => load({ quiet: true }), 60_000);
})();
