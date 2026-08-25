import AppKit
import Foundation

let arguments = CommandLine.arguments
guard arguments.count == 3 else {
    fputs("usage: generate-social-image.swift SOURCE OUTPUT\n", stderr)
    exit(2)
}

let sourceURL = URL(fileURLWithPath: arguments[1])
let outputURL = URL(fileURLWithPath: arguments[2])
guard let source = NSImage(contentsOf: sourceURL) else {
    fputs("Could not read source image\n", stderr)
    exit(1)
}

let canvasSize = NSSize(width: 1200, height: 630)
let canvas = NSImage(size: canvasSize)
canvas.lockFocusFlipped(false)

NSColor(calibratedRed: 0.969, green: 0.953, blue: 0.925, alpha: 1).setFill()
NSRect(origin: .zero, size: canvasSize).fill()

let panelRect = NSRect(x: 96, y: 16, width: 1008, height: 598)
let panelPath = NSBezierPath(roundedRect: panelRect, xRadius: 18, yRadius: 18)
NSColor(calibratedWhite: 1, alpha: 0.62).setFill()
panelPath.fill()
NSColor(calibratedRed: 0.85, green: 0.87, blue: 0.85, alpha: 0.95).setStroke()
panelPath.lineWidth = 1
panelPath.stroke()

let available = NSSize(width: 960, height: 570)
let scale = min(available.width / source.size.width, available.height / source.size.height)
let drawSize = NSSize(width: source.size.width * scale, height: source.size.height * scale)
let drawRect = NSRect(
    x: canvasSize.width / 2 - drawSize.width / 2,
    y: canvasSize.height / 2 - drawSize.height / 2,
    width: drawSize.width,
    height: drawSize.height
)
source.draw(in: drawRect, from: NSRect(origin: .zero, size: source.size), operation: .sourceOver, fraction: 1)
canvas.unlockFocus()

guard let tiff = canvas.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiff),
      let png = bitmap.representation(using: .png, properties: [:]) else {
    fputs("Could not encode PNG\n", stderr)
    exit(1)
}

try png.write(to: outputURL, options: .atomic)
