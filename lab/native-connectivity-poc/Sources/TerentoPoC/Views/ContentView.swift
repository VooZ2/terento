import SwiftUI

struct ContentView: View {
    @ObservedObject var deviceEngine: DeviceEngine
    @ObservedObject var mapEngine: MapEngine
    @StateObject private var lifecycleViewModel: MapLifecycleViewModel

    init(deviceEngine: DeviceEngine, mapEngine: MapEngine) {
        self.deviceEngine = deviceEngine
        self.mapEngine = mapEngine
        _lifecycleViewModel = StateObject(
            wrappedValue: MapLifecycleViewModel(
                deviceEngine: deviceEngine,
                mapEngine: mapEngine
            )
        )
    }

    var body: some View {
        ConnectScreen(
            deviceEngine: deviceEngine,
            mapEngine: mapEngine,
            lifecycleViewModel: lifecycleViewModel
        )
    }
}
