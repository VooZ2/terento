import SwiftUI

struct ContentView: View {
    @ObservedObject var deviceEngine: DeviceEngine
    @ObservedObject var mapEngine: MapEngine
    @ObservedObject var appUpdateController: AppUpdateController
    @ObservedObject var evidenceController: InstallationEvidenceController
    @ObservedObject var mapStatisticsController: MapStatisticsEventController
    @StateObject private var lifecycleViewModel: MapLifecycleViewModel

    init(
        deviceEngine: DeviceEngine,
        mapEngine: MapEngine,
        appUpdateController: AppUpdateController,
        evidenceController: InstallationEvidenceController,
        mapStatisticsController: MapStatisticsEventController
    ) {
        self.deviceEngine = deviceEngine
        self.mapEngine = mapEngine
        self.appUpdateController = appUpdateController
        self.evidenceController = evidenceController
        self.mapStatisticsController = mapStatisticsController
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
            mapStatisticsController: mapStatisticsController,
            appUpdateController: appUpdateController
        )
    }
}
