import Foundation

extension Bundle { static var module: Bundle { .main } }

/// Scripted USB/MTP boundary. No device, network or file system is touched.
private final class ScriptedDetectionTransport: DeviceSnapshotReader, GarminUSBDeviceCounter,
    DevicePresenceReader, @unchecked Sendable {
    private let lock = NSLock()
    private var usbCount: Int
    private var snapshotResults: [Result<DeviceSnapshot, Error>]
    private var presenceError: Error?
    private(set) var snapshotCalls = 0

    init(usbCount: Int, snapshots: [Result<DeviceSnapshot, Error>] = []) {
        self.usbCount = usbCount
        self.snapshotResults = snapshots
    }

    func setUSBCount(_ count: Int) { lock.withLock { usbCount = count } }
    func setPresenceError(_ error: Error?) { lock.withLock { presenceError = error } }
    func enqueue(_ result: Result<DeviceSnapshot, Error>) { lock.withLock { snapshotResults.append(result) } }
    var calls: Int { lock.withLock { snapshotCalls } }

    func countGarminUSBDevices() throws -> Int { lock.withLock { usbCount } }

    func readSnapshot() throws -> DeviceSnapshot {
        let next: Result<DeviceSnapshot, Error> = lock.withLock {
            snapshotCalls += 1
            return snapshotResults.isEmpty ? .failure(MTPTransportError.readFailed("No MTP device connected"))
                : snapshotResults.removeFirst()
        }
        return try next.get()
    }

    func readPresence() throws -> DevicePresence {
        try lock.withLock {
            if let presenceError { throw presenceError }
            guard usbCount == 1 else {
                if usbCount == 0 { throw MTPTransportError.deviceAbsent }
                throw MTPTransportError.multipleGarminDevices
            }
            return DevicePresence(vendorID: 0x091e, productID: 0)
        }
    }
}

private func nativeSnapshotError(_ code: Int32, kind: InstallationFailureContext.ResultKind = .nativeError) -> Error {
    InstallationTransportError.contextual(failure: .operationFailed,
        message: "The device operation could not be completed.", createdItemID: nil,
        context: InstallationFailureContext(boundary: .initialSnapshot, classificationSource: .native,
            devicePresence: .unknown, operation: .snapshot, executionMode: .worker, resultKind: kind,
            nativeCodeNamespace: kind == .nativeError ? .terentoSnapshot : nil,
            nativeResultCode: kind == .nativeError ? code : nil))
}

private let watch = DeviceSnapshot(manufacturer: "Garmin", model: "fenix 8 - 47mm", deviceVersion: "fixture",
    vendorID: 0x091e, productID: 0x51b8,
    storages: [StorageInfo(id: 1, description: "Internal", volumeIdentifier: "", maximumCapacity: 32_000, freeSpace: 20_000)],
    serialNumber: "1234567890")

@MainActor
private func makeEngine(_ transport: ScriptedDetectionTransport, outcomes: OutcomeRecorder) -> DeviceEngine {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    let engine = DeviceEngine(transport: transport, operationGate: MTPOperationGate(),
        compatibilityStatusClient: CompatibilityStatusClient(
            cache: CompatibilityStatusCache(fileURL: root.appendingPathComponent("compatibility.json")),
            dataLoader: { _ in throw URLError(.notConnectedToInternet) }),
        installationAuthorizationClient: InstallationAuthorizationClient(dataLoader: { _ in
            throw URLError(.notConnectedToInternet)
        }))
    engine.connectOutcomeHandler = { outcomes.values.append($0) }
    return engine
}

@MainActor
private final class OutcomeRecorder {
    var values: [DeviceConnectOutcome] = []
}

@MainActor
private func waitUntil(_ seconds: Double, _ condition: () -> Bool) async -> Bool {
    let deadline = Date().addingTimeInterval(seconds)
    while Date() < deadline {
        if condition() { return true }
        try? await Task.sleep(for: .milliseconds(20))
    }
    return condition()
}

@main
struct DeviceDetectionEngineTests {
    static func check(_ condition: Bool, _ message: String) {
        guard condition else {
            print("FAIL: \(message)")
            exit(1)
        }
        print("PASS: \(message)")
    }

    @MainActor static func main() async {
        await testNoWatchStaysCalm()
        await testWatchAppearsLater()
        await testMultipleDevicesThenRecovery()
        await testNativeMultipleAndBusyClassification()
        await testStoppedRespondingThenReplug()
        await testUnexpectedDisconnectRestartsDiscovery()
        testClassifier()
        print("PASS: device detection engine")
    }

    @MainActor static func testNoWatchStaysCalm() async {
        let transport = ScriptedDetectionTransport(usbCount: 0)
        let outcomes = OutcomeRecorder()
        let engine = makeEngine(transport, outcomes: outcomes)
        engine.readDevice()
        try? await Task.sleep(for: .milliseconds(1_600))
        check(engine.state == .detecting && engine.detectionPhase == .waitingForWatch,
              "without a Garmin the engine stays in the calm waiting state")
        check(transport.calls == 0, "no libmtp snapshot is attempted without a Garmin on USB")
        check(engine.userErrorMessage == nil && outcomes.values.isEmpty, "waiting shows no error and reports nothing")
        engine.cancelReadDevice()
    }

    @MainActor static func testWatchAppearsLater() async {
        let transport = ScriptedDetectionTransport(usbCount: 0, snapshots: [.success(watch)])
        let outcomes = OutcomeRecorder()
        let engine = makeEngine(transport, outcomes: outcomes)
        engine.setPresenceMonitoringEnabled(false)
        engine.readDevice()
        try? await Task.sleep(for: .milliseconds(700))
        transport.setUSBCount(1)
        check(await waitUntil(4) { engine.hasConnectedDevice }, "plugging the watch in later connects without a click")
        check(outcomes.values == [.connected] && engine.lastConnectOutcome == .connected, "connected outcome is exposed once")
    }

