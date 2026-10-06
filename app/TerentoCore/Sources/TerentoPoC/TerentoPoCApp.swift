import AppKit
import Combine
import SwiftUI

@main
struct TerentoEntryPoint {
    static func main() {
        if MTPFinishingWorker.runIfRequested() { return }
        Task.detached(priority: .utility) {
            MapAcquisitionWorkspace.scavengeStale()
            MapAcquisitionWorkspace.scavengeStaleTemporaryDownloads()
        }
        TerentoPoCApp.main()
    }
}

struct TerentoPoCApp: App {
    @NSApplicationDelegateAdaptor(TerentoAppDelegate.self) private var appDelegate
    @StateObject private var deviceEngine: DeviceEngine
    @StateObject private var mapEngine: MapEngine
    @StateObject private var lifecycleViewModel: MapLifecycleViewModel
    @StateObject private var appUpdateController = AppUpdateController()
    @StateObject private var evidenceController: InstallationEvidenceController
    @StateObject private var mapStatisticsController: MapStatisticsEventController
    @Environment(\.openWindow) private var openWindow

    @State private var funnelObserver: AppFunnelStateObserver?
    private let funnel: AppFunnelTelemetryController

    init() {
        let statistics = MapStatisticsEventController()
        let evidence = InstallationEvidenceController()
        // The funnel shares the device-compatibility reporting preference.
        let evidenceStore = evidence.store
        let funnel = AppFunnelTelemetryController(sharingEnabled: {
            evidenceStore.consent()?.choice != .declined
        })
        evidence.onSharingDeclined = { [weak funnel] in funnel?.sharingDeclined() }
        self.funnel = funnel
        let device = DeviceEngine()
        let maps = MapEngine(statisticsController: statistics, evidenceController: evidence, funnel: funnel)
        // One lifecycle model for the app: reopening the main window must not
        // create a second model while an operation is running.
        let lifecycle = MapLifecycleViewModel(deviceEngine: device, mapEngine: maps)
        _evidenceController = StateObject(wrappedValue: evidence)
        _mapStatisticsController = StateObject(wrappedValue: statistics)
        _deviceEngine = StateObject(wrappedValue: device)
        _mapEngine = StateObject(wrappedValue: maps)
        _lifecycleViewModel = StateObject(wrappedValue: lifecycle)
        DeviceOperationActivityMonitor.shared.observe(mapEngine: maps, lifecycle: lifecycle)
    }

    var body: some Scene {
        // A single main window: File > New Window would otherwise create a
        // second view hierarchy with its own selection and plan state.
        Window("Terento", id: "main") {
            ContentView(
                deviceEngine: deviceEngine,
                mapEngine: mapEngine,
                lifecycleViewModel: lifecycleViewModel,
                appUpdateController: appUpdateController,
                evidenceController: evidenceController,
                mapStatisticsController: mapStatisticsController
            )
            .background(TerentoWindowConfigurator())
            .task {
                appUpdateController.startAutomaticCheck()
                if funnelObserver == nil {
                    funnelObserver = AppFunnelStateObserver(funnel: funnel,
                        deviceEngine: deviceEngine, mapEngine: mapEngine)
                }
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
                Button("Troubleshooting") {
                    openExternalURL(TerentoAppLinks.troubleshootingGuide)
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
                deviceEngine: deviceEngine,
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

/// Keeps the Mac awake while maps are downloaded, prepared, written, verified,
/// updated or removed, and tells the app delegate when a device write is
/// active. It observes the engines; it never starts or stops device work.
@MainActor
final class DeviceOperationActivityMonitor {
    static let shared = DeviceOperationActivityMonitor()

    private var cancellables: Set<AnyCancellable> = []
    private var activity: NSObjectProtocol?
    private weak var mapEngine: MapEngine?
    private weak var lifecycle: MapLifecycleViewModel?
    private(set) var isDeviceWriteActive = false

    func observe(mapEngine: MapEngine, lifecycle: MapLifecycleViewModel) {
        self.mapEngine = mapEngine
        self.lifecycle = lifecycle
        cancellables.removeAll()
        // objectWillChange fires before the new value is stored; evaluate on
        // the next main-loop turn.
        mapEngine.objectWillChange
            .merge(with: lifecycle.objectWillChange)
            .receive(on: RunLoop.main)
            .sink { [weak self] _ in self?.refresh() }
            .store(in: &cancellables)
        refresh()
    }

    func applicationWillTerminate() {
        mapEngine?.purgeRetainedArtifacts()
        if let activity {
            ProcessInfo.processInfo.endActivity(activity)
            self.activity = nil
        }
    }

    private func refresh() {
        guard let mapEngine, let lifecycle else { return }
        let lifecyclePhases = lifecycle.operations.values.map(\.phase)
        isDeviceWriteActive = DeviceOperationActivityPolicy.writesToDevice(
            mapInstallActive: mapEngine.state == .installing,
            lifecyclePhases: lifecyclePhases
        )
        let keepAwake = DeviceOperationActivityPolicy.keepsMacAwake(
            installationPhase: mapEngine.installationPhase,
            mapPreparationActive: mapEngine.state == .acquiringArtifact
                || mapEngine.state == .preparingInstallation
                || mapEngine.state == .installing,
            lifecyclePhases: lifecyclePhases
        )
        if keepAwake, activity == nil {
            activity = ProcessInfo.processInfo.beginActivity(
                options: [.userInitiated, .idleSystemSleepDisabled],
                reason: "Terento is transferring maps with a connected Garmin watch."
            )
        } else if !keepAwake, let activity {
            ProcessInfo.processInfo.endActivity(activity)
            self.activity = nil
        }
    }
}

final class TerentoAppDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        let writeActive = MainActor.assumeIsolated { DeviceOperationActivityMonitor.shared.isDeviceWriteActive }
        guard writeActive else { return .terminateNow }
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = "Terento is still working on your watch"
        alert.informativeText = "Quitting now can leave an incomplete map on your watch. Wait until Terento finishes, then quit."
        alert.addButton(withTitle: "Keep Terento open")
        alert.addButton(withTitle: "Quit anyway")
        return alert.runModal() == .alertFirstButtonReturn ? .terminateCancel : .terminateNow
    }

    func applicationWillTerminate(_ notification: Notification) {
        MainActor.assumeIsolated { DeviceOperationActivityMonitor.shared.applicationWillTerminate() }
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
