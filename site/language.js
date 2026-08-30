(() => {
  const supportedLanguages = new Set(["en", "de", "fr", "pl", "cs", "it"]);
  const preferenceKey = "terento-language";

  const languagePath = (language) => language === "en" ? "/" : `/${language}/`;

  const saveLanguagePreference = (language) => {
    if (!supportedLanguages.has(language)) return;
    try {
      window.localStorage.setItem(preferenceKey, language);
    } catch {
      // Local preference is optional; the switcher remains usable without it.
    }
  };

  const updateLanguageMenu = (language) => {
    const currentLink = document.querySelector(`[data-language-switch="${language}"]`);
    const currentFlag = currentLink?.querySelector(".language-option-flag")?.textContent.trim() || "";
    const currentName = currentLink?.getAttribute("aria-label") || language.toUpperCase();
    document.querySelectorAll("[data-language-current]").forEach((element) => {
      element.textContent = currentFlag;
      element.setAttribute("aria-label", currentName);
    });
  };

  const shellLanguageMenu = window.TerentoLanguageMenu;
  window.TerentoLanguageMenu = {
    update(language) {
      shellLanguageMenu?.update?.(language);
      updateLanguageMenu(language);
    },
  };

  const languageFromTag = (tag) => {
    if (typeof tag !== "string") return null;
    const language = tag.toLowerCase().split("-")[0];
    return supportedLanguages.has(language) ? language : null;
  };

  const regionFromTag = (tag) => {
    if (typeof tag !== "string") return null;
    const parts = tag.split("-");
    return parts.slice(1).find((part) => /^[A-Za-z]{2}$/.test(part))?.toUpperCase() || null;
  };

  const languageFromRegion = (region) => {
    const regionLanguages = {
      AT: "de", BE: "fr", CH: "de", CZ: "cs", DE: "de", FR: "fr",
      IT: "it", LU: "fr", PL: "pl"
    };
    return regionLanguages[region] || null;
  };

  const languageFromTimezone = () => {
    let timezone = "";
    try {
      timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch {
      return null;
    }
    if (/^Europe\/(Berlin|Busingen|Zurich|Vienna)/.test(timezone)) return "de";
    if (/^Europe\/(Brussels|Luxembourg|Paris)/.test(timezone)) return "fr";
    if (/^Europe\/Prague/.test(timezone)) return "cs";
    if (/^Europe\/Warsaw/.test(timezone)) return "pl";
    if (/^Europe\/Rome/.test(timezone)) return "it";
    return null;
  };

  const preferredLanguage = () => {
    try {
      const savedLanguage = window.localStorage.getItem(preferenceKey);
      return supportedLanguages.has(savedLanguage) ? savedLanguage : null;
    } catch {
      return null;
    }
  };

  const browserLanguages = () => {
    const languages = Array.isArray(navigator.languages) && navigator.languages.length
      ? navigator.languages
      : [navigator.language];
    return languages.filter(Boolean);
  };

  const detectLanguage = () => {
    const browserTags = browserLanguages();
    for (const tag of browserTags) {
      const language = languageFromTag(tag);
      if (language) return language;
    }

    for (const tag of browserTags) {
      const language = languageFromRegion(regionFromTag(tag));
      if (language) return language;
    }

    return languageFromTimezone() || "en";
  };

  document.querySelectorAll("[data-language-switch]").forEach((link) => {
    link.addEventListener("click", () => {
      saveLanguagePreference(link.dataset.languageSwitch);
      link.closest(".language-menu")?.removeAttribute("open");
    });
  });

  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  if (path !== "/") return;

  const selectedLanguage = preferredLanguage() || detectLanguage();
  if (selectedLanguage === "en") return;

  window.location.replace(`${languagePath(selectedLanguage)}${window.location.search}${window.location.hash}`);
})();
