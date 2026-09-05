import SwiftUI

/// Semantic colors used by the native app. Canonical values come from the
/// generated token facade; local opacity is retained only where it is part of
/// the existing visual contract.
enum TerentoColors {
    static let sky = TerentoGeneratedTokens.Brand.sky
    static let lichen = TerentoGeneratedTokens.Brand.lichen
    static let lichenDark = TerentoGeneratedTokens.Functional.lichenDark
    static let warmStone = TerentoGeneratedTokens.Brand.warmStone
    static let canvas = TerentoGeneratedTokens.Light.backgroundPrimary
    static let sidebar = TerentoGeneratedTokens.Light.backgroundSecondary
    static let surface = TerentoGeneratedTokens.Light.surfacePrimary.opacity(0.78)
    static let helpSurface = TerentoGeneratedTokens.Light.surfacePrimary.opacity(0.48)
    static let graphite = TerentoGeneratedTokens.Brand.graphite
    static let secondaryText = TerentoGeneratedTokens.Functional.secondaryText
    static let border = TerentoGeneratedTokens.Light.borderSubtle
    static let sidebarBorder = TerentoGeneratedTokens.Light.borderSubtle.opacity(0.72)
    static let selectedBackground = TerentoGeneratedTokens.Light.selectedBackground
    // Component-only disabled border. No canonical brand token represents it;
    // keep the existing value unchanged for visual parity.
    static let inactiveBorder = Color(
        red: 199.0 / 255.0,
        green: 201.0 / 255.0,
        blue: 197.0 / 255.0
    )
    static let progressTrack = TerentoGeneratedTokens.Light.progressTrack
    static let interactive = TerentoGeneratedTokens.Functional.interactivePrimary
    static let warning = TerentoGeneratedTokens.Functional.stoneDark
    static let error = TerentoGeneratedTokens.Status.error
}
