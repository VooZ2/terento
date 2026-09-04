import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const sharp = require("sharp");

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const mastersDir = path.join(projectRoot, "site", "assets", "app", "masters");
const optimizedDir = path.join(projectRoot, "site", "assets", "app", "optimized");
const widths = [640, 960, 1280, 1600];
const sourceNames = [
  "your-garmin.png",
  "install-maps.png",
  "ready-to-install.png",
  "installing-maps.png",
  "manage-maps.png",
  "about.png",
  "maps-done.png",
];

await fs.mkdir(optimizedDir, { recursive: true });

for (const sourceName of sourceNames) {
  const sourcePath = path.join(mastersDir, sourceName);
  const metadata = await sharp(sourcePath).metadata();
  const sourceWidth = metadata.width;
  const baseName = path.basename(sourceName, path.extname(sourceName));
  const outputWidths = widths.filter((width) => width < sourceWidth);

  for (const width of outputWidths) {
    const resized = sharp(sourcePath).resize({
      width,
      fit: "inside",
      withoutEnlargement: true,
    });
    await resized.clone().avif({ quality: 78, effort: 6 }).toFile(path.join(optimizedDir, `${baseName}-${width}.avif`));
    await resized.clone().webp({ quality: 88, effort: 6 }).toFile(path.join(optimizedDir, `${baseName}-${width}.webp`));
    if (width === outputWidths.at(-1)) {
      await resized.clone().png({ compressionLevel: 9, adaptiveFiltering: true }).toFile(path.join(optimizedDir, `${baseName}-${width}.png`));
    }
  }
}

const socialMaster = path.join(mastersDir, "your-garmin.png");
const socialScreenshot = await sharp(socialMaster)
  .resize({ width: 650, height: 412, fit: "inside", withoutEnlargement: true })
  .png()
  .toBuffer();
const socialBackdrop = Buffer.from(`<svg width="1200" height="630" xmlns="http://www.w3.org/2000/svg">
  <rect width="1200" height="630" fill="#F7F3EC"/>
  <path d="M0 118 C180 56 318 86 447 145 S708 214 860 128 S1040 74 1200 112" fill="none" stroke="#D7DDDA" stroke-width="2"/>
  <path d="M0 510 C180 442 322 470 458 523 S742 575 888 488 S1050 446 1200 477" fill="none" stroke="#D7DDDA" stroke-width="2"/>
  <circle cx="1038" cy="106" r="60" fill="#9AA58B" opacity=".36"/>
  <circle cx="108" cy="522" r="44" fill="#7898A8" opacity=".28"/>
  <rect x="442" y="86" width="688" height="452" rx="20" fill="#FFFFFF" opacity=".55" stroke="#D7DDDA" stroke-width="2"/>
</svg>`);
const socialType = Buffer.from(`<svg width="1200" height="630" xmlns="http://www.w3.org/2000/svg">
  <text x="170" y="125" fill="#222A2B" font-family="Instrument Sans, Helvetica Neue, Arial, sans-serif" font-size="50" font-weight="600" letter-spacing="-1.5">Terento</text>
  <text x="90" y="250" fill="#222A2B" font-family="Instrument Sans, Helvetica Neue, Arial, sans-serif" font-size="42" font-weight="600" letter-spacing="-1.1">Your device, ready</text>
  <text x="90" y="300" fill="#222A2B" font-family="Instrument Sans, Helvetica Neue, Arial, sans-serif" font-size="42" font-weight="600" letter-spacing="-1.1">for where you're going.</text>
  <text x="90" y="382" fill="#6D706F" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="22">A native macOS app for Garmin smartwatches.</text>
</svg>`);
const logo = await sharp(path.join(projectRoot, "site", "assets", "logo-sky.svg"))
  .resize({ width: 58, height: 58, fit: "contain" })
  .png()
  .toBuffer();

await sharp(socialBackdrop)
  .composite([
    { input: logo, left: 90, top: 80 },
    { input: socialScreenshot, left: 460, top: 106 },
    { input: socialType, left: 0, top: 0 },
  ])
  .png({ compressionLevel: 9, adaptiveFiltering: true })
  .toFile(path.join(projectRoot, "site", "og.png"));

console.log(`Optimized ${sourceNames.length} screenshots at ${widths.length} responsive widths and generated site/og.png`);
