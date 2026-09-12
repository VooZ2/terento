import CoreGraphics
import Foundation

/// One page-level geometry contract for every primary Terento screen.
/// Components may add semantic spacing inside this shell, but equivalent
/// titles, lists, section headings, and footers all inherit these bounds.
enum TerentoPageLayout: Sendable {
    static let maxWidth: CGFloat = 1_040
    static let horizontalPadding: CGFloat = 42
    static let primaryTopPadding: CGFloat = 58
    static let primaryBottomPadding: CGFloat = 42
    static let titleSubtitleSpacing: CGFloat = 8
    static let firstSectionTopPadding: CGFloat = 18
    static let sectionSpacing: CGFloat = 14
    static let sectionContentTopPadding: CGFloat = 6
    static let sectionHeaderMinHeight: CGFloat = 26
    static let sectionHeaderChevronWidth: CGFloat = 14
    static let sectionHeaderChevronHeight: CGFloat = sectionHeaderMinHeight
    static let sectionHeaderItemSpacing: CGFloat = 8
    static let footerMinHeight: CGFloat = 50
    static let footerBottomPadding: CGFloat = 42
}

/// Stable window metrics for the normal Terento working layout. The window
/// remains freely resizable; these values only describe the fresh-launch
/// default and the smallest usable layout.
enum TerentoWindowPresentation: Sendable {
    static let defaultWidth: CGFloat = 1_180
    static let defaultHeight: CGFloat = 820
    static let minimumWidth: CGFloat = 920
    static let minimumHeight: CGFloat = 600

    // Compatibility aliases for non-view callers and existing presentation
    // tests. Views use TerentoPageLayout directly.
    static let contentMaxWidth: CGFloat = TerentoPageLayout.maxWidth
    static let contentHorizontalPadding: CGFloat = TerentoPageLayout.horizontalPadding
}

/// Pure frame calculation shared by the one-time migration and geometry tests.
/// Sizes are frame sizes here, after AppKit has added the title bar.
enum TerentoWindowFrameLayout {
    static func centeredOrigin(windowSize: CGSize, visibleFrame: CGRect) -> CGPoint {
        CGPoint(
            x: visibleFrame.minX + max(0, (visibleFrame.width - windowSize.width) / 2),
            y: visibleFrame.maxY - windowSize.height
                - max(0, (visibleFrame.height - windowSize.height) / 2)
        )
    }

    static func fittedFrame(current: CGRect, desiredSize: CGSize, visibleFrame: CGRect) -> CGRect {
        let size = CGSize(
            width: min(desiredSize.width, visibleFrame.width),
            height: min(desiredSize.height, visibleFrame.height)
        )
        return CGRect(
            x: min(max(current.minX, visibleFrame.minX), visibleFrame.maxX - size.width),
            y: min(max(current.maxY - size.height, visibleFrame.minY), visibleFrame.maxY - size.height),
            width: size.width,
            height: size.height
        )
    }
}
