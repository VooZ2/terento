import AppKit
import Foundation

private let sky = "#7898A8"
private let alpineOffWhite = "#F7F3EC"
private let canvasSize = 1024
private let outputSizes = [16, 32, 64, 128, 256, 512, 1024]

let repositoryRoot = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
let sourceURL = repositoryRoot.appendingPathComponent("brand/logo/logo.svg")
let outputDirectory = repositoryRoot.appendingPathComponent(
    "app/Terento/Assets.xcassets/AppIcon.appiconset"
)

guard let canonicalSVG = try? String(contentsOf: sourceURL, encoding: .utf8) else {
    fputs("Unable to read canonical symbol at \(sourceURL.path)\n", stderr)
    exit(1)
}

guard let groupStart = canonicalSVG.range(of: "<g "),
      let groupEnd = canonicalSVG.range(
          of: "</g>",
          range: groupStart.lowerBound..<canonicalSVG.endIndex
      ) else {
    fputs("Canonical symbol does not contain the expected path group\n", stderr)
    exit(1)
}

let canonicalGroup = String(canonicalSVG[groupStart.lowerBound..<groupEnd.upperBound])
let recoloredGroup = canonicalGroup.replacingOccurrences(
    of: "fill=\"#000000\"",
    with: "fill=\"\(alpineOffWhite)\""
)

// The paths come directly from brand/logo/logo.svg. Only the square app
// background, scale, and color are composed here; symbol geometry is untouched.
let composedSVG = """
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 \(canvasSize) \(canvasSize)" width="\(canvasSize)" height="\(canvasSize)">
  <rect width="\(canvasSize)" height="\(canvasSize)" fill="\(sky)"/>
  <svg x="223" y="174" width="578" height="676" viewBox="0 0 780 913" preserveAspectRatio="xMidYMid meet">
    \(recoloredGroup)
  </svg>
</svg>
"""

let temporarySVGURL = URL(fileURLWithPath: NSTemporaryDirectory())
    .appendingPathComponent("terento-app-icon-\(ProcessInfo.processInfo.processIdentifier).svg")
do {
    try Data(composedSVG.utf8).write(to: temporarySVGURL, options: .atomic)
} catch {
    fputs("Unable to create temporary icon SVG: \(error)\n", stderr)
    exit(1)
}
defer { try? FileManager.default.removeItem(at: temporarySVGURL) }

guard let sourceImage = NSImage(contentsOf: temporarySVGURL) else {
    fputs("AppKit could not rasterize the composed icon SVG\n", stderr)
    exit(1)
}

try? FileManager.default.createDirectory(
    at: outputDirectory,
    withIntermediateDirectories: true
)

for size in outputSizes {
    guard let bitmap = NSBitmapImageRep(
        bitmapDataPlanes: nil,
        pixelsWide: size,
        pixelsHigh: size,
        bitsPerSample: 8,
        samplesPerPixel: 4,
        hasAlpha: true,
        isPlanar: false,
        colorSpaceName: .deviceRGB,
        bitmapFormat: [],
        bytesPerRow: 0,
        bitsPerPixel: 32
    ) else {
        fputs("Unable to allocate \(size)x\(size) bitmap\n", stderr)
        exit(1)
    }

    bitmap.size = NSSize(width: size, height: size)
    guard let context = NSGraphicsContext(bitmapImageRep: bitmap) else {
        fputs("Unable to create graphics context for \(size)x\(size) bitmap\n", stderr)
        exit(1)
    }

    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = context
    sourceImage.draw(
        in: NSRect(x: 0, y: 0, width: size, height: size),
        from: .zero,
        operation: .copy,
        fraction: 1
    )
    context.flushGraphics()
    NSGraphicsContext.restoreGraphicsState()

    let outputURL = outputDirectory.appendingPathComponent("AppIcon-\(size).png")
    guard let png = bitmap.representation(using: .png, properties: [:]) else {
        fputs("Unable to encode \(size)x\(size) PNG\n", stderr)
        exit(1)
    }
    do {
        try png.write(to: outputURL, options: .atomic)
    } catch {
        fputs("Unable to write \(outputURL.path): \(error)\n", stderr)
        exit(1)
    }
}

print("Generated Terento macOS AppIcon assets from \(sourceURL.path)")
