import AppKit
import CoreText
import SwiftUI

/// The native app's only text sizes (owner decision 2026-11-22). Every text
/// style in the app is one of these roles; a weight may change for emphasis,
/// the size never does. SF Symbol sizes are icon metrics, not text roles.
enum TerentoTypography {
    enum Role: CaseIterable, Sendable {
        /// Page titles: "Your Garmin", "Install maps", "Manage maps".
        case pageTitle
        /// The connected watch name, and the About and Diagnostics window titles.
        case deviceName
        /// Page subtitles and dialog titles.
        case lede
        /// Map row titles, section labels and group headers.
        case rowTitle
        /// All secondary text: row metadata, sizes, storage, counts, buttons.
        case meta
        /// The smallest notes only: download estimate, badges.
        case caption

        var size: CGFloat {
            switch self {
            case .pageTitle: return 42
            case .deviceName: return 28
            case .lede: return 19
            case .rowTitle: return 16
            case .meta: return 14
            case .caption: return 12
            }
        }

        var defaultWeight: Font.Weight {
            switch self {
            case .pageTitle, .deviceName, .rowTitle: return .semibold
            case .lede, .meta, .caption: return .medium
            }
        }

        /// Instrument Sans for the two headline roles, Inter for the rest.
        var usesBrandFace: Bool {
            self == .pageTitle || self == .deviceName
        }
    }

    /// Every allowed text size, for the type-scale contract test.
    static let allowedSizes: Set<CGFloat> = Set(Role.allCases.map(\.size))

    /// The sidebar wordmark is part of the logo lockup, not a text role. Its
    /// size matches the website header lockup.
    static let wordmarkSize: CGFloat = 22
}

/// The brand fonts ship inside Terento.app (SIL OFL 1.1, licence files next
/// to them in Resources/Fonts) and are registered for this process at launch,
/// so every Mac shows Inter and Instrument Sans like the website.
enum TerentoBundledFonts {
    static let fileNames = [
        "Inter-Regular",
        "Inter-Medium",
        "Inter-SemiBold",
        "InstrumentSans-Regular",
        "InstrumentSans-SemiBold"
    ]

    /// Registers each bundled font once. Returns the files that could not be
    /// registered; an already registered font is not a failure.
    @discardableResult
    static func register(bundle: Bundle = .module) -> [String] {
        fileNames.filter { name in
            guard let url = bundle.url(forResource: name, withExtension: "ttf")
                ?? bundle.url(forResource: name, withExtension: "ttf", subdirectory: "Fonts")
            else { return true }
            var error: Unmanaged<CFError>?
            if CTFontManagerRegisterFontsForURL(url as CFURL, .process, &error) { return false }
            guard let failure = error?.takeRetainedValue() else { return true }
            return CFErrorGetCode(failure) != CTFontManagerError.alreadyRegistered.rawValue
        }
    }
}

extension Font {
    /// A text role from the app type scale, optionally with another weight.
    static func terento(_ role: TerentoTypography.Role, weight: Font.Weight? = nil) -> Font {
        let weight = weight ?? role.defaultWeight
        let name = role.usesBrandFace
            ? TerentoGeneratedTokens.Typography.brandFontName
            : TerentoGeneratedTokens.Typography.uiFontName
        return terentoFace(name, size: role.size, weight: weight)
    }

    /// The sidebar wordmark beside the logo symbol.
    static var terentoWordmark: Font {
        terentoFace(TerentoGeneratedTokens.Typography.brandFontName,
            size: TerentoTypography.wordmarkSize, weight: .semibold)
    }

    private static func terentoFace(_ name: String, size: CGFloat, weight: Font.Weight) -> Font {
        NSFont(name: name, size: size) == nil
            ? .system(size: size, weight: weight)
            : .custom(name, size: size).weight(weight)
    }
}
