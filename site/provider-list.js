(() => {
  const lists = [...document.querySelectorAll("[data-provider-list]")];
  if (!lists.length) return;

  const API_URL = "https://api.terento.app/maps/catalog.json";

  const render = (providers) => {
    const names = providers
      .filter((provider) => String(provider?.status || "").toUpperCase() === "ACTIVE")
      .map((provider) => String(provider?.name || "").trim())
      .filter(Boolean);
    if (!names.length) return;
    lists.forEach((list) => {
      list.replaceChildren(...names.map((name) => {
        const item = document.createElement("li");
        item.textContent = name;
        return item;
      }));
    });
  };

  fetch(API_URL, { headers: { Accept: "application/json" } })
    .then((response) => response.ok ? response.json() : Promise.reject(new Error("provider_catalog_unavailable")))
    .then((payload) => Array.isArray(payload?.providers) && render(payload.providers))
    .catch(() => {
      // The server-rendered list remains visible when the catalog is unavailable.
    });
})();
