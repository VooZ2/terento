import Foundation

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

struct SafeUpdateProgress: Equatable, Sendable {
    let state: SafeUpdateState
    let bytesCompleted: UInt64
    let totalBytes: UInt64
    let bytesPerSecond: Double

    var fractionCompleted: Double {
        guard totalBytes > 0 else { return 0 }
        return min(1, Double(bytesCompleted) / Double(totalBytes))
    }
}

enum SafeUpdateState: String, Equatable, Sendable {
    case idle
    case validating
    case revalidating
    case acquiring
    case backingUp
    case writing
    case verifying
    case committing
    case postVerifying
    case reconcilingManifest
    case completed
    case failed
}

private enum MapLifecyclePresentationTestError: Error {
    case failed(String)
}

private var passed = 0

private func require(_ condition: @autoclosure () -> Bool, _ message: String) throws {
    guard condition() else {
        throw MapLifecyclePresentationTestError.failed(message)
    }
    passed += 1
    print("PASS: \(message)")
}

private let installedVersion = MapVersion(year: 2026, month: 5)!
private let catalogVersion = MapVersion(year: 2026, month: 6)!

private func installedMap(
    itemID: UInt32? = 42,
    managementState: MapManagementState = .managedByTerento
) -> InstalledMap {
    InstalledMap(
        name: "Freizeitkarte LTU+",
        provider: "Freizeitkarte",
        region: "LTU",
        family: "Freizeitkarte",
        rawVersion: "Release 26.05",
        version: installedVersion,
        identifier: nil,
        productId: nil,
        familyId: nil,
        sizeBytes: 100,
        sourceFile: InstalledMapFile(
            path: "/GARMIN/terento_freizeitkarte_ltu.img",
            filename: "terento_freizeitkarte_ltu.img",
            sizeBytes: 100,
            itemID: itemID
        ),
        metadataStatus: .parsed,
        managementState: managementState
    )
}

private func lifecycleItem(
    installed: InstalledMap? = installedMap(),
    classification: MapLifecycleClassification = .terentoManaged
) -> MapLifecycleItem {
    MapLifecycleItem(
        id: "freizeitkarte-ltu",
        title: "Freizeitkarte Lithuania",
        provider: "Freizeitkarte",
        region: "LTU",
        version: installed?.version,
        rawVersion: installed?.rawVersion,
        sizeBytes: installed?.sizeBytes ?? 0,
        installedMaps: installed.map { [$0] } ?? [],
        classification: classification
    )
}

private func comparison(
    item: InstalledMap? = installedMap(),
    status: MapStatus = .updateAvailable
) -> MapComparison {
    MapComparison(
        providerName: "Freizeitkarte",
        regionName: "Lithuania",
        catalogMap: MapPackage(
            id: "freizeitkarte-ltu",
            providerId: "freizeitkarte",
            regionId: "LTU",
            name: "Lithuania",
            version: catalogVersion,
            sizeBytes: 100,
            sourceURL: nil,
            releaseDate: nil,
            identifier: nil
        ),
        installedMap: item,
        status: status
    )
}

private func identity() -> DeviceIdentity {
    DeviceIdentity(
        manufacturer: "Garmin",
        model: "fenix 8 - 47mm",
        family: "fēnix",
        variant: nil,
        usbVendorId: 0x091e,
        usbProductId: 0x51b8,
        firmware: "2244",
        storageCapacity: 31_000,
        freeSpace: 15_000
    )
}

private func context(
    item: MapLifecycleItem,
    comparison: MapComparison?,
    hash: String = String(repeating: "a", count: 64)
) -> MapLifecycleContext {
    MapLifecycleContext(
        item: item,
        comparison: comparison,
        selectedMap: comparison?.catalogMap,
        identity: identity(),
        availableStorage: 15_000,
        profile: DeviceInstallProfileRegistry.local.profile(for: identity()),
        deviceKey: "fenix-8-091e-51b8",
        expectedSHA256ByItemID: [42: hash]
    )
}

