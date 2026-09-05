(() => {
  const umamiSource = "https://stats.enduristas.lt/script.js";
  const umamiWebsiteId = "d8097a98-ffe4-478e-b212-9f06b5bcccbe";
  const campaignParameterKeys = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"];
  const campaignValuePattern = /^[A-Za-z0-9._~-]{1,80}$/;
  const loadUmami = () => {
    if (document.querySelector("script[data-terento-umami]")) return;
    const script = document.createElement("script");
    script.async = true;
    script.src = umamiSource;
    script.dataset.websiteId = umamiWebsiteId;
    script.dataset.terentoUmami = "true";
    document.head.append(script);
  };

  const readCampaignParams = (url) => {
    const result = {};
    campaignParameterKeys.forEach((key) => {
      const value = url.searchParams.get(key);
      if (value && campaignValuePattern.test(value)) result[key] = value;
    });
    return result;
  };

  // Campaign values travel in the URL only; no browser storage is read or written.
  const getCampaignParams = () => readCampaignParams(new URL(window.location.href));

  const appendCampaignParams = (link, campaignParams) => {
    if (!link || Object.keys(campaignParams).length === 0) return;
    const rawHref = link.getAttribute("href");
    if (!rawHref || rawHref.startsWith("#")) return;
    let url;
    try {
      url = new URL(rawHref, window.location.href);
    } catch {
      return;
    }
    const path = url.pathname.toLowerCase();
    const isInternalLink = url.origin === window.location.origin;
    const isDownloadArtifact = path.endsWith(".dmg") || path.endsWith(".zip");
    if (!isInternalLink && !isDownloadArtifact) return;
    campaignParameterKeys.forEach((key) => {
      if (campaignParams[key] && !url.searchParams.has(key)) url.searchParams.set(key, campaignParams[key]);
    });
    const serialized = isInternalLink
      ? `${url.pathname}${url.search}${url.hash}`
      : url.toString();
    link.setAttribute("href", serialized);
  };

  const propagateCampaignParams = (campaignParams) => {
    document.querySelectorAll("a[href]").forEach((link) => appendCampaignParams(link, campaignParams));
  };

  // Attach conversion metadata before the Umami script loads. Keeping it on
  // the links preserves native navigation if the analytics service is down.
  const setConversionEvent = (link, eventName, properties) => {
    if (!link || (link.dataset.umamiEvent && link.dataset.umamiEvent !== eventName)) return;
    link.dataset.umamiEvent = eventName;
    Object.entries(properties).forEach(([key, value]) => {
      const attribute = `umamiEvent${key.charAt(0).toUpperCase()}${key.slice(1)}`;
      link.dataset[attribute] = value;
    });
  };

  const withCampaignProperties = (properties, campaignParams) => {
    const campaignProperties = {
      campaignSource: campaignParams.utm_source,
      campaignMedium: campaignParams.utm_medium,
      campaignName: campaignParams.utm_campaign,
      campaignContent: campaignParams.utm_content,
      campaignTerm: campaignParams.utm_term,
    };
    return {
      ...properties,
      ...Object.fromEntries(Object.entries(campaignProperties).filter(([, value]) => value)),
    };
  };

  const pageLocation = () => {
    const path = window.location.pathname.replace(/\/+$/, "") || "/";
    if (path === "/") return "home-page";
    if (/\/download$/.test(path)) return "download-page";
    if (/\/guides\/install-garmin-maps-mac$/.test(path)) return "guide-page";
    if (/\/compatibility$/.test(path)) return "compatibility-page";
    if (/\/about$/.test(path)) return "about-page";
    if (/\/legal$/.test(path)) return "legal-page";
    if (/\/privacy$/.test(path)) return "privacy-page";
    return "public-page";
  };

  const linkLocation = (link) => {
    if (link.dataset.umamiEventLocation) return link.dataset.umamiEventLocation;
    if (link.classList.contains("hero-compatibility-link")) return "home-hero";
    if (link.classList.contains("download-info-link")) return "download-page";
    if (link.closest(".site-header")) return "header-nav";
    if (link.closest(".footer-nav")) return "footer-nav";
    if (link.closest(".footer-identity")) return "footer";
    return pageLocation();
  };

  const instrumentCompatibilityLinks = (campaignParams) => {
    document.querySelectorAll('a[href]:not(.language-option)').forEach((link) => {
      let url;
      try {
        url = new URL(link.href, window.location.href);
      } catch {
        return;
      }
      if (url.origin !== window.location.origin || !/\/compatibility\/?$/.test(url.pathname)) return;
      setConversionEvent(link, "compatibility-link-click", withCampaignProperties({
        location: linkLocation(link)
      }, campaignParams));
    });
  };

  const instrumentSupportAndProjectLinks = (campaignParams) => {
    document.querySelectorAll("a[href]").forEach((link) => {
      let url;
      try {
        url = new URL(link.href, window.location.href);
      } catch {
        return;
      }
      const hostname = url.hostname.toLowerCase();
      const path = url.pathname.replace(/\/+$/, "").toLowerCase() || "/";
      const location = linkLocation(link);

      if (hostname === "github.com" && path === "/vooz2/terento") {
        setConversionEvent(link, "project-link-click", withCampaignProperties({
          location,
          destination: "github"
        }, campaignParams));
        return;
      }
      if (hostname === "github.com" && path.startsWith("/vooz2/terento/issues")) {
        setConversionEvent(link, "support-link-click", withCampaignProperties({
          location,
          destination: "github-issues"
        }, campaignParams));
        return;
      }
      if (hostname === "github.com" && path.startsWith("/vooz2/terento/blob/")) {
        setConversionEvent(link, "project-link-click", withCampaignProperties({
          location,
          destination: "github-source"
        }, campaignParams));
        return;
      }
      if (hostname === "support.garmin.com" || hostname === "support.apple.com") {
        setConversionEvent(link, "support-link-click", withCampaignProperties({
          location,
          destination: hostname === "support.garmin.com" ? "garmin-support" : "apple-support"
        }, campaignParams));
        return;
      }
      if (url.protocol === "mailto:") {
        setConversionEvent(link, "support-link-click", withCampaignProperties({
          location,
          destination: "email"
        }, campaignParams));
      }
    });
  };

  const instrumentConversionLinks = (campaignParams) => {
    document.querySelectorAll("a[href]").forEach((link) => {
      let url;
      try {
        url = new URL(link.href, window.location.href);
      } catch {
        return;
      }
      const path = url.pathname.toLowerCase();
      if (path.endsWith(".dmg") || path.endsWith(".zip")) {
        setConversionEvent(link, "download-click", withCampaignProperties({
          file: path.endsWith(".dmg") ? "dmg" : "zip",
          location: "download-page"
        }, campaignParams));
      }
    });

    document.querySelectorAll('.hero-copy a.download-action[href], .final-cta a.download-action[href], .site-header a.download-action[href]').forEach((link) => {
      let url;
      try {
        url = new URL(link.href, window.location.href);
      } catch {
        return;
      }
      if (!url.pathname.endsWith("/download/")) return;
      const location = link.closest(".site-header")
        ? "header-nav"
        : link.closest(".final-cta")
          ? "home-final-cta"
          : "home-hero";
      setConversionEvent(link, "download-cta-click", withCampaignProperties({ location }, campaignParams));
    });

    document.querySelectorAll(".footer-support-link[href]").forEach((link) => {
      setConversionEvent(link, "donate", {
        location: "footer",
        destination: "buymeacoffee"
      });
    });

    document.querySelectorAll(".footer-project-link[href]").forEach((link) => {
      setConversionEvent(link, "project-link-click", {
        location: "footer",
        destination: "github"
      });
    });

    instrumentCompatibilityLinks(campaignParams);
    instrumentSupportAndProjectLinks(campaignParams);
  };

  const campaignParams = getCampaignParams();
  propagateCampaignParams(campaignParams);
  instrumentConversionLinks(campaignParams);
  loadUmami();
})();
