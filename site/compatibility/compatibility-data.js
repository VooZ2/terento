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

  return Object.freeze({ normalize, canonicalFamilyKey, familyOptions, filterByFamily });
});
