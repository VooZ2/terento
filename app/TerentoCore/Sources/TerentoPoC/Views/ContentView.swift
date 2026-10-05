import SwiftUI

struct ContentView: View {
    @ObservedObject var deviceEngine: DeviceEngine
    @ObservedObject var mapEngine: MapEngine
    @ObservedObject var appUpdateController: AppUpdateController
    @ObservedObject var evidenceController: InstallationEvidenceController
    @ObservedObject var mapStatisticsController: MapStatisticsEventController
    /// Owned by the app so the main window shares one lifecycle model.
    @ObservedObject var lifecycleViewModel: MapLifecycleViewModel

    init(
        deviceEngine: DeviceEngine,
        mapEngine: MapEngine,
        lifecycleViewModel: MapLifecycleViewModel,
        appUpdateController: AppUpdateController,
        evidenceController: InstallationEvidenceController,
        mapStatisticsController: MapStatisticsEventController
    ) {
        self.deviceEngine = deviceEngine
        self.mapEngine = mapEngine
        self.lifecycleViewModel = lifecycleViewModel
        self.appUpdateController = appUpdateController
        self.evidenceController = evidenceController
        self.mapStatisticsController = mapStatisticsController
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
