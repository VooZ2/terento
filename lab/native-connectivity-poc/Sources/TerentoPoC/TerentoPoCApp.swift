import SwiftUI

@main
struct TerentoPoCApp: App {
    @StateObject private var deviceEngine = DeviceEngine()
    @StateObject private var mapEngine = MapEngine()

    var body: some Scene {
        WindowGroup("Terento") {
            ContentView(
                deviceEngine: deviceEngine,
                mapEngine: mapEngine
            )
        }
        .defaultSize(width: 1160, height: 800)
        .windowResizability(.automatic)
        .windowStyle(.titleBar)
    }
}
