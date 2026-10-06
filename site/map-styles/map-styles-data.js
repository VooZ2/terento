(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.TerentoMapStylesData = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const KM_PER_DEGREE = 111.32;
  const BEST_COUNT = 10;
  const STATUSES = new Set(["AVAILABLE", "NOT_COVERED", "PENDING"]);

  function bbox(area) {
    const [lon, lat] = area.center;
    const [width, height] = area.sizeKm;
    const halfLat = height / 2 / KM_PER_DEGREE;
    const halfLon = width / 2 / (KM_PER_DEGREE * Math.max(Math.cos(lat * Math.PI / 180), 0.01));
    return [lon - halfLon, lat - halfLat, lon + halfLon, lat + halfLat];
  }

  function defaultZoom(area) {
    return Math.min(area.zoom[1], area.zoom[0] + (area.kind === "city" ? 2 : 1));
  }

  function zoomPercent(area, zoom, base = defaultZoom(area)) {
    return Math.round(100 * Math.pow(2, zoom - base));
  }

  function format(template, values) {
    return String(template).replace(/\{(\w+)\}/g, (match, key) => (key in values ? String(values[key]) : match));
  }

  function plural(locale, forms, count) {
    let rule = "other";
    try { rule = new Intl.PluralRules(locale).select(count); } catch (error) { rule = count === 1 ? "one" : "other"; }
    return format(forms[rule] || forms.other, {n: count});
  }

  function normalize(text) {
    return String(text || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  function matches(area, query, countryName) {
    const needle = normalize(query).trim();
    if (!needle) return true;
    const names = area.countryCodes.map((code) => (countryName ? countryName(code) : "") + " " + code);
    const haystack = normalize([area.name, area.routeName || "", names.join(" "), area.tags.join(" ")].join(" "));
    return haystack.includes(needle);
  }

  function parseHash(hash) {
    const params = new URLSearchParams(String(hash || "").replace(/^#/, ""));
    const mode = params.get("mode");
    return {
      area: params.get("area"),
      style: params.get("style"),
      compare: params.get("compare"),
      mode: ["single", "split", "swipe"].includes(mode) ? mode : null,
    };
  }

  function serializeHash(state) {
    const params = new URLSearchParams();
    params.set("area", state.area);
    params.set("style", state.a);
    if (state.mode !== "single") {
      params.set("compare", state.b);
      params.set("mode", state.mode);
    }
    return "#" + params.toString();
  }

  function manifestArea(manifest, areaId) {
    if (!manifest || !Array.isArray(manifest.areas)) return null;
    return manifest.areas.find((item) => item.id === areaId) || null;
  }

  function layerStatus(manifest, areaId, styleId) {
    const area = manifestArea(manifest, areaId);
    const layer = area && Array.isArray(area.layers) ? area.layers.find((item) => item.style === styleId) : null;
    return layer && STATUSES.has(layer.status) ? layer.status : "PENDING";
  }

  function coveredCount(manifest, areaId, styleIds) {
    return styleIds.filter((styleId) => layerStatus(manifest, areaId, styleId) !== "NOT_COVERED").length;
  }

  function tileUrl(manifest, areaId, styleId) {
    if (!manifest || typeof manifest.tileUrlTemplate !== "string") return null;
    if (!/^https:\/\/api\.terento\.app\//.test(manifest.tileUrlTemplate)) return null;
    return manifest.tileUrlTemplate.replace("{area}", encodeURIComponent(areaId)).replace("{style}", encodeURIComponent(styleId));
  }

  function bestAreas(areas, manifest) {
    const scored = areas
      .map((area) => ({id: area.id, score: (manifestArea(manifest, area.id) || {}).diffScore}))
      .filter((item) => typeof item.score === "number");
    if (scored.length >= BEST_COUNT) {
      return new Set(scored.sort((a, b) => b.score - a.score).slice(0, BEST_COUNT).map((item) => item.id));
    }
    return new Set(areas.filter((area) => area.featured).map((area) => area.id));
  }

  return {
    bbox, defaultZoom, zoomPercent, format, plural, normalize, matches, parseHash, serializeHash,
    layerStatus, coveredCount, tileUrl, bestAreas,
  };
});
