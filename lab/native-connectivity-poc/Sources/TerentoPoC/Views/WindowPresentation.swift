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
    static let sectionHeaderChevronHeight: CGFloat = 18
    static let sectionHeaderItemSpacing: CGFloat = 8
    static let footerMinHeight: CGFloat = 50
    static let footerBottomPadding: CGFloat = 42
}

/// Stable window metrics for the normal Terento working layout. The window
/// remains freely resizable; these values only describe the fresh-launch
/// default and the smallest usable layout.
enum TerentoWindowPresentation: Sendable {
    static let defaultWidth: CGFloat = 1_100
    static let defaultHeight: CGFloat = 700
    static let minimumWidth: CGFloat = 920
    static let minimumHeight: CGFloat = 600

    // Compatibility aliases for non-view callers and existing presentation
    // tests. Views use TerentoPageLayout directly.
    static let contentMaxWidth: CGFloat = TerentoPageLayout.maxWidth
    static let contentHorizontalPadding: CGFloat = TerentoPageLayout.horizontalPadding
}
