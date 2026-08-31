import Foundation

@main
struct Stage7NavigationTests {
    static func main() {
        let destinations = TerentoSection.allCases.map(\.rawValue)

        expect(
            destinations == ["Device", "Install maps", "Manage maps", "About"],
            "sidebar exposes the three direct product destinations and About"
        )
        expect(
            TerentoSection.installMaps != TerentoSection.manageMaps,
            "Install maps and Manage maps are distinct destinations"
        )
        expect(
            TerentoWindowPresentation.defaultWidth >= 1_040
                && TerentoWindowPresentation.defaultWidth <= 1_160
                && TerentoWindowPresentation.defaultHeight >= 660
                && TerentoWindowPresentation.defaultHeight <= 760,
            "fresh launches use the approved working window size"
        )
        expect(
            TerentoWindowPresentation.minimumWidth == 920
                && TerentoWindowPresentation.minimumHeight == 600
                && TerentoWindowPresentation.defaultWidth > TerentoWindowPresentation.minimumWidth
                && TerentoWindowPresentation.defaultHeight > TerentoWindowPresentation.minimumHeight,
            "the window remains resizable with a usable minimum"
        )
        expect(
            TerentoWindowPresentation.contentMaxWidth == 1_040
                && TerentoWindowPresentation.contentHorizontalPadding == 42,
            "large windows keep a stable content max-width and grid padding"
        )
        expect(
            TerentoPageLayout.maxWidth == TerentoWindowPresentation.contentMaxWidth
                && TerentoPageLayout.horizontalPadding == TerentoWindowPresentation.contentHorizontalPadding,
            "all primary screens use the shared page layout contract"
        )
        expect(
            TerentoPageLayout.titleSubtitleSpacing == 8
                && TerentoPageLayout.firstSectionTopPadding == 18,
            "Install and Manage share title and first-section spacing"
        )
        expect(
            TerentoPageLayout.sectionSpacing == 14
                && TerentoPageLayout.sectionContentTopPadding == 6,
            "Install and Manage share section rhythm"
        )
        expect(
            TerentoPageLayout.sectionHeaderMinHeight == 26
                && TerentoPageLayout.sectionHeaderChevronWidth == 14
                && TerentoPageLayout.sectionHeaderChevronHeight
                    == TerentoPageLayout.sectionHeaderMinHeight
                && TerentoPageLayout.sectionHeaderItemSpacing == 8,
            "Install and Manage share section-header geometry"
        )
        expect(
            TerentoPageLayout.footerMinHeight == 50
                && TerentoPageLayout.footerBottomPadding == 42,
            "all Back and primary actions share footer geometry"
        )

        print("PASS: 10 Stage 7 navigation/window presentation tests")
    }

    private static func expect(_ condition: Bool, _ message: String) {
        if condition {
            print("PASS: \(message)")
        } else {
            print("FAIL: \(message)")
            exit(1)
        }
    }
}
