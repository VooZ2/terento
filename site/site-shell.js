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
      guide: "Guide", faq: "FAQ", download: "Download", language: "Choose language",
      footer: "Footer navigation", status: "Open-source project", legal: "Legal",
      privacy: "Privacy", support: "Support Terento",
      stats: "Visit statistics (Umami) do not use cookies.",
    },
    de: {
      home: "Terento Startseite", primary: "Hauptnavigation", menu: "Menü",
      close: "Menü schließen", about: "Über uns", compatibility: "Kompatibilität",
      guide: "Anleitung", faq: "FAQ", download: "Download", language: "Sprache wählen",
      footer: "Footer-Navigation", status: "Open-Source-Projekt", legal: "Rechtliches",
      privacy: "Datenschutz", support: "Support Terento",
      stats: "Besuchsstatistik (Umami) verwendet keine Cookies.",
    },
    fr: {
      home: "Accueil Terento", primary: "Navigation principale", menu: "Menu",
      close: "Fermer le menu", about: "À propos", compatibility: "Compatibilité",
      guide: "Guide", faq: "FAQ", download: "Télécharger", language: "Choisir la langue",
      footer: "Navigation du pied de page", status: "Projet open source", legal: "Mentions légales",
      privacy: "Confidentialité", support: "Support Terento",
      stats: "Les statistiques de visites (Umami) n’utilisent pas de cookies.",
    },
    pl: {
      home: "Strona główna Terento", primary: "Główna nawigacja", menu: "Menu",
      close: "Zamknij menu", about: "O projekcie", compatibility: "Kompatybilność",
      guide: "Poradnik", faq: "FAQ", download: "Pobierz", language: "Wybierz język",
      footer: "Nawigacja w stopce", status: "Projekt open source", legal: "Informacje prawne",
      privacy: "Prywatność", support: "Support Terento",
      stats: "Statystyki odwiedzin (Umami) nie używają plików cookie.",
    },
    cs: {
      home: "Domů Terento", primary: "Hlavní navigace", menu: "Menu",
      close: "Zavřít menu", about: "O projektu", compatibility: "Kompatibilita",
      guide: "Průvodce", faq: "FAQ", download: "Stáhnout", language: "Vybrat jazyk",
      footer: "Navigace v zápatí", status: "Open-source projekt", legal: "Právní informace",
      privacy: "Soukromí", support: "Support Terento",
      stats: "Statistiky návštěvnosti (Umami) nepoužívají cookies.",
    },
    it: {
      home: "Home Terento", primary: "Navigazione principale", menu: "Menu",
      close: "Chiudi il menu", about: "Informazioni", compatibility: "Compatibilità",
      guide: "Guida", faq: "FAQ", download: "Scarica", language: "Scegli la lingua",
      footer: "Navigazione del piè di pagina", status: "Progetto open source", legal: "Note legali",
      privacy: "Privacy", support: "Support Terento",
      stats: "Le statistiche delle visite (Umami) non usano cookie.",
    },
  };

  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  const declaredPage = document.documentElement.dataset.page || "";
  const pageType = ["home", "about", "compatibility", "guide", "download", "legal", "privacy"].includes(declaredPage)
    ? declaredPage
    : path === "/compatibility" || /\/compatibility$/.test(path)
      ? "compatibility"
      : path === "/download" || /\/download$/.test(path)
        ? "download"
        : path === "/about" || /\/about$/.test(path)
          ? "about"
          : /\/guides\/install-garmin-maps-mac$/.test(path)
            ? "guide"
            : path === "/legal"
              ? "legal"
              : path === "/privacy"
                ? "privacy"
                : "home";
  const pageRoute = {
    about: "about/",
    compatibility: "compatibility/",
    download: "download/",
    guide: "guides/install-garmin-maps-mac/",
  }[pageType] || "";
  let currentLanguage = (document.documentElement.lang || "en").toLowerCase().split("-")[0];
  if (!translations[currentLanguage]) currentLanguage = "en";

  const localizedRoot = (language) => language === "en" ? "/" : `/${language}/`;
  const link = (language, key) => ({
    about: `${localizedRoot(language)}about/`,
    compatibility: `${localizedRoot(language)}compatibility/`,
    guide: `${localizedRoot(language)}guides/install-garmin-maps-mac/`,
    faq: `${localizedRoot(language)}#faq`,
    download: `${localizedRoot(language)}download/`,
  }[key]);

  const renderShell = (language) => {
    const copy = translations[language] || translations.en;
    const root = localizedRoot(language);
    const active = (key) => (key === "about" && pageType === "about")
      || (key === "compatibility" && pageType === "compatibility")
      || (key === "download" && pageType === "download")
      || (key === "guide" && pageType === "guide");
    const homeHash = pageType === "home" && window.location.hash === "#faq" ? "#faq" : "";
    const languageOptions = languages.map((item) => {
      const href = item.code === "en" ? `/${pageRoute}` : `/${item.code}/${pageRoute}`;
      const current = item.code === language ? ' aria-current="page"' : "";
      return `<a class="language-option" href="${href}${homeHash}" data-language-switch="${item.code}" lang="${item.code}" aria-label="${item.name}"${current}><span class="language-option-flag" aria-hidden="true">${item.flag}</span><span>${item.name}</span></a>`;
    }).join("");
    const languageMenu = (mobile = false) => `<details class="language-menu${mobile ? " mobile-language-menu" : ""}">
    <summary class="language-trigger" aria-label="${copy.language}">${mobile ? `<span class="mobile-language-label">${language.toUpperCase()}</span>` : `<span class="language-code" aria-hidden="true">${language.toUpperCase()}</span>`}</summary>
    <div class="language-options">${languageOptions}</div>
  </details>`;
    const navLink = (key, variant = "") => {
      const classAttribute = variant ? ` class="${variant}"` : "";
      return `<a${classAttribute} href="${link(language, key)}"${active(key) ? ' aria-current="page"' : ""}>${copy[key]}</a>`;
    };
    const header = `<header class="site-header">
    <div class="shell header-inner">
      <a class="brand-lockup" href="${root}" aria-label="${copy.home}">
        <img src="/assets/logo-sky.svg" alt="" width="40" height="40">
        <span>Terento</span>
      </a>
      <nav class="primary-nav" aria-label="${copy.primary}">
        ${navLink("compatibility")}${navLink("guide")}${navLink("about")}${navLink("download", "download-action")}
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
          ${navLink("compatibility")}${navLink("guide")}${navLink("about")}${navLink("download", "download-action")}
        </nav>
        <div class="mobile-nav-language">${languageMenu(true)}</div>
      </div>
    </div>
  </header>`;

    const footer = `<footer class="site-footer">
    <div class="shell footer-grid">
      <div class="footer-identity">
        <a class="brand-lockup footer-brand" href="${root}" aria-label="${copy.home}">
          <img src="/assets/logo-white.svg" alt="" width="32" height="32">
          <span>Terento</span>
        </a>
        <div class="footer-meta">
          <a class="footer-status footer-project-link" data-project-link href="https://github.com/VooZ2/terento" target="_blank" rel="noopener noreferrer">${copy.status}</a>
          <a class="footer-support-link" data-support-link href="https://buymeacoffee.com/vooz2" rel="noopener noreferrer">${copy.support}</a>
        </div>
      </div>
      <nav class="footer-nav" aria-label="${copy.footer}">
        ${navLink("about")}${navLink("compatibility")}${navLink("guide")}${navLink("faq")}${navLink("download")}
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
    document.querySelectorAll("[data-language-switch]").forEach((item) => {
      item.addEventListener("click", () => {
        try { window.localStorage.setItem("terento-language", item.dataset.languageSwitch); } catch { /* optional */ }
      });
    });
  };

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const menuButton = document.querySelector(".menu-toggle");
    const mobileNav = document.querySelector(".mobile-nav");
    if (menuButton?.getAttribute("aria-expanded") === "true") {
      menuButton.setAttribute("aria-expanded", "false");
      if (mobileNav) mobileNav.hidden = true;
      document.documentElement.classList.remove("mobile-menu-open");
      menuButton.focus();
    }
  });

  window.TerentoLanguageMenu = {
    update(language) {
      if (!translations[language]) return;
      currentLanguage = language;
      renderShell(currentLanguage);
    },
  };
  renderShell(currentLanguage);
})();
