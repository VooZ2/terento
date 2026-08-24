(() => {
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
  const copy = {
    en: {title:"Legal notices — Terento", description:"Terento legal notices: what the project is, how Garmin, Apple, map providers and third-party software are described, and what is still missing.", locale:"en_US", about:"About", faq:"FAQ", legal:"Legal", privacy:"Privacy", skip:"Skip to content", home:"Terento home", primaryNav:"Primary navigation", languageSelection:"Language selection", footerNav:"Footer navigation", footerStatus:"Open-source project", inDevelopment:"In development", footerCopy:"Visit statistics (Umami) do not use cookies. Details:", garminNotice:"Garmin is a trademark of Garmin Ltd. Terento is an independent project and is not affiliated with or endorsed by Garmin."},
    de: {title:"Rechtliche Hinweise — Terento", description:"Rechtliche Hinweise von Terento: Projekt, Garmin, Apple, Kartenanbieter, Drittsoftware und noch offene Angaben.", locale:"de_DE", about:"Über uns", faq:"FAQ", legal:"Rechtliches", privacy:"Datenschutz", skip:"Zum Inhalt springen", home:"Terento-Startseite", primaryNav:"Hauptnavigation", languageSelection:"Sprachauswahl", footerNav:"Footer-Navigation", footerStatus:"Open-Source-Projekt", inDevelopment:"In Entwicklung", footerCopy:"Besuchsstatistik (Umami) verwendet keine Cookies. Details:", garminNotice:"Garmin ist eine Marke von Garmin Ltd. Terento ist ein unabhängiges Projekt und nicht mit Garmin verbunden oder von Garmin unterstützt."},
    fr: {title:"Mentions légales — Terento", description:"Mentions légales de Terento : projet, Garmin, Apple, fournisseurs de cartes, logiciels tiers et informations encore manquantes.", locale:"fr_FR", about:"À propos", faq:"FAQ", legal:"Mentions légales", privacy:"Confidentialité", skip:"Aller au contenu", home:"Accueil Terento", primaryNav:"Navigation principale", languageSelection:"Choix de la langue", footerNav:"Navigation de pied de page", footerStatus:"Projet open source", inDevelopment:"En développement", footerCopy:"Les statistiques de fréquentation (Umami) n’utilisent pas de cookies. Détails :", garminNotice:"Garmin est une marque de Garmin Ltd. Terento est un projet indépendant, sans affiliation ni soutien de Garmin."},
    pl: {title:"Informacje prawne — Terento", description:"Informacje prawne Terento: projekt, Garmin, Apple, dostawcy map, oprogramowanie stron trzecich i brakujące jeszcze dane.", locale:"pl_PL", about:"O projekcie", faq:"FAQ", legal:"Informacje prawne", privacy:"Prywatność", skip:"Przejdź do treści", home:"Strona główna Terento", primaryNav:"Nawigacja główna", languageSelection:"Wybór języka", footerNav:"Nawigacja stopki", footerStatus:"Projekt open source", inDevelopment:"W trakcie rozwoju", footerCopy:"Statystyki odwiedzin (Umami) nie używają plików cookie. Szczegóły:", garminNotice:"Garmin jest znakiem towarowym firmy Garmin Ltd. Terento to niezależny projekt, który nie jest związany z firmą Garmin ani przez nią wspierany."},
    cs: {title:"Právní informace — Terento", description:"Právní informace Terento: projekt, Garmin, Apple, poskytovatelé map, software třetích stran a dosud chybějící údaje.", locale:"cs_CZ", about:"O projektu", faq:"FAQ", legal:"Právní informace", privacy:"Soukromí", skip:"Přejít k obsahu", home:"Domů Terento", primaryNav:"Hlavní navigace", languageSelection:"Výběr jazyka", footerNav:"Navigace v zápatí", footerStatus:"Open-source projekt", inDevelopment:"Ve vývoji", footerCopy:"Statistiky návštěvnosti (Umami) nepoužívají cookies. Podrobnosti:", garminNotice:"Garmin je ochranná známka společnosti Garmin Ltd. Terento je nezávislý projekt, který není se společností Garmin propojen ani jí podporován."},
    it: {title:"Note legali — Terento", description:"Note legali di Terento: progetto, Garmin, Apple, fornitori di mappe, software di terze parti e informazioni ancora mancanti.", locale:"it_IT", about:"Il progetto", faq:"FAQ", legal:"Note legali", privacy:"Privacy", skip:"Vai al contenuto", home:"Home Terento", primaryNav:"Navigazione principale", languageSelection:"Selezione della lingua", footerNav:"Navigazione del piè di pagina", footerStatus:"Progetto open source", inDevelopment:"In sviluppo", footerCopy:"Le statistiche delle visite (Umami) non usano cookie. Dettagli:", garminNotice:"Garmin è un marchio di Garmin Ltd. Terento è un progetto indipendente, non affiliato a Garmin né approvato da Garmin."}
  };

  const apply = (language) => {
    const selectedLanguage = copy[language] ? language : "en";
    const selected = copy[selectedLanguage];
    page.dataset.pageLanguage = selectedLanguage;
    root.lang = selectedLanguage;
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
    document.querySelector("[data-footer-privacy]").textContent = selected.privacy;
    document.querySelector("[data-footer-privacy]").setAttribute("aria-label", `${selected.privacy} — Terento`);
  };

  document.querySelectorAll("[data-language-switch]").forEach((link) => {
    link.addEventListener("click", (event) => {
      const language = link.dataset.languageSwitch;
      if (!copy[language]) return;
      event.preventDefault();
      try {
        window.localStorage.setItem("terento-language", language);
      } catch {
        // The language preference is optional.
      }
      apply(language);
    });
  });

  let initialLanguage = "en";
  try {
    const savedLanguage = window.localStorage.getItem("terento-language");
    if (copy[savedLanguage]) initialLanguage = savedLanguage;
  } catch {
    // The language preference is optional.
  }
  apply(initialLanguage);
})();
