(() => {
  const umamiSource = "https://stats.enduristas.lt/script.js";
  const umamiWebsiteId = "d8097a98-ffe4-478e-b212-9f06b5bcccbe";
  const campaignStorageKey = "terento-campaign-attribution";
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

  const getCampaignParams = () => {
    const current = readCampaignParams(new URL(window.location.href));
    let stored = {};
    try {
      const candidate = JSON.parse(window.sessionStorage.getItem(campaignStorageKey) || "{}");
      if (candidate && typeof candidate === "object" && !Array.isArray(candidate)) {
        stored = readCampaignParams(new URL(`https://terento.app/?${new URLSearchParams(candidate)}`));
      }
      if (Object.keys(current).length > 0) {
        window.sessionStorage.setItem(campaignStorageKey, JSON.stringify({ ...stored, ...current }));
      }
    } catch {
      // Attribution remains page-local if session storage is unavailable.
    }
    return { ...stored, ...current };
  };

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

    document.querySelectorAll('.hero-copy .text-link[href], .final-cta a.download-action[href]').forEach((link) => {
      let url;
      try {
        url = new URL(link.href, window.location.href);
      } catch {
        return;
      }
      if (!url.pathname.endsWith("/download/")) return;
      const location = link.closest(".final-cta") ? "home-final-cta" : "home-hero";
      setConversionEvent(link, "download-cta-click", withCampaignProperties({ location }, campaignParams));
    });

    document.querySelectorAll(".footer-support-link[href]").forEach((link) => {
      setConversionEvent(link, "support-click", {
        location: "footer",
        destination: "buymeacoffee"
      });
    });
  };

  const campaignParams = getCampaignParams();
  propagateCampaignParams(campaignParams);
  instrumentConversionLinks(campaignParams);
  loadUmami();
})();
