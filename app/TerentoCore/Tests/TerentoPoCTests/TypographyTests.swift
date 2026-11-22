import AppKit
import Foundation
import SwiftUI

/// The app type scale and the bundled brand fonts. With a path argument the
/// fonts are registered from that built Terento.app, exactly as at launch.
@main
struct TypographyTests {
    @MainActor static func main() {
        let arguments = CommandLine.arguments
        guard arguments.count == 2 else {
            fail("usage: typography-tests <Terento.app or font directory>")
        }
        guard let bundle = Bundle(path: arguments[1]) else {
            fail("no bundle at \(arguments[1])")
        }

        expect(TerentoTypography.allowedSizes == [42, 28, 19, 16, 14, 12],
            "the app uses exactly the six approved text sizes")
        expect(TerentoTypography.Role.pageTitle.size == 42 && TerentoTypography.Role.deviceName.size == 28
            && TerentoTypography.Role.lede.size == 19 && TerentoTypography.Role.rowTitle.size == 16
            && TerentoTypography.Role.meta.size == 14 && TerentoTypography.Role.caption.size == 12,
            "each role keeps its approved size")
        expect(TerentoTypography.Role.pageTitle.usesBrandFace && TerentoTypography.Role.deviceName.usesBrandFace
            && !TerentoTypography.Role.lede.usesBrandFace && !TerentoTypography.Role.meta.usesBrandFace,
            "Instrument Sans for the headline roles, Inter for the rest")

        let failed = TerentoBundledFonts.register(bundle: bundle)
        expect(failed.isEmpty, "every bundled font registers: \(failed)")
        expect(TerentoBundledFonts.register(bundle: bundle).isEmpty, "registering twice is not a failure")

        expect(NSFont(name: "Inter", size: 14) != nil, "NSFont(name: \"Inter\", size: 14) is available")
        expect(NSFont(name: "Instrument Sans", size: 42) != nil, "NSFont(name: \"Instrument Sans\", size: 42) is available")
        for postScriptName in ["Inter-Regular", "Inter-Medium", "Inter-SemiBold",
                               "InstrumentSans-Regular", "InstrumentSans-SemiBold"] {
            expect(NSFont(name: postScriptName, size: 14)?.fontName == postScriptName, "\(postScriptName) is registered")
        }
        let interFaces = NSFontManager.shared.availableMembers(ofFontFamily: "Inter")?.compactMap { $0[0] as? String } ?? []
        expect(Set(["Inter-Regular", "Inter-Medium", "Inter-SemiBold"]).isSubset(of: interFaces),
            "the Inter family has the regular, medium and semibold faces: \(interFaces)")
        let brandFaces = NSFontManager.shared.availableMembers(ofFontFamily: "Instrument Sans")?.compactMap { $0[0] as? String } ?? []
        expect(Set(["InstrumentSans-Regular", "InstrumentSans-SemiBold"]).isSubset(of: brandFaces),
            "the Instrument Sans family has the regular and semibold faces: \(brandFaces)")

        print("PASS: app type scale and bundled brand fonts")

        guard #available(macOS 13, *) else { fail("the group header baseline test needs macOS 13") }
        _ = NSApplication.shared
        testGroupHeaderBaseline()
    }

    /// Manage maps group header (owner QA 2026-11-22): the name and the count
    /// sit on one baseline. Renders the shared label at 2x with the bundled
    /// fonts and compares the bottom of the flat "B" with the bottom of the
    /// flat "1". Centred lines put the count about 3 px (1.5 pt) higher.
    @available(macOS 13, *)
    @MainActor private static func testGroupHeaderBaseline() {
        let renderer = ImageRenderer(content: TerentoTitleCountLabel(title: "BBBike", count: "1 map", spacing: 8)
            .fixedSize()
            .padding(4))
        renderer.scale = 2
        guard let image = renderer.cgImage else { fail("the group header label did not render") }
        let width = image.width, height = image.height
        var pixels = [UInt8](repeating: 0, count: width * height * 4)
        let drawn = pixels.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(data: buffer.baseAddress, width: width, height: height,
                bitsPerComponent: 8, bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return false }
            context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        expect(drawn, "the rendered group header label could not be read")
        func ink(_ x: Int, _ y: Int) -> Bool { pixels[(y * width + x) * 4 + 3] >= 128 }
        let inkColumns = (0..<width).filter { x in (0..<height).contains { ink(x, $0) } }
        guard let titleStart = inkColumns.first else { fail("the group header label has no text") }
        // The name ends at the first gap wider than any gap between its letters.
        var titleEnd = titleStart
        for x in inkColumns.dropFirst() {
            if x - titleEnd > 10 { break }
            titleEnd = x
        }
        guard let countStart = inkColumns.first(where: { $0 > titleEnd + 10 }) else {
            fail("the count is missing from the group header label")
        }
        // Rows grow downwards in the bitmap: the baseline is the lowest ink row.
        // The band covers the whole "1" (its flag alone does not reach the baseline).
        func baseline(_ columns: Range<Int>) -> Int? {
            (0..<height).last { y in columns.contains { ink($0, y) } }
        }
        let firstLetter = titleStart..<min(titleStart + 10, titleEnd + 1)
        let firstDigit = countStart..<min(countStart + 12, width)
        guard let name = baseline(firstLetter), let count = baseline(firstDigit) else {
            fail("no baseline found in the group header label")
        }
        expect(abs(name - count) <= 1,
            "the count sits on the name's baseline (name \(name) px, count \(count) px at 2x)")
        print("PASS: group header name and count share one baseline (name \(name) px, count \(count) px at 2x)")
    }

    private static func expect(_ condition: Bool, _ message: String) {
        if !condition { fail(message) }
    }

    private static func fail(_ message: String) -> Never {
        FileHandle.standardError.write(Data("FAIL: \(message)\n".utf8))
        exit(1)
    }
}
