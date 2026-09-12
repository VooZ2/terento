import AppKit
import SwiftUI

@main
struct TerentoEntryPoint {
    static func main() {
        if MTPFinishingWorker.runIfRequested() { return }
        Task.detached(priority: .utility) { MapAcquisitionWorkspace.scavengeStale() }
        TerentoPoCApp.main()
    }
}

struct TerentoPoCApp: App {
    @StateObject private var deviceEngine = DeviceEngine()
    @StateObject private var mapEngine = MapEngine()
    @StateObject private var appUpdateController = AppUpdateController()
    @StateObject private var evidenceController = InstallationEvidenceController()
    @StateObject private var mapStatisticsController = MapStatisticsEventController()
    @Environment(\.openWindow) private var openWindow

    var body: some Scene {
        WindowGroup("Terento") {
            ContentView(
                deviceEngine: deviceEngine,
                mapEngine: mapEngine,
                appUpdateController: appUpdateController,
                evidenceController: evidenceController,
                mapStatisticsController: mapStatisticsController
            )
            .background(TerentoWindowConfigurator())
            .task {
                appUpdateController.startAutomaticCheck()
            }
        }
        .defaultSize(
            width: TerentoWindowPresentation.defaultWidth,
            height: TerentoWindowPresentation.defaultHeight
        )
        .windowResizability(.automatic)
        .windowStyle(.titleBar)
        .commands {
            CommandGroup(replacing: .appInfo) {
                Button("About Terento") {
                    openWindow(id: "about")
                }
                Button("Diagnostics") {
                    openWindow(id: "diagnostics")
                }
                Button("Check updates") {
                    appUpdateController.checkForUpdates()
                }
            }
            CommandGroup(replacing: .help) {
                Button("Terento Website") {
                    openExternalURL(TerentoAppLinks.website)
                }
                Button("Documentation") {
                    openExternalURL(TerentoAppLinks.documentation)
                }
                Button("Report an Issue") {
                    openExternalURL(TerentoAppLinks.issues)
                }
                Button("GitHub Repository") {
                    openExternalURL(TerentoAppLinks.repository)
                }
            }
        }
        Window("About Terento", id: "about") {
            AboutTerentoView(appUpdateController: appUpdateController)
                .background(TerentoSecondaryWindowPlacement())
        }
        .defaultSize(width: 560, height: 580)
        .windowResizability(.automatic)
        .windowStyle(.titleBar)
        Window("Diagnostics", id: "diagnostics") {
            DiagnosticsView(
                evidenceController: evidenceController,
                mapStatisticsController: mapStatisticsController
            )
            .background(TerentoSecondaryWindowPlacement())
        }
        .defaultSize(width: 520, height: 600)
        .windowResizability(.contentSize)
        .windowStyle(.titleBar)
    }

    private func openExternalURL(_ url: URL) {
        NSWorkspace.shared.open(url)
    }
}

/// SwiftUI's defaultSize is only consulted when macOS has no restored frame.
/// A one-time migration grows the catalog workspace within its screen,
/// while preserving larger restored frames and later user resizing.
private struct TerentoWindowConfigurator: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.async {
            guard let window = view.window else { return }

            let visibleFrame = window.screen?.visibleFrame ?? NSScreen.main?.visibleFrame ?? window.frame
            let minimumFrame = window.frameRect(forContentRect: NSRect(
                origin: .zero,
                size: NSSize(
                    width: TerentoWindowPresentation.minimumWidth,
                    height: TerentoWindowPresentation.minimumHeight
                )
            ))
            window.minSize = NSSize(
                width: min(minimumFrame.width, visibleFrame.width),
                height: min(minimumFrame.height, visibleFrame.height)
            )

            // Supersedes v2's reset and v3's height-only migration. Grow both
            // dimensions once, retaining larger restored frames and later
            // manual resizing. Reopening or changing pages never resizes.
            let migrationKey = "Terento.windowGeometry.catalog.v4"
            guard !UserDefaults.standard.bool(forKey: migrationKey) else { return }
            let currentContent = window.contentRect(forFrameRect: window.frame)
            let desiredContent = NSRect(origin: .zero, size: NSSize(
                width: max(currentContent.width, TerentoWindowPresentation.defaultWidth),
                height: max(currentContent.height, TerentoWindowPresentation.defaultHeight)
            ))
            let desiredFrame = window.frameRect(forContentRect: desiredContent)
            window.setFrame(TerentoWindowFrameLayout.fittedFrame(
                current: window.frame,
                desiredSize: desiredFrame.size,
                visibleFrame: visibleFrame
            ), display: true)
            UserDefaults.standard.set(true, forKey: migrationKey)
            UserDefaults.standard.set(true, forKey: "Terento.windowGeometry.v2")
            UserDefaults.standard.set(true, forKey: "Terento.windowGeometry.catalogHeight.v3")
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {}
}

/// Both utility windows open on the active display. Only a new opening is
/// centered: bringing an already visible window forward respects its position.
private struct TerentoSecondaryWindowPlacement: NSViewRepresentable {
    func makeNSView(context: Context) -> PlacementView { PlacementView() }
    func updateNSView(_ nsView: PlacementView, context: Context) {}

    final class PlacementView: NSView {
        private weak var observedWindow: NSWindow?
        private var needsPlacement = true

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            guard observedWindow !== window else { return }
            NotificationCenter.default.removeObserver(self)
            observedWindow = window
            needsPlacement = true
            guard let window else { return }
            NotificationCenter.default.addObserver(
                self, selector: #selector(windowBecameKey(_:)),
                name: NSWindow.didBecomeKeyNotification, object: window
            )
            NotificationCenter.default.addObserver(
                self, selector: #selector(windowWillClose(_:)),
                name: NSWindow.willCloseNotification, object: window
            )
            // Attachment can happen after SwiftUI has already made it key.
            if window.isKeyWindow { placeIfNeeded() }
        }

        @objc private func windowBecameKey(_ notification: Notification) {
            placeIfNeeded()
        }

        @objc private func windowWillClose(_ notification: Notification) {
            needsPlacement = true
        }

        private func placeIfNeeded() {
            guard needsPlacement, let window = observedWindow else { return }
            needsPlacement = false
            let sourceWindow = NSApp.orderedWindows.first {
                $0 !== window && $0.isVisible && $0.screen != nil
            }
            guard let screen = sourceWindow?.screen ?? window.screen ?? NSScreen.main else { return }
            window.setFrameOrigin(TerentoWindowFrameLayout.centeredOrigin(
                windowSize: window.frame.size,
                visibleFrame: screen.visibleFrame
            ))
        }

        deinit { NotificationCenter.default.removeObserver(self) }
    }
}
