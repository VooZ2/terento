# Terento Typography

## Approved font roles

### Instrument Sans

Role: **brand / marketing headings**

Use for:

- Hero
- H1–H3
- marketing statements
- brand-led editorial text

Weights:

- 500
- 600

The validated system uses 600 for Hero/H1/H2 and 500–600 for H3.

Instrument Sans should carry expression without becoming decorative.

### Inter

Role: **UI / body**

Use for:

- body copy
- labels
- buttons
- UI headings
- captions
- dense product information

Weights:

- 400
- 500
- 600

### JetBrains Mono

Role: **diagnostics only**

Use for:

- logs
- technical identifiers
- filenames
- troubleshooting output

Weights:

- 400
- 500

Do not use JetBrains Mono as a general brand treatment.

---

## Validated type scale

| Role | Family | Size / line | Weight |
|---|---|---:|---:|
| Hero | Instrument Sans | 64 / 70 px | 600 |
| H1 | Instrument Sans | 52 / 60 px | 600 |
| H2 | Instrument Sans | 40 / 48 px | 600 |
| H3 | Instrument Sans | 30 / 38 px | 500–600 |
| UI Heading | Inter | 22 / 28 px | 600 |
| Body | Inter | 17 / 26 px | 400 |
| Body Small | Inter | 15 / 22 px | 400 |
| Label | Inter | 14 / 20 px | 500 |
| Button | Inter | 15 / 20 px | 600 |
| Caption | Inter | 13 / 18 px | 400 |
| Diagnostics | JetBrains Mono | 13 / 20 px | 400–500 |

---

## Web fallback stacks

```css
--font-brand: "Instrument Sans", "Helvetica Neue", Arial, sans-serif;
--font-ui: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
--font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
```

The final visual check should be performed in a real browser with the intended webfont files loaded. Static image previews may render fallback fonts.

---

## Font licensing

The selected font families are open-source and published under the **SIL Open Font License 1.1**:

- Instrument Sans — OFL-1.1
- Inter — OFL-1.1
- JetBrains Mono typeface — OFL-1.1

This permits normal embedding/bundling use subject to each font's license terms.

Repository sources:

- Instrument Sans: `github.com/Instrument/instrument-sans`
- Inter: `github.com/rsms/inter`
- JetBrains Mono: `github.com/JetBrains/JetBrainsMono`

Do not copy font binaries into the Terento repository until the exact files/versions and their license notices have been recorded in `THIRD_PARTY_NOTICES.md`.

When fonts are added:

1. pin the source/version;
2. include the relevant OFL license notice;
3. record the dependency in `THIRD_PARTY_NOTICES.md`;
4. prefer WOFF2 for web delivery;
5. subset only if the license and tooling workflow remain compliant.
