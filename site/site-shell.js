(() => {
  const languages = [
    { code: "en", flag: "🇬🇧", name: "English" },
    { code: "de", flag: "🇩🇪", name: "Deutsch" },
    { code: "fr", flag: "🇫🇷", name: "Français" },
    { code: "pl", flag: "🇵🇱", name: "Polski" },
    { code: "cs", flag: "🇨🇿", name: "Čeština" },
    { code: "it", flag: "🇮🇹", name: "Italiano" },
  ];

  const translations = {
    en: {
      home: "Terento home", primary: "Primary navigation", menu: "Menu",
      close: "Close menu", about: "About", compatibility: "Compatibility",
      faq: "FAQ", download: "Download", language: "Language selection",
      footer: "Footer navigation", status: "Open-source project", legal: "Legal",
      privacy: "Privacy", stats: "Visit statistics (Umami) do not use cookies.",
    },
    de: {
      home: "Terento Startseite", primary: "Hauptnavigation", menu: "Menü",
      close: "Menü schließen", about: "Über uns", compatibility: "Kompatibilität",
      faq: "FAQ", download: "Download", language: "Sprachauswahl",
      footer: "Footer-Navigation", status: "Open-Source-Projekt", legal: "Rechtliches",
      privacy: "Datenschutz", stats: "Besuchsstatistik (Umami) verwendet keine Cookies.",
    },
    fr: {
      home: "Accueil Terento", primary: "Navigation principale", menu: "Menu",
      close: "Fermer le menu", about: "À propos", compatibility: "Compatibilité",
      faq: "FAQ", download: "Télécharger", language: "Choix de la langue",
      footer: "Navigation du pied de page", status: "Projet open source", legal: "Mentions légales",
      privacy: "Confidentialité", stats: "Les statistiques de visites (Umami) n’utilisent pas de cookies.",
    },
    pl: {
      home: "Strona główna Terento", primary: "Główna nawigacja", menu: "Menu",
      close: "Zamknij menu", about: "O projekcie", compatibility: "Kompatybilność",
      faq: "FAQ", download: "Pobierz", language: "Wybór języka",
      footer: "Nawigacja w stopce", status: "Projekt open source", legal: "Informacje prawne",
      privacy: "Prywatność", stats: "Statystyki odwiedzin (Umami) nie używają plików cookie.",
    },
    cs: {
      home: "Domů Terento", primary: "Hlavní navigace", menu: "Menu",
      close: "Zavřít menu", about: "O projektu", compatibility: "Kompatibilita",
      faq: "FAQ", download: "Stáhnout", language: "Výběr jazyka",
      footer: "Navigace v zápatí", status: "Open-source projekt", legal: "Právní informace",
      privacy: "Soukromí", stats: "Statistiky návštěvnosti (Umami) nepoužívají cookies.",
    },
    it: {
      home: "Home Terento", primary: "Navigazione principale", menu: "Menu",
      close: "Chiudi il menu", about: "Informazioni", compatibility: "Compatibilità",
      faq: "FAQ", download: "Scarica", language: "Selezione della lingua",
      footer: "Navigazione del piè di pagina", status: "Progetto open source", legal: "Note legali",
      privacy: "Privacy", stats: "Le statistiche delle visite (Umami) non usano cookie.",
    },
  };

  const language = (document.documentElement.lang || "en").toLowerCase().split("-")[0];
  const copy = translations[language] || translations.en;
  const localizedRoot = language === "en" ? "/" : `/${language}/`;
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  const isCompatibility = path === "/compatibility";
  const isDownload = path === "/download" || path === `/${language}/download`;
  const link = (key) => ({
    about: `${localizedRoot}#about`,
    compatibility: "/compatibility/",
    faq: `${localizedRoot}#faq`,
    download: `${localizedRoot}download/`,
  }[key]);
  const active = (key) => (key === "compatibility" && isCompatibility)
    || (key === "download" && isDownload);

  const languageOptions = () => languages.map((item) => {
    const href = item.code === "en" ? "/" : `/${item.code}/`;
    const current = item.code === language ? ' aria-current="page"' : "";
    return `<a class="language-option" href="${href}" data-language-switch="${item.code}" lang="${item.code}" aria-label="${item.name}"${current}><span class="language-option-flag" aria-hidden="true">${item.flag}</span><span>${item.name}</span></a>`;
  }).join("");

  const languageMenu = (mobile = false) => `<details class="language-menu${mobile ? " mobile-language-menu" : ""}">
    <summary class="language-trigger" aria-label="${copy.language}">${mobile ? `<span class="mobile-language-label">${copy.language}</span>` : ""}<span class="language-current" data-language-current aria-hidden="true">${languages.find((item) => item.code === language)?.flag || "🇬🇧"}</span></summary>
    <div class="language-options">${languageOptions()}</div>
  </details>`;

  const navLink = (key) => `<a href="${link(key)}"${active(key) ? ' aria-current="page"' : ""}>${copy[key]}</a>`;
  const header = `<header class="site-header">
    <div class="shell header-inner">
      <a class="brand-lockup" href="${localizedRoot}" aria-label="${copy.home}">
        <img src="/assets/logo-sky.svg" alt="" width="40" height="40">
        <span>Terento</span>
      </a>
      <nav class="primary-nav" aria-label="${copy.primary}">
        ${navLink("about")}${navLink("compatibility")}${navLink("faq")}${navLink("download")}
        <span class="language-switcher">${languageMenu()}</span>
      </nav>
      <button class="menu-toggle" type="button" aria-expanded="false" aria-controls="mobile-nav" aria-label="${copy.menu}">
        <span class="menu-toggle-icon" aria-hidden="true"><span></span><span></span><span></span></span>
        <span class="menu-toggle-text">${copy.menu}</span>
      </button>
    </div>
    <div class="mobile-nav" id="mobile-nav" hidden>
      <div class="shell mobile-nav-inner">
        <nav class="mobile-nav-links" aria-label="${copy.primary}">
          ${navLink("about")}${navLink("compatibility")}${navLink("faq")}${navLink("download")}
        </nav>
        <div class="mobile-nav-language">${languageMenu(true)}</div>
      </div>
    </div>
  </header>`;

  const footer = `<footer class="site-footer">
    <div class="shell footer-grid">
      <div class="footer-identity">
        <a class="brand-lockup footer-brand" href="${localizedRoot}" aria-label="${copy.home}">
          <img src="/assets/logo-sky.svg" alt="" width="32" height="32">
          <span>Terento</span>
        </a>
        <p class="footer-status">${copy.status}</p>
      </div>
      <nav class="footer-nav" aria-label="${copy.footer}">
        ${navLink("about")}${navLink("faq")}
        <a href="/legal/">${copy.legal}</a>
        <a href="/privacy/">${copy.privacy}</a>
      </nav>
    </div>
    <div class="shell footer-bottom"><p>© 2026 Terento Project · Beta</p></div>
    <div class="shell footer-note"><p><span data-footer-copy>${copy.stats}</span></p></div>
  </footer>`;

  document.querySelector("header.site-header")?.replaceWith(document.createRange().createContextualFragment(header));
  document.querySelector("footer.site-footer")?.replaceWith(document.createRange().createContextualFragment(footer));

  const menuButton = document.querySelector(".menu-toggle");
  const mobileNav = document.querySelector(".mobile-nav");
  const setMenu = (open) => {
    if (!menuButton || !mobileNav) return;
    menuButton.setAttribute("aria-expanded", String(open));
    menuButton.setAttribute("aria-label", open ? copy.close : copy.menu);
    mobileNav.hidden = !open;
    document.documentElement.classList.toggle("mobile-menu-open", open);
  };

  menuButton?.addEventListener("click", () => setMenu(menuButton.getAttribute("aria-expanded") !== "true"));
  mobileNav?.querySelectorAll("a").forEach((item) => item.addEventListener("click", () => setMenu(false)));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && menuButton?.getAttribute("aria-expanded") === "true") {
      setMenu(false);
      menuButton.focus();
    }
  });
  document.querySelectorAll("[data-language-switch]").forEach((item) => {
    item.addEventListener("click", () => {
      try { window.localStorage.setItem("terento-language", item.dataset.languageSwitch); } catch { /* optional */ }
    });
  });
})();
