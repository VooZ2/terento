// Home numbers strip: the build-time snapshot is the fallback; on load the same public
// compatibility data the Compatibility page uses refreshes the three numbers.
(() => {
  const strip = document.querySelector(".home-trust-strip");
  if (!strip || typeof fetch !== "function") return;
  const locales = { en: "en-US", de: "de-DE", fr: "fr-FR", pl: "pl-PL", cs: "cs-CZ", it: "it-IT" };
  const locale = locales[document.documentElement.lang] || "en-US";
  const count = (row) => Number(row.successfulInstallations ?? row.successful_installations ?? row.successes ?? 0) || 0;
  const last = (row) => row.lastSuccessfulInstallation || row.last_successful_installation || row.lastSuccess || null;
  const signal = typeof AbortSignal !== "undefined" && AbortSignal.timeout ? AbortSignal.timeout(15000) : undefined;
  fetch(`https://api.terento.app/compatibility/public/models.json?limit=500&refresh=${Date.now()}`, { cache: "no-store", headers: { Accept: "application/json" }, signal })
    .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
    .then((payload) => {
      const rows = Array.isArray(payload.models) ? payload.models.filter((row) => count(row) > 0) : [];
      if (!rows.length) return;
      const set = (key, value) => { const node = strip.querySelector(`[data-home-stat="${key}"]`); if (node) node.textContent = value; };
      set("models", rows.length.toLocaleString(locale));
      set("successes", rows.reduce((sum, row) => sum + count(row), 0).toLocaleString(locale));
      const latest = rows.map(last).filter(Boolean).sort().at(-1);
      const time = strip.querySelector('[data-home-stat="latest"]');
      const date = latest ? new Date(latest) : null;
      if (time && date && !Number.isNaN(date.getTime())) {
        time.dateTime = latest;
        time.querySelector(".date-long").textContent = date.toLocaleDateString(locale, { dateStyle: "long" });
        time.querySelector(".date-short").textContent = date.toLocaleDateString(locale, { dateStyle: "medium", timeZone: "UTC" });
      }
    })
    .catch(() => {});
})();
