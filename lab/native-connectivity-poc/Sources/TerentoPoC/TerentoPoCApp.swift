import AppKit
import SwiftUI

@main
struct TerentoPoCApp: App {
    @StateObject private var deviceEngine = DeviceEngine()
    @StateObject private var mapEngine = MapEngine()
    @StateObject private var appUpdateController = AppUpdateController()
    @Environment(\.openWindow) private var openWindow

    var body: some Scene {
        WindowGroup("Terento") {
            ContentView(
                deviceEngine: deviceEngine,
                mapEngine: mapEngine,
                appUpdateController: appUpdateController
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
                Divider()
                Button("About Terento") {
                    openWindow(id: "about")
                }
            }
        }
        Window("About Terento", id: "about") {
            AboutTerentoView(appUpdateController: appUpdateController)
        }
        .defaultSize(width: 360, height: 330)
        .windowResizability(.contentSize)
        .windowStyle(.titleBar)
    }

    private func openExternalURL(_ url: URL) {
        NSWorkspace.shared.open(url)
    }
}

/// SwiftUI's defaultSize is only consulted when macOS has no restored frame.
/// A one-time geometry migration clears the oversized frame left by the
/// earlier prototype while preserving later user resizing and navigation.
private struct TerentoWindowConfigurator: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.async {
            guard let window = view.window else { return }

            window.minSize = NSSize(
                width: TerentoWindowPresentation.minimumWidth,
                height: TerentoWindowPresentation.minimumHeight
            )

            let migrationKey = "Terento.windowGeometry.v2"
            guard !UserDefaults.standard.bool(forKey: migrationKey) else {
                return
            }

            window.setContentSize(
                NSSize(
                    width: TerentoWindowPresentation.defaultWidth,
                    height: TerentoWindowPresentation.defaultHeight
                )
            )
            window.center()
            UserDefaults.standard.set(true, forKey: migrationKey)
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {}
}
