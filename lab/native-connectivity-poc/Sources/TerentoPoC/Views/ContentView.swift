import SwiftUI

struct ContentView: View {
    @ObservedObject var deviceEngine: DeviceEngine
    @ObservedObject var mapEngine: MapEngine
    @ObservedObject var appUpdateController: AppUpdateController
    @StateObject private var lifecycleViewModel: MapLifecycleViewModel
    @StateObject private var evidenceController = InstallationEvidenceController()

    init(
        deviceEngine: DeviceEngine,
        mapEngine: MapEngine,
        appUpdateController: AppUpdateController
    ) {
        self.deviceEngine = deviceEngine
        self.mapEngine = mapEngine
        self.appUpdateController = appUpdateController
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
            lifecycleViewModel: lifecycleViewModel,
            evidenceController: evidenceController,
            appUpdateController: appUpdateController
        )
    }
}
