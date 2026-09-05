// Generated from brand/DESIGN_TOKENS.json. Do not edit manually.
import SwiftUI

enum TerentoGeneratedTokens {
    enum Brand {
        static let sky = Color(terentoHex: 0x7898A8)
        static let lichen = Color(terentoHex: 0x9AA58B)
        static let warmStone = Color(terentoHex: 0xB39A78)
        static let offWhite = Color(terentoHex: 0xF7F3EC)
        static let graphite = Color(terentoHex: 0x222A2B)
    }

    enum Functional {
        static let interactivePrimary = Color(terentoHex: 0x577787)
        static let interactiveHover = Color(terentoHex: 0x4F6E7E)
        static let secondaryText = Color(terentoHex: 0x6D706F)
        static let lichenDark = Color(terentoHex: 0x5F6D53)
        static let stoneDark = Color(terentoHex: 0x7B6246)
        static let errorRust = Color(terentoHex: 0x8A4F47)
        static let selectedTint = Color(terentoHex: 0xE7EEF1)
    }

    enum Light {
        static let backgroundPrimary = Color(terentoHex: 0xF7F3EC)
        static let backgroundSecondary = Color(terentoHex: 0xF1EEE7)
        static let surfacePrimary = Color(terentoHex: 0xFFFFFF)
        static let surfaceElevated = Color(terentoHex: 0xFCFBF8)
        static let textPrimary = Color(terentoHex: 0x222A2B)
        static let textSecondary = Color(terentoHex: 0x6D706F)
        static let textMuted = Color(terentoHex: 0x7E8481)
        static let textDisabled = Color(terentoHex: 0x9EA5A2)
        static let borderSubtle = Color(terentoHex: 0xD7DDDA)
        static let selectedBackground = Color(terentoHex: 0xE7EEF1)
        static let selectedBorder = Color(terentoHex: 0x577787)
        static let focusRing = Color(terentoHex: 0x577787)
        static let progressTrack = Color(terentoHex: 0xDDE6E5)
        static let progressFill = Color(terentoHex: 0x577787)
    }

    enum Status {
        static let success = Color(terentoHex: 0x5F6D53)
        static let warning = Color(terentoHex: 0x7B6246)
        static let error = Color(terentoHex: 0x8A4F47)
        static let info = Color(terentoHex: 0x577787)
    }

    enum Typography {
        static let brandFontName = "Instrument Sans"
        static let uiFontName = "Inter"
        static let monoFontName = "JetBrains Mono"
    }
}

private extension Color {
    init(terentoHex hex: UInt32) {
        self.init(
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255
        )
    }
}
