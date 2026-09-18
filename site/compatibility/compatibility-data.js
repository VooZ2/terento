((root, factory) => {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.TerentoCompatibilityData = api;
})(typeof globalThis === "object" ? globalThis : this, () => {
  const normalize = (value) => String(value || "")
    .trim()
    .toLocaleLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ");

  const canonicalFamilyKey = (value) => normalize(value)
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "") || "other";

  const familyOptions = (rows) => {
    const families = new Map();
    rows.forEach((row) => {
      const key = canonicalFamilyKey(row.family);
      const label = String(row.familyName || row.family || "Other").trim().normalize("NFC") || "Other";
      if (!families.has(key)) families.set(key, label);
    });
    return [...families.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  };

  const filterByFamily = (rows, family) => family === "ALL"
    ? [...rows]
    : rows.filter((row) => canonicalFamilyKey(row.family) === canonicalFamilyKey(family));

  // Presentation only: never derive identity IDs or compatibility groups here.
  const sizePattern = /\b\d{2,3}(?:\s*[x×]\s*\d{2,3})?\s*mm\b/gi;
  const featurePattern = /\b(?:AMOLED|MicroLED|MIP|Solar|inReach)\b/gi;
  const clean = (value) => String(value || "").replace(/[®™]/g, "").replace(/\s+/g, " ").trim();
  const trimSeparators = (value) => clean(value).replace(/^[ ,·•|:–—-]+|[ ,·•|:–—-]+$/g, "");

  const exactVariantLabel = (row, fallbackVariants = []) => {
    const raw = clean(row.variant);
    const model = clean(row.model);
    if (/\bHistorical\s*$/i.test(model)) return "Historical";
    const source = `${raw} ${model}`;
    const size = Number(row.caseSizeMm ?? row.case_size_mm);
    const sizes = source.match(sizePattern) || [];
    const parts = [];
    if (Number.isInteger(size) && size > 0) parts.push(`${size} mm`);
    else if (sizes.length) parts.push(sizes[0].replace(/\s*mm$/i, " mm").replace(/\s*[x×]\s*/g, " × "));
    const display = row.screenTechnology || row.screen_technology || row.displayType || row.display_type || "";
    const facts = `${source} ${display}`;
    const screens = ["AMOLED", "MicroLED", "MIP"].filter(name => new RegExp(`\\b${name}\\b`, "i").test(facts));
    for (const name of ["AMOLED", "MicroLED", "MIP", "Solar", "inReach"]) {
      if (screens.includes(name) && screens.length > 1) continue;
      const present = new RegExp(`\\b${name}\\b`, "i").test(facts)
        || (name === "Solar" && row.solar === true)
        || (name === "inReach" && (row.inReach ?? row.inreach) === true);
      if (present) parts.push(name);
    }
    const extras = raw.replace(sizePattern, "").replace(featurePattern, "");
    for (const extra of extras.split(/[,·•|/]/).map(trimSeparators).filter(Boolean)) {
      if (!parts.includes(extra)) parts.push(extra);
    }
    return parts.length ? parts.join(", ") : fallbackVariants.map(clean).filter(Boolean).join(" · ");
  };

  const publicModelName = (value) => {
    const label = clean(value).replace(/^Garmin\s+/i, "");
    const modelOnly = label.split(/\s*[·|:]\s*/, 1)[0].trim();
    return trimSeparators(modelOnly.replace(sizePattern, "").replace(featurePattern, "")
      .replace(/\bHistorical\s*$/i, "")
      .replace(/\b(?:fenix|fēnix)\b/gi, "fēnix")
      .replace(/\bpro\b/gi, "Pro")
      .replace(/(fēnix\s+\d+)([sx])\b/gi, (_, base, suffix) => base + suffix.toUpperCase())
      .replace(/[·•|:,]+/g, " ")) || label;
  };

  const successfulInstallLabel = (value) => {
    const count = Number(value);
    if (!Number.isFinite(count) || count < 1) return "No successful installs yet";
    return `${count} successful install${count === 1 ? "" : "s"}`;
  };

  return Object.freeze({ normalize, canonicalFamilyKey, familyOptions, filterByFamily, exactVariantLabel, publicModelName, successfulInstallLabel });
});
