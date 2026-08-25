(() => {
  const consentKey = "terento-analytics-consent";
  const umamiSource = "https://stats.enduristas.lt/script.js";
  const umamiWebsiteId = "d8097a98-ffe4-478e-b212-9f06b5bcccbe";
  const copy = {
    en: {
      title: "Privacy choices",
      body: "We use Umami only to measure visits. It does not use tracking cookies or create personal profiles. You can allow or decline analytics.",
      allow: "Allow analytics",
      decline: "Decline analytics",
      settings: "Privacy settings"
    },
    de: {
      title: "Datenschutzeinstellungen",
      body: "Wir verwenden Umami nur zur Messung von Besuchen. Es verwendet keine Tracking-Cookies und erstellt keine persönlichen Profile. Du kannst die Analyse erlauben oder ablehnen.",
      allow: "Analyse erlauben",
      decline: "Analyse ablehnen",
      settings: "Datenschutzeinstellungen"
    },
    fr: {
      title: "Choix de confidentialité",
      body: "Nous utilisons Umami uniquement pour mesurer les visites. Il n’utilise pas de cookies de suivi et ne crée pas de profils personnels. Vous pouvez autoriser ou refuser les statistiques.",
      allow: "Autoriser les statistiques",
      decline: "Refuser les statistiques",
      settings: "Réglages de confidentialité"
    },
    pl: {
      title: "Ustawienia prywatności",
      body: "Używamy Umami wyłącznie do mierzenia odwiedzin. Nie używa ono plików cookie do śledzenia ani nie tworzy osobistych profili. Możesz zezwolić na analitykę lub ją odrzucić.",
      allow: "Zezwól na analitykę",
      decline: "Odrzuć analitykę",
      settings: "Ustawienia prywatności"
    },
    cs: {
      title: "Nastavení soukromí",
      body: "Umami používáme pouze k měření návštěv. Nepoužívá sledovací cookies ani nevytváří osobní profily. Analytiku můžete povolit nebo odmítnout.",
      allow: "Povolit analytiku",
      decline: "Odmítnout analytiku",
      settings: "Nastavení soukromí"
    },
    it: {
      title: "Scelte sulla privacy",
      body: "Usiamo Umami solo per misurare le visite. Non usa cookie di tracciamento e non crea profili personali. Puoi consentire o rifiutare le statistiche.",
      allow: "Consenti le statistiche",
      decline: "Rifiuta le statistiche",
      settings: "Impostazioni privacy"
    }
  };

  const getLanguage = () => {
    const language = (document.documentElement.lang || "en").toLowerCase().split("-")[0];
    return copy[language] ? language : "en";
  };

  const getChoice = () => {
    try {
      const choice = window.localStorage.getItem(consentKey);
      return choice === "granted" || choice === "denied" ? choice : null;
    } catch {
      return null;
    }
  };

  const saveChoice = (choice) => {
    try {
      window.localStorage.setItem(consentKey, choice);
    } catch {
      // Consent remains active for this page if browser storage is unavailable.
    }
  };

  const loadUmami = () => {
    if (document.querySelector("script[data-terento-umami]")) return;
    const script = document.createElement("script");
    script.async = true;
    script.src = umamiSource;
    script.dataset.websiteId = umamiWebsiteId;
    script.dataset.terentoUmami = "true";
    document.head.append(script);
  };

  // Conversion metadata is inert until the consent-gated Umami script loads.
  // Keeping it on the links preserves native navigation if analytics is blocked.
  const setConversionEvent = (link, eventName, properties) => {
    if (!link || link.dataset.umamiEvent) return;
    link.dataset.umamiEvent = eventName;
    Object.entries(properties).forEach(([key, value]) => {
      const attribute = `umamiEvent${key.charAt(0).toUpperCase()}${key.slice(1)}`;
      link.dataset[attribute] = value;
    });
  };

  const instrumentConversionLinks = () => {
    document.querySelectorAll("a[href]").forEach((link) => {
      let url;
      try {
        url = new URL(link.href, window.location.href);
      } catch {
        return;
      }
      const path = url.pathname.toLowerCase();
      if (path.endsWith(".dmg") || path.endsWith(".zip")) {
        setConversionEvent(link, "download-click", {
          file: path.endsWith(".dmg") ? "dmg" : "zip",
          location: "download-page"
        });
      }
    });

    document.querySelectorAll('.hero-copy .text-link[href], .final-cta a.download-action[href]').forEach((link) => {
      let url;
      try {
        url = new URL(link.href, window.location.href);
      } catch {
        return;
      }
      if (!url.pathname.endsWith("/download/")) return;
      const location = link.closest(".final-cta") ? "home-final-cta" : "home-hero";
      setConversionEvent(link, "download-cta-click", { location });
    });
  };

  instrumentConversionLinks();

  const banner = document.createElement("section");
  banner.className = "consent-banner";
  banner.hidden = true;
  banner.setAttribute("role", "dialog");
  banner.setAttribute("aria-labelledby", "terento-consent-title");
  banner.innerHTML = `<div class="consent-banner-inner"><div class="consent-copy"><h2 id="terento-consent-title"></h2><p></p></div><div class="consent-actions"><button type="button" class="consent-button consent-button-secondary" data-consent-choice="denied"></button><button type="button" class="consent-button consent-button-primary" data-consent-choice="granted"></button></div></div>`;
  document.body.append(banner);

  const title = banner.querySelector("h2");
  const body = banner.querySelector("p");
  const allow = banner.querySelector('[data-consent-choice="granted"]');
  const decline = banner.querySelector('[data-consent-choice="denied"]');
  const footerNote = document.querySelector(".footer-note");
  const settings = document.createElement("button");
  settings.type = "button";
  settings.className = "privacy-settings";
  const footerCopy = footerNote?.querySelector("p");
  if (footerCopy) {
    footerCopy.append(document.createTextNode(" "));
    footerCopy.append(settings);
  }

  const renderCopy = () => {
    const selected = copy[getLanguage()];
    title.textContent = selected.title;
    body.textContent = selected.body;
    allow.textContent = selected.allow;
    decline.textContent = selected.decline;
    settings.textContent = selected.settings;
  };

  const showBanner = () => {
    renderCopy();
    banner.hidden = false;
  };

  const choose = (choice) => {
    const previousChoice = getChoice();
    saveChoice(choice);
    banner.hidden = true;
    if (choice === "granted") loadUmami();
    if (previousChoice === "granted" && choice === "denied") window.location.reload();
  };

  allow.addEventListener("click", () => choose("granted"));
  decline.addEventListener("click", () => choose("denied"));
  settings.addEventListener("click", showBanner);
  renderCopy();

  if (getChoice() === "granted") loadUmami();
  else if (!getChoice()) showBanner();

  if (typeof MutationObserver === "function") {
    const observer = new MutationObserver(renderCopy);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
  }
})();