func runMapLifecyclePresentationTests() throws {
    let resolver = MapLifecyclePresentationResolver()
    let managed = lifecycleItem()
    let managedContext = context(item: managed, comparison: comparison())

    let update = resolver.resolve(
        item: managed,
        comparison: comparison(status: .updateAvailable),
        hasIntegrityRecord: true,
        hasValidatedUpdateProfile: true
    )
    try require(update.allows(.backup), "managed map allows backup")
    try require(update.allows(.remove), "managed map allows removal")
    try require(update.allows(.update), "older managed map allows update")
    try require(update.status == "Update available", "update status is user-facing")

    let upToDate = resolver.resolve(
        item: managed,
        comparison: comparison(status: .upToDate),
        hasIntegrityRecord: true,
        hasValidatedUpdateProfile: true
    )
    try require(upToDate.allows(.backup), "up-to-date map allows backup")
    try require(upToDate.allows(.remove), "up-to-date map allows removal")
    try require(!upToDate.allows(.update), "up-to-date map does not expose update")
    try require(upToDate.reason?.contains("explicit confirmation") == true, "up-to-date replacement remains explicit")

    let newer = resolver.resolve(
        item: managed,
        comparison: comparison(status: .newerInstalled),
        hasIntegrityRecord: true,
        hasValidatedUpdateProfile: true
    )
    try require(!newer.allows(.update), "newer installed map cannot be downgraded")
    try require(newer.status == "Newer version installed", "newer status is user-facing")

    let noProfile = resolver.resolve(
        item: managed,
        comparison: comparison(status: .updateAvailable),
        hasIntegrityRecord: true,
        hasValidatedUpdateProfile: false
    )
    try require(!noProfile.allows(.update), "unvalidated update profile blocks update")
    try require(noProfile.reason != nil, "blocked update provides a reason")

    let external = resolver.resolve(
        item: lifecycleItem(installed: installedMap(managementState: .detectedNotManaged), classification: .externalRecognized),
        comparison: comparison(item: installedMap(managementState: .detectedNotManaged)),
        hasIntegrityRecord: true,
        hasValidatedUpdateProfile: true
    )
    try require(external.actions.isEmpty, "external map exposes no lifecycle actions")
    try require(external.reason?.contains("left unchanged") == true, "external map explains read-only handling")

    let ambiguous = resolver.resolve(
        item: lifecycleItem(installed: installedMap(itemID: nil), classification: .ambiguous),
        comparison: nil,
        hasIntegrityRecord: false,
        hasValidatedUpdateProfile: true
    )
    try require(ambiguous.actions.isEmpty, "ambiguous map exposes no lifecycle actions")
    try require(ambiguous.status == "Identity unavailable", "ambiguous map has a safe status")

    let missingIntegrity = resolver.resolve(
        item: managed,
        comparison: comparison(),
        hasIntegrityRecord: false,
        hasValidatedUpdateProfile: true
    )
    try require(missingIntegrity.actions.isEmpty, "missing integrity record blocks actions")
    try require(missingIntegrity.status == "Needs verification", "missing integrity has a safe status")

    let notInstalled = resolver.resolve(
        item: lifecycleItem(installed: nil),
        comparison: comparison(item: nil, status: .notInstalled),
        hasIntegrityRecord: false,
        hasValidatedUpdateProfile: true
    )
    try require(notInstalled.actions.isEmpty, "not-installed map exposes no lifecycle actions")
    try require(notInstalled.status == "Not installed", "not-installed status is user-facing")

    try require(managedContext.hasIntegrityRecord, "complete manifest hash is recognized")
    try require(!context(item: managed, comparison: comparison(), hash: "bad").hasIntegrityRecord, "invalid manifest hash is rejected")

    try require(MapLifecycleOperationPhase.backingUp.userLabel == "Backing up", "backup phase has a product label")
    try require(MapLifecycleOperationPhase.removing.userLabel == "Removing", "remove phase has a product label")
    try require(MapLifecycleOperationPhase.updating.userLabel == "Updating", "update phase has a product label")
    try require(MapLifecycleOperationPhase.verifying.userLabel == "Verifying", "verify phase has a product label")
    try require(MapLifecycleOperationPhase.failed.userLabel == "Could not complete", "failure phase has a product label")

    let progress = SafeUpdateProgress(
        state: .backingUp,
        bytesCompleted: 50,
        totalBytes: 100,
        bytesPerSecond: 10
    )
    try require(progress.fractionCompleted == 0.5, "lifecycle progress reports a fraction")
    try require(MapLifecycleAction.allCases.count == 3, "only backup, remove, and update actions are exposed")
}

@main
private struct MapLifecyclePresentationTestRunner {
    static func main() {
        do {
            try runMapLifecyclePresentationTests()
            print("PASS: \(passed) Stage 5 UI lifecycle presentation tests")
        } catch {
            print("FAIL: \(error)")
            exit(1)
        }
    }
}
