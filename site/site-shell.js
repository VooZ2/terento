(() => {
  const menuButton = document.querySelector(".menu-toggle");
  const mobileNav = document.querySelector(".mobile-nav");
  const setMenu = (open) => {
    if (!menuButton || !mobileNav) return;
    menuButton.setAttribute("aria-expanded", String(open));
    menuButton.setAttribute("aria-label", open ? menuButton.dataset.closeLabel : menuButton.dataset.menuLabel);
    mobileNav.hidden = !open;
    document.documentElement.classList.toggle("mobile-menu-open", open);
  };
  menuButton?.addEventListener("click", () => setMenu(menuButton.getAttribute("aria-expanded") !== "true"));
  mobileNav?.addEventListener("click", event => {
    if (event.target.closest("a, [data-language-switch]")) setMenu(false);
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && menuButton?.getAttribute("aria-expanded") === "true") {
      setMenu(false);
      menuButton.focus();
    }
  });
  // Keep the FAQ destination when switching between localized Home pages.
  if (window.location.hash === "#faq") {
    document.querySelectorAll("a[data-language-switch]").forEach(link => { link.hash = "faq"; });
  }
  const translations = JSON.parse(document.querySelector("#shell-translations")?.textContent || "{}");
  window.TerentoLanguageMenu = {
    update(language) {
      const copy = translations[language];
      if (!copy) return;
      const root = language === "en" ? "/" : `/${language}/`;
      const routes = {about: "about/", compatibility: "compatibility/", guide: "guides/install-garmin-maps-mac/", faq: "#faq", download: "download/"};
      document.querySelectorAll("[data-shell-copy]").forEach(node => { node.textContent = copy[node.dataset.shellCopy]; });
      document.querySelectorAll("[data-shell-aria]").forEach(node => { node.setAttribute("aria-label", copy[node.dataset.shellAria]); });
      document.querySelectorAll("[data-shell-root]").forEach(node => { node.href = root; });
      document.querySelectorAll("[data-shell-route]").forEach(node => { node.href = root + routes[node.dataset.shellRoute]; });
      document.querySelectorAll(".language-code").forEach(node => { node.textContent = language.toUpperCase(); });
      document.querySelectorAll(".mobile-language-label").forEach(node => { node.textContent = copy.name; });
      if (menuButton) {
        menuButton.dataset.menuLabel = copy.menu;
        menuButton.dataset.closeLabel = copy.close;
      }
      setMenu(false);
    },
  };
})();
