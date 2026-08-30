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

  const displayLabel = (value) => ({
    amoled: "AMOLED",
    solar: "Solar",
    microled: "microLED",
  }[String(value || "").toLocaleLowerCase()] || String(value || "").trim());

  const variantParts = (value) => {
    const source = String(value || "").trim();
    const sizeMatch = source.match(/\b(\d{2})\s*mm\b/i);
    const displayMatch = source.match(/\b(amoled|solar|microled)\b/i);
    return {
      size: sizeMatch ? `${Number(sizeMatch[1])} mm` : "",
      display: displayMatch ? displayLabel(displayMatch[1]) : "",
    };
  };

  const exactVariantLabel = (row, fallbackVariants = []) => {
    const rawVariant = String(row.variant || "").trim();
    const source = `${rawVariant} ${String(row.model || "")}`;
    const parsed = variantParts(source);
    const sizeValue = Number(row.caseSizeMm ?? row.case_size_mm);
    const size = Number.isInteger(sizeValue) && sizeValue > 0 ? `${sizeValue} mm` : parsed.size;
    const displayValue = String(row.displayType ?? row.display_type ?? "").trim();
    const display = displayValue ? displayLabel(displayValue) : parsed.display;
    const exactParts = [];
    if (size) exactParts.push(size);
    if (display) exactParts.push(display);
    if (exactParts.length) return exactParts.join(", ");
    if (rawVariant) return rawVariant.replace(/\s*(?:·|\||\/)\s*/g, ", ").replace(/\s+/g, " ");
    return fallbackVariants.map((value) => String(value).trim()).filter(Boolean).join(" · ");
  };

  const publicModelName = (value) => {
    const label = String(value || "").trim().normalize("NFC").replace(/^Garmin\s+/i, "");
    const withoutVariant = label
      .replace(/\s*(?:[·•|:]\s*|[-–—]\s*)?\d{2}\s*mm(?:\s*,?\s*(?:AMOLED|Solar|microLED))?\s*$/i, "")
      .replace(/\s*(?:[·•|:]\s*|[-–—]\s*)?(?:AMOLED|Solar|microLED)\s*$/i, "")
      .replace(/\s+/g, " ")
      .trim();
    return withoutVariant || label;
  };

  const successfulInstallLabel = (value) => {
    const count = Number(value);
    if (!Number.isFinite(count) || count < 1) return "No successful installs yet";
    return `${count} successful install${count === 1 ? "" : "s"}`;
  };

  return Object.freeze({ normalize, canonicalFamilyKey, familyOptions, filterByFamily, exactVariantLabel, publicModelName, successfulInstallLabel });
});
