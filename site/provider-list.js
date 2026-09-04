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
      const provider = activeProviders.get(String(card.dataset.providerCard || "").trim().toLowerCase());
      card.hidden = !provider;
      if (!provider) return;

      const maps = Array.isArray(provider.maps)
        ? provider.maps.filter((map) => String(map?.availability || "").toUpperCase() === "AVAILABLE")
        : [];
      const countElement = card.querySelector("[data-provider-count]");
      if (!countElement || !maps.length) return;

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
