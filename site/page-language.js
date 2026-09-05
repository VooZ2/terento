window.TerentoPageLanguage = (copy) => {
  const page = document.querySelector(".page-lang");
  if (!page) return;

  const root = document.documentElement;
  const meta = {
    description: document.querySelector('meta[name="description"]'),
    ogTitle: document.querySelector('meta[property="og:title"]'),
    ogDescription: document.querySelector('meta[property="og:description"]'),
    ogLocale: document.querySelector('meta[property="og:locale"]'),
    twitterTitle: document.querySelector('meta[name="twitter:title"]'),
    twitterDescription: document.querySelector('meta[name="twitter:description"]')
  };
  // Delegation survives the shared shell rebuilding the language menu.
  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-language-switch]");
    if (!link || !copy[link.dataset.languageSwitch]) return;
    event.preventDefault();
    const language = link.dataset.languageSwitch;
    try { window.localStorage.setItem("terento-language", language); } catch {}
    apply(language);
  });

  const apply = (language) => {
    const selectedLanguage = copy[language] ? language : "en";
    const selected = copy[selectedLanguage];
    page.dataset.pageLanguage = selectedLanguage;
    root.lang = selectedLanguage;
    window.TerentoLanguageMenu?.update(selectedLanguage);
    document.title = selected.title;
    meta.description.content = selected.description;
    meta.ogTitle.content = selected.title;
    meta.ogDescription.content = selected.description;
    meta.ogLocale.content = selected.locale;
    meta.twitterTitle.content = selected.title;
    meta.twitterDescription.content = selected.description;
    document.querySelectorAll("[data-language-switch]").forEach((link) => {
      link.toggleAttribute("aria-current", link.dataset.languageSwitch === selectedLanguage);
    });
    document.querySelectorAll("[data-i18n]").forEach((element) => {
      const value = selected[element.dataset.i18n];
      if (value) element.textContent = value;
    });
    document.querySelectorAll("[data-i18n-aria]").forEach((element) => {
      const value = selected[element.dataset.i18nAria];
      if (value) element.setAttribute("aria-label", value);
    });
    document.querySelector("[data-footer-copy]").textContent = selected.footerCopy;
  };

  let initialLanguage = "en";
  try {
    const savedLanguage = window.localStorage.getItem("terento-language");
    if (copy[savedLanguage]) initialLanguage = savedLanguage;
  } catch {
    // The language preference is optional.
  }
  apply(initialLanguage);
};
