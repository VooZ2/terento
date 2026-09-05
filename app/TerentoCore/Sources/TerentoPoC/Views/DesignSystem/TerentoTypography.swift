import AppKit
import SwiftUI

extension Font {
    static func terentoHeading(size: CGFloat, weight: Font.Weight) -> Font {
        NSFont(name: TerentoGeneratedTokens.Typography.brandFontName, size: size) == nil
            ? .system(size: size, weight: weight)
            : .custom(TerentoGeneratedTokens.Typography.brandFontName, size: size).weight(weight)
    }

    static func terentoUI(size: CGFloat, weight: Font.Weight) -> Font {
        NSFont(name: TerentoGeneratedTokens.Typography.uiFontName, size: size) == nil
            ? .system(size: size, weight: weight)
            : .custom(TerentoGeneratedTokens.Typography.uiFontName, size: size).weight(weight)
    }

    static func terentoBody(size: CGFloat, weight: Font.Weight) -> Font {
        NSFont(name: TerentoGeneratedTokens.Typography.uiFontName, size: size) == nil
            ? .system(size: size, weight: weight)
            : .custom(TerentoGeneratedTokens.Typography.uiFontName, size: size).weight(weight)
    }
}
