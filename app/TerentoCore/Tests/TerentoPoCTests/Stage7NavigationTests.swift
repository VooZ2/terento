import CoreGraphics
import Foundation

@main
struct Stage7NavigationTests {
    static func main() {
        let destinations = TerentoSection.allCases.map(\.rawValue)

        expect(
            destinations == ["Device", "Install maps", "Manage maps"],
            "sidebar exposes only the three direct product destinations; About belongs to the app menu"
        )
        expect(
            TerentoSection.installMaps != TerentoSection.manageMaps,
            "Install maps and Manage maps are distinct destinations"
        )
        expect(
            TerentoWindowPresentation.defaultWidth == 1_180
                && TerentoWindowPresentation.defaultHeight == 820,
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

        let screen = CGRect(x: 0, y: 0, width: 1440, height: 900)
        let grown = TerentoWindowFrameLayout.fittedFrame(
            current: CGRect(x: 200, y: 100, width: 1100, height: 760),
            desiredSize: CGSize(width: 1180, height: 848),
            visibleFrame: screen
        )
        expect(
            grown.size == CGSize(width: 1180, height: 848) && screen.contains(grown),
            "migration grows the workspace and keeps its title bar inside the screen"
        )
        expect(
            grown.maxY == 860,
            "growing a window preserves its top edge when the screen allows it"
        )
        let compactScreen = CGRect(x: -1280, y: 30, width: 1280, height: 720)
        let fitted = TerentoWindowFrameLayout.fittedFrame(
            current: CGRect(x: -200, y: 80, width: 1500, height: 1000),
            desiredSize: CGSize(width: 1500, height: 1000),
            visibleFrame: compactScreen
        )
        expect(
            fitted == compactScreen,
            "oversized frames fit a smaller secondary screen with a negative origin"
        )
        let largerFrame = CGRect(x: 20, y: 20, width: 1300, height: 860)
        expect(
            TerentoWindowFrameLayout.fittedFrame(
                current: largerFrame,
                desiredSize: largerFrame.size,
                visibleFrame: screen
            ) == largerFrame,
            "an already larger frame remains unchanged when it fits the screen"
        )
        let offscreen = TerentoWindowFrameLayout.fittedFrame(
            current: CGRect(x: 1800, y: -500, width: 1180, height: 848),
            desiredSize: CGSize(width: 1180, height: 848),
            visibleFrame: screen
        )
        expect(
            screen.contains(offscreen) && offscreen.size == CGSize(width: 1180, height: 848),
            "offscreen restored positions are repositioned without shrinking a fitting window"
        )

        print("PASS: 15 Stage 7 navigation/window presentation tests")
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
