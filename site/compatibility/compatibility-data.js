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

  const exactVariantLabel = (row, fallbackVariants = []) => {
    const variant = String(row.variant || "").trim();
    const model = String(row.model || "").trim();
    const explicitSize = Number(row.caseSizeMm ?? row.case_size_mm);
    const sizeMatch = variant.match(/\b(\d{2})\s*mm\b/i) || model.match(/\b(\d{2})\s*mm\b/i);
    const size = Number.isInteger(explicitSize) && explicitSize > 0
      ? explicitSize
      : sizeMatch ? Number(sizeMatch[1]) : null;
    const display = String(row.displayType ?? row.display_type ?? "").trim()
      || (variant.match(/\b(amoled|solar|microled)\b/i) || model.match(/\b(amoled|solar|microled)\b/i) || [])[1]
      || "";
    const exactParts = [];
    if (Number.isInteger(size) && size > 0) exactParts.push(`${size} mm`);
    if (display) exactParts.push(display);
    if (exactParts.length) return exactParts.join(", ");
    if (variant) return variant;
    return fallbackVariants.map((value) => String(value).trim()).filter(Boolean).join(" · ");
  };

  const publicModelName = (model) => {
    const original = String(model || "").trim();
    const withoutVariant = original
      .replace(/\b\d{2}\s*mm\b/gi, "")
      .replace(/\b(?:amoled|solar|microled)\b/gi, "")
      .replace(/\s*[·–—]\s*/g, " ")
      .replace(/,\s*$/, "")
      .replace(/\s{2,}/g, " ")
      .trim();
    return withoutVariant.replace(/^Garmin\s+/i, "") || original;
  };

  const successfulInstallLabel = (count) => {
    const total = Number(count);
    if (!Number.isFinite(total) || total < 1) return "No successful installs yet";
    return `${total} successful install${total === 1 ? "" : "s"}`;
  };

  const resultCountLabel = (visible, total) => {
    if (visible === total) return "";
    const modelLabel = total === 1 ? "model" : "models";
    return `${visible} of ${total} Garmin ${modelLabel}`;
  };

  return Object.freeze({
    normalize,
    canonicalFamilyKey,
    familyOptions,
    filterByFamily,
    exactVariantLabel,
    publicModelName,
    successfulInstallLabel,
    resultCountLabel,
  });
});
