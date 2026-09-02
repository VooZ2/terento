(() => {
  const homeFaq = document.querySelector("#faq");
  const guide = document.querySelector(".guide-article");
  if (!homeFaq && !guide) return;

  const stateKey = `terento-reading-state:${window.location.pathname}`;
  const readState = () => {
    try {
      const value = sessionStorage.getItem(stateKey);
      return value ? JSON.parse(value) : null;
    } catch {
      return null;
    }
  };
  const saveState = () => {
    try {
      const details = homeFaq ? [...homeFaq.querySelectorAll("details")] : [];
      sessionStorage.setItem(stateKey, JSON.stringify({
        hash: window.location.hash,
        scrollY: window.scrollY,
        openFaq: details.map((item) => item.open),
      }));
    } catch {
      // Restoring reading position is an enhancement, not a requirement.
    }
  };
  const restoreState = (event) => {
    const navigation = performance.getEntriesByType("navigation")[0];
    if (!event.persisted && navigation?.type !== "back_forward") return;
    const state = readState();
    if (!state) return;

    if (homeFaq && Array.isArray(state.openFaq)) {
      [...homeFaq.querySelectorAll("details")].forEach((item, index) => {
        item.open = Boolean(state.openFaq[index]);
      });
    }
    requestAnimationFrame(() => {
      window.scrollTo({ top: Number(state.scrollY) || 0, behavior: "auto" });
    });
    try { sessionStorage.removeItem(stateKey); } catch { /* optional */ }
  };

  window.addEventListener("pagehide", saveState);
  window.addEventListener("pageshow", restoreState);
  restoreState({ persisted: false });
})();
