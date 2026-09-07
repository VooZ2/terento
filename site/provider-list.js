(() => {
  const cards = [...document.querySelectorAll("[data-provider-card]")];
  if (!cards.length) return;

  const API_URL = "https://api.terento.app/maps/catalog.json";
  const PUBLIC_PROVIDER_IDS = new Set(["freizeitkarte", "opentopomap"]);

  const render = (providers) => {
    const activeProviders = new Map(providers
      .filter((provider) => PUBLIC_PROVIDER_IDS.has(String(provider?.id || "").trim().toLowerCase()))
      .filter((provider) => String(provider?.status || "").toUpperCase() === "ACTIVE")
      .map((provider) => [String(provider.id).trim().toLowerCase(), provider]));

    cards.forEach((card) => {
      const cardID = String(card.dataset.providerCard || "").trim().toLowerCase();
      const isContourCard = cardID === "opentopomap-contours";
      const provider = activeProviders.get(isContourCard ? "opentopomap" : cardID);
      card.hidden = !provider;
      if (!provider) return;

      const maps = Array.isArray(provider.maps)
        ? provider.maps.filter((map) => String(map?.availability || "").toUpperCase() === "AVAILABLE")
        : [];
      const countElement = card.querySelector("[data-provider-count]");
      if (!countElement) return;
      if (!maps.length) {
        if (isContourCard) card.hidden = true;
        return;
      }

      if (isContourCard) {
        const contourCount = maps.filter((map) => Array.isArray(map?.artifacts)
          && map.artifacts.some((artifact) => String(artifact?.kind || "").toLowerCase() === "contours"
            && String(artifact?.validationStatus || artifact?.validationState || "").toUpperCase() === "VALIDATED"))
          .length;
        card.hidden = contourCount === 0;
        if (contourCount === 0) return;
        countElement.textContent = countElement.dataset.countTemplate
          .replace("{count}", String(contourCount));
        return;
      }

      const countries = new Set(maps
        .map((map) => String(map?.country || "").trim())
        .filter(Boolean));
      const template = countElement.dataset.countTemplate || "{count} map packages";
      countElement.textContent = template
        .replace("{count}", String(maps.length))
        .replace("{countries}", String(countries.size));
    });
  };

  fetch(API_URL, { headers: { Accept: "application/json" } })
    .then((response) => response.ok ? response.json() : Promise.reject(new Error("provider_catalog_unavailable")))
    .then((payload) => Array.isArray(payload?.providers) && render(payload.providers))
    .catch(() => {
      // The server-rendered list remains visible when the catalog is unavailable.
    });
})();