    @MainActor static func testMultipleDevicesThenRecovery() async {
        let transport = ScriptedDetectionTransport(usbCount: 2, snapshots: [.success(watch)])
        let outcomes = OutcomeRecorder()
        let engine = makeEngine(transport, outcomes: outcomes)
        engine.setPresenceMonitoringEnabled(false)
        engine.readDevice()
        check(await waitUntil(2) { engine.detectionPhase == .needsAttention(.multipleDevices) },
              "two Garmins are shown immediately")
        check(transport.calls == 0 && engine.state == .detecting, "two Garmins do not open a native session")
        transport.setUSBCount(1)
        check(await waitUntil(5) { engine.hasConnectedDevice }, "unplugging the second Garmin continues automatically")
        check(outcomes.values == [.multipleDevices, .connected], "multiple devices then connected are reported")
    }

    @MainActor static func testNativeMultipleAndBusyClassification() async {
        let transport = ScriptedDetectionTransport(usbCount: 1, snapshots: [
            .failure(nativeSnapshotError(-5)), .failure(nativeSnapshotError(-5))
        ])
        let outcomes = OutcomeRecorder()
        let engine = makeEngine(transport, outcomes: outcomes)
        engine.setPresenceMonitoringEnabled(false)
        engine.readDevice()
        check(await waitUntil(6) { engine.detectionPhase == .needsAttention(.busy) },
              "repeated session-open failures are shown as busy while polling continues")
        check(engine.state == .detecting, "busy keeps detecting so quitting the other app reconnects")
        transport.enqueue(.success(watch))
        check(await waitUntil(6) { engine.hasConnectedDevice }, "a freed watch connects automatically")
        check(outcomes.values == [.busy, .connected], "busy then connected are reported")
    }

    @MainActor static func testStoppedRespondingThenReplug() async {
        let transport = ScriptedDetectionTransport(usbCount: 1, snapshots: [
            .failure(nativeSnapshotError(0, kind: .timeout))
        ])
        let outcomes = OutcomeRecorder()
        let engine = makeEngine(transport, outcomes: outcomes)
        engine.setPresenceMonitoringEnabled(false)
        engine.readDevice()
        check(await waitUntil(3) { engine.state == .failed }, "a bounded read deadline ends detection")
        check(engine.userErrorMessage == UserFacingErrorMessage.stoppedResponding,
              "a stalled watch shows the unplug-and-replug recovery message")
        check(outcomes.values == [.failed], "a stalled read reports failed")
        transport.enqueue(.success(watch))
        transport.setUSBCount(0)
        try? await Task.sleep(for: .milliseconds(1_300))
        transport.setUSBCount(1)
        check(await waitUntil(6) { engine.hasConnectedDevice }, "replugging after a failure restarts discovery automatically")
    }

    @MainActor static func testUnexpectedDisconnectRestartsDiscovery() async {
        let transport = ScriptedDetectionTransport(usbCount: 1, snapshots: [.success(watch)])
        let outcomes = OutcomeRecorder()
        let engine = makeEngine(transport, outcomes: outcomes)
        engine.readDevice()
        check(await waitUntil(3) { engine.hasConnectedDevice }, "fixture watch connects")
        transport.setUSBCount(0)
        check(await waitUntil(4) { engine.state == .detecting && engine.detectionPhase == .waitingForWatch },
              "an unexpected disconnect returns to calm discovery")
        check(engine.disconnectNotice != nil && outcomes.values == [.connected, .disconnected],
              "the waiting screen explains the disconnect and the outcome is reported")
        transport.enqueue(.success(watch))
        transport.setUSBCount(2)
        check(await waitUntil(4) { engine.detectionPhase == .needsAttention(.multipleDevices) },
              "a second Garmin is shown as its own issue, not a disconnect")
        transport.setUSBCount(1)
        check(await waitUntil(5) { engine.hasConnectedDevice }, "the remaining watch reconnects automatically")
        engine.setPresenceMonitoringEnabled(false)
    }

    static func testClassifier() {
        check(DeviceDetectionErrorClassifier.classify(nativeSnapshotError(-2)) == .notYetEnumerated, "native -2 is not yet enumerated")
        check(DeviceDetectionErrorClassifier.classify(nativeSnapshotError(-3)) == .notYetEnumerated, "native -3 is not yet enumerated")
        check(DeviceDetectionErrorClassifier.classify(nativeSnapshotError(-4)) == .multipleDevices, "native -4 is multiple devices")
        check(DeviceDetectionErrorClassifier.classify(nativeSnapshotError(-5)) == .busy, "native -5 is busy")
        check(DeviceDetectionErrorClassifier.classify(nativeSnapshotError(-10)) == .transient, "storage read failure is transient")
        check(DeviceDetectionErrorClassifier.classify(nativeSnapshotError(0, kind: .timeout)) == .stoppedResponding, "worker deadline is stopped responding")
        check(DeviceDetectionErrorClassifier.classify(MTPTransportError.multipleGarminDevices) == .multipleDevices, "presence multiple-device error")
        check(DeviceDetectionErrorClassifier.classify(MTPTransportError.readFailed("More than one Garmin MTP device detected")) == .multipleDevices, "in-process multiple-device text")
        check(DeviceDetectionErrorClassifier.classify(MTPTransportError.readFailed("No Garmin MTP device detected")) == .notYetEnumerated, "in-process absent text")
    }
}
