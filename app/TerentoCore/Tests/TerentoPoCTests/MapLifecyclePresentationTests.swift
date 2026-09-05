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
        name: "Freizeitkarte DEU+",
        provider: "Freizeitkarte",
        region: "DEU",
        family: "Freizeitkarte",
        rawVersion: "Release 26.05",
        version: installedVersion,
        identifier: nil,
        productId: nil,
        familyId: nil,
        sizeBytes: 100,
        sourceFile: InstalledMapFile(
            path: "/GARMIN/terento_freizeitkarte_deu.img",
            filename: "terento_freizeitkarte_deu.img",
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
        id: "freizeitkarte-deu",
        title: "Freizeitkarte Germany",
        provider: "Freizeitkarte",
        region: "DEU",
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
        regionName: "Germany",
        catalogMap: MapPackage(
            id: "freizeitkarte-deu",
            providerId: "freizeitkarte",
            regionId: "DEU",
            name: "Germany",
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
    try require(
        managed.manageMetadataLabel.contains("2026-05")
            && !managed.manageMetadataLabel.contains("Freizeitkarte")
            && !managed.manageMetadataLabel.contains("Installed"),
        "managed row uses release and size without repeating provider or installed state"
    )
    try require(
        ManageMapRowActionPresentation.actions(for: update) == [.update, .backup, .remove],
        "three valid actions use one ordered action group"
    )
    try require(
        ManageMapRowActionPresentation.primaryActions(for: update) == [.update, .remove]
            && ManageMapRowActionPresentation.advancedActions(for: update) == [.backup],
        "backup moves to advanced actions while update and remove stay visible"
    )

    let withheldUpdate = resolver.resolve(
        item: managed,
        comparison: comparison(status: .updateAvailable),
        hasIntegrityRecord: true,
        hasValidatedUpdateProfile: true,
        acquisitionAvailability: .withheldRussia
    )
    try require(withheldUpdate.allows(.backup), "withheld managed map retains safe backup")
    try require(withheldUpdate.allows(.remove), "withheld managed map retains safe removal")
    try require(!withheldUpdate.allows(.update), "withheld managed map does not expose update")
    try require(
        withheldUpdate.status == "Updates are not offered for this map"
            && comparison(status: .updateAvailable).status == .updateAvailable,
        "withheld update presentation preserves factual UPDATE_AVAILABLE state"
    )
    let withheldWithoutProfile = resolver.resolve(
        item: managed,
        comparison: comparison(status: .updateAvailable),
        hasIntegrityRecord: true,
        hasValidatedUpdateProfile: false,
        acquisitionAvailability: .withheldCrimea
    )
    try require(
        withheldWithoutProfile.status == "Updates are not offered for this map"
            && withheldWithoutProfile.actions == [.backup, .remove],
        "withheld update policy remains neutral without a validated update profile"
    )

    let transferable = resolver.resolve(
        item: managed,
        comparison: comparison(status: .upToDate),
        hasIntegrityRecord: true,
        hasValidatedUpdateProfile: true,
        hasStableWatchIdentity: true
    )
    try require(
        ManageMapRowActionPresentation.actions(for: transferable)
            == [.backup, .transferOwnership, .remove],
        "managed map can export a private ownership file for another Mac"
    )
    try require(
        ManageMapRowActionPresentation.primaryActions(for: transferable) == [.remove]
            && ManageMapRowActionPresentation.advancedActions(for: transferable)
                == [.backup, .transferOwnership],
        "backup and ownership export are grouped under advanced actions"
    )
    try require(
        ManageMapRowActionPresentation.productionActions(for: transferable) == [.remove]
            && ManageMapRowActionPresentation.productionMenuActions(for: transferable).isEmpty,
        "production rows hide backup and ownership tools while retaining removal"
    )

    try require(
        ManageMapRowActionPresentation.productionActions(for: update) == [.update, .remove]
            && ManageMapRowActionPresentation.productionPrimaryActions(for: update) == [.update, .remove],
        "production update row exposes only Update and Remove"
    )

    let recoveryRecord = TerentoFailedInstallRecoveryRecord(
        deviceKey: "fenix-8-091e-51b8",
        packageID: "freizeitkarte-deu",
        providerId: "freizeitkarte",
        regionId: "DEU",
        version: installedVersion,
        devicePath: "/GARMIN/terento_freizeitkarte_deu.img",
        filename: "terento_freizeitkarte_deu.img",
        sizeBytes: 100,
        sha256: String(repeating: "a", count: 64),
        createdAt: Date(timeIntervalSince1970: 0)
    )
    let recoveryItem = MapLifecycleItem(
        id: managed.id,
        title: managed.title,
        provider: managed.provider,
        region: managed.region,
        version: managed.version,
        rawVersion: managed.rawVersion,
        sizeBytes: managed.sizeBytes,
        installedMaps: managed.installedMaps,
        classification: .externalRecognized,
        failedInstallRecovery: recoveryRecord
    )
    let recovery = resolver.resolve(
        item: recoveryItem,
        comparison: comparison(status: .upToDate),
        hasIntegrityRecord: true,
        hasValidatedUpdateProfile: true,
        failedInstallRecovery: true
    )
    try require(recovery.actions == [.remove], "failed install recovery exposes only removal")
    try require(!recovery.allows(.backup), "failed install recovery does not expose backup as a separate action")
    try require(recovery.status == "Failed install recovery", "failed install recovery has a distinct status")
    try require(
        recoveryItem.manageMetadataLabel.contains("2026-05")
            && recoveryItem.manageMetadataLabel.contains("Incomplete installation")
            && !recoveryItem.manageMetadataLabel.contains("Freizeitkarte"),
        "recovery row uses explicit incomplete-installation metadata"
    )

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
    try require(
        ManageMapRowActionPresentation.actions(for: upToDate) == [.backup, .remove],
        "two valid actions use the same ordered action group"
    )
    try require(
        ManageMapRowActionPresentation.productionActions(for: upToDate) == [.remove]
            && ManageMapRowActionPresentation.productionMenuActions(for: upToDate).isEmpty,
        "production up-to-date row exposes only Remove and no overflow"
    )

    let backupOnly = MapLifecycleActionAvailability(
        actions: [.backup],
        status: "Installed",
        reason: nil
    )
    try require(
        ManageMapRowActionPresentation.actions(for: backupOnly) == [.backup],
        "one valid action keeps the same action control style"
    )
    try require(
        ManageMapRowActionPresentation.primaryActions(for: backupOnly).isEmpty
            && ManageMapRowActionPresentation.advancedActions(for: backupOnly) == [.backup],
        "backup-only rows expose the advanced menu without a primary button"
    )
    try require(
        ManageMapRowActionPresentation.productionActions(for: backupOnly).isEmpty
            && ManageMapRowActionPresentation.productionMenuActions(for: backupOnly).isEmpty,
        "internal backup-only state has no production action surface"
    )

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
    try require(
        lifecycleItem(
            installed: installedMap(managementState: .detectedNotManaged),
            classification: .externalRecognized
        ).manageMetadataLabel.contains("2026-05"),
        "external row keeps concise release and size metadata"
    )
    try require(
        ManageMapRowActionPresentation.actions(for: external) == [],
        "no valid actions leaves the row action area empty"
    )


    let recoverable = resolver.resolve(
        item: lifecycleItem(
            installed: installedMap(managementState: .detectedNotManaged),
            classification: .externalRecognized
        ),
        comparison: comparison(item: installedMap(managementState: .detectedNotManaged)),
        hasIntegrityRecord: false,
        hasValidatedUpdateProfile: true,
        hasStableWatchIdentity: true
    )
    try require(
        recoverable.actions == [.recoverOwnership],
        "read-only Terento filename exposes only explicit ownership recovery"
    )
    try require(
        ManageMapRowActionPresentation.primaryActions(for: recoverable).isEmpty
            && ManageMapRowActionPresentation.advancedActions(for: recoverable)
                == [.recoverOwnership],
        "ownership recovery is presented only in the advanced menu"
    )
    try require(
        ManageMapRowActionPresentation.productionActions(for: recoverable).isEmpty,
        "internal ownership recovery does not leak into production Manage Maps"
    )

    let rawExternalMap = InstalledMap(
        name: "OpenTopoMap Lithuani",
        provider: nil,
        region: nil,
        family: "OpenTopoMap Lithuani",
        rawVersion: nil,
        version: nil,
        identifier: nil,
        productId: nil,
        familyId: nil,
        sizeBytes: 100,
        sourceFile: InstalledMapFile(
            path: "/GARMIN/otm-lithuania-contours.img",
            filename: "otm-lithuania-contours.img",
            sizeBytes: 100,
            itemID: 43
        ),
        metadataStatus: .parsed,
        managementState: .detectedNotManaged
    )
    let removableExternal = MapLifecycleItem(
        id: rawExternalMap.sourceFile.path,
        title: rawExternalMap.name,
        sourceKind: .provider,
        provider: nil,
        region: nil,
        version: nil,
        rawVersion: nil,
        sizeBytes: rawExternalMap.sizeBytes,
        installedMaps: [rawExternalMap],
        classification: .externalRecognized
    )
    let externalRemoval = resolver.resolve(
        item: removableExternal,
        comparison: nil,
        hasIntegrityRecord: false,
        hasValidatedUpdateProfile: true,
        hasStableWatchIdentity: true
    )
    try require(
        externalRemoval.actions == [.remove]
            && externalRemoval.status == "External map",
        "a parsed third-party map exposes one-by-one removal"
    )

    let ambiguous = resolver.resolve(
        item: lifecycleItem(installed: installedMap(itemID: nil), classification: .ambiguous),
        comparison: nil,
        hasIntegrityRecord: false,
        hasValidatedUpdateProfile: true
    )
    try require(ambiguous.actions.isEmpty, "ambiguous map exposes no lifecycle actions")
    try require(ambiguous.status == "Read-only", "ambiguous map has a safe status")

    let missingIntegrity = resolver.resolve(
        item: managed,
        comparison: comparison(),
        hasIntegrityRecord: false,
        hasValidatedUpdateProfile: true
    )
    try require(missingIntegrity.actions.isEmpty, "missing integrity record blocks actions")
    try require(missingIntegrity.status == "Read-only", "missing integrity has a safe status")

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
    try require(
        MapLifecycleAction.allCases.count == 5,
        "only backup, transfer, recover, remove, and unchanged update actions are exposed"
    )
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
