import AppKit
import Foundation
import SwiftUI

/// The app type scale and the bundled brand fonts. With a path argument the
/// fonts are registered from that built Terento.app, exactly as at launch.
@main
struct TypographyTests {
    static func main() {
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
    }

    private static func expect(_ condition: Bool, _ message: String) {
        if !condition { fail(message) }
    }

    private static func fail(_ message: String) -> Never {
        FileHandle.standardError.write(Data("FAIL: \(message)\n".utf8))
        exit(1)
    }
}
