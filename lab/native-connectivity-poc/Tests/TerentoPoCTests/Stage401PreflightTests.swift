import Foundation

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

@main
struct Stage401PreflightTests {
    static func main() {
        testRealFenixModelResolvesValidatedProfile()
        testMissingAmoledStringDoesNotBlockValidatedProfile()
        testPartialIdentityDoesNotClaimExactAsset()
        testUnknownDeviceStaysBlocked()
        testMapCapableBetaDeviceGetsLiveBoundProfile()
        testBetaProfileRequiresOneGarminRoot()
        testNonMapWatchCannotEnroll()
        testExistingExternalMapRequiresExplicitReplacement()
        testNewMapWithEnoughStorageIsReady()
        testUnknownInstallSizeIsBlocked()
        testInsufficientStorageIsBlocked()
        testAmbiguousExistingMapIsBlocked()
        testUnknownInstallTargetIsBlocked()
        testUpToDateMapIsStillAnExistingMapConflict()
        testPreflightIsTransportIndependentAndReadOnly()

        print("PASS: 15 Stage 4.0.1 preflight tests")
    }

    private static func testRealFenixModelResolvesValidatedProfile() {
        let identity = realIdentity()
        let profile = DeviceInstallProfileRegistry.local.profile(for: identity)

        expect(
            identity.canonicalModel == "fēnix 8"
                && profile?.targetDirectory == "/GARMIN"
                && profile?.supportsMapWrite == true,
            "real fenix 8 - 47mm identity resolves the validated /GARMIN profile"
        )
    }

    private static func testMissingAmoledStringDoesNotBlockValidatedProfile() {
        let identity = realIdentity()
        expect(
            identity.variant == "47mm"
                && DeviceInstallProfileRegistry.local.profile(for: identity) != nil,
            "missing AMOLED in the raw model string does not block profile matching"
        )
    }

    private static func testPartialIdentityDoesNotClaimExactAsset() {
        let asset = DeviceAssetRegistry.local.asset(for: realIdentity())
        expect(
            asset.scope == .modelSize && !asset.isExactMatch,
            "model-plus-size identity cannot claim an exact AMOLED asset"
        )
    }

    private static func testUnknownDeviceStaysBlocked() {
        let unknownIdentity = DeviceIdentity(
            manufacturer: "Garmin",
            model: "fenix 8 pro",
            family: "fēnix",
            variant: nil,
            usbVendorId: 0x091e,
            usbProductId: 0xffff,
            firmware: nil,
            storageCapacity: 0,
            freeSpace: 0
        )
        let result = makeEngine().evaluate(
            identity: unknownIdentity,
            selectedMap: makePackage(),
            comparison: makeComparison(status: .notInstalled),
            installedMaps: [],
            inspectedFiles: [],
            availableStorage: 15 * gigabyte,
            profile: DeviceInstallProfileRegistry.local.profile(for: unknownIdentity)
        )

        expect(
            DeviceInstallProfileRegistry.local.profile(for: unknownIdentity) == nil
                && result.status == .blockedUnsupportedDevice,
            "unknown PID/model does not inherit the validated install profile"
        )
    }

    private static func testMapCapableBetaDeviceGetsLiveBoundProfile() {
        let identity = betaIdentity(model: "fenix 8 - 51mm", family: "fēnix")
        let profile = DeviceInstallProfileRegistry.local.profile(
            for: identity,
            deviceFiles: [garminRoot(itemID: 10)]
        )

        expect(
            profile?.id == "garmin-map-capable-beta"
                && profile?.usbProductIds == [0x7777]
                && profile?.targetDirectory == "/GARMIN"
                && profile?.matches(identity) == true,
            "map-capable beta watch gets an exact live-bound /GARMIN profile"
        )
    }

    private static func testBetaProfileRequiresOneGarminRoot() {
        let identity = betaIdentity(model: "fenix 8 - 51mm", family: "fēnix")
        let missing = DeviceInstallProfileRegistry.local.profile(for: identity, deviceFiles: [])
        let duplicate = DeviceInstallProfileRegistry.local.profile(
            for: identity,
            deviceFiles: [garminRoot(itemID: 10), garminRoot(itemID: 11)]
        )

        expect(
            missing == nil && duplicate == nil,
            "beta enrollment fails closed unless exactly one root /GARMIN folder exists"
        )
    }

    private static func testNonMapWatchCannotEnroll() {
        let identity = betaIdentity(model: "Lily 2 Active", family: "Lily")
        let profile = DeviceInstallProfileRegistry.local.profile(
            for: identity,
            deviceFiles: [garminRoot(itemID: 10)]
        )

        expect(profile == nil, "known non-map Garmin watch cannot enter beta map installation")
    }

    private static func betaIdentity(model: String, family: String) -> DeviceIdentity {
        DeviceIdentity(
            manufacturer: "Garmin",
            model: model,
            family: family,
            variant: model.contains("51mm") ? "51mm" : nil,
            usbVendorId: 0x091e,
            usbProductId: 0x7777,
            firmware: "22.44",
            storageCapacity: 31 * gigabyte,
            freeSpace: 16 * gigabyte
        )
    }

    private static func garminRoot(itemID: UInt32) -> DeviceFile {
        DeviceFile(
            itemID: itemID,
            parentID: 0,
            storageID: 1,
            path: "/GARMIN",
            filename: "GARMIN",
            sizeBytes: 0,
            isFolder: true
        )
    }

    private static func testExistingExternalMapRequiresExplicitReplacement() {
        let package = makePackage()
        let installedMap = makeInstalledMap()
        let result = makeEngine().evaluate(
            identity: realIdentity(),
            selectedMap: package,
            comparison: makeComparison(installedMap: installedMap, status: .upToDate),
            installedMaps: [installedMap],
            inspectedFiles: [installedMap.sourceFile],
            availableStorage: 15 * gigabyte,
            profile: realProfile()
        )

        expect(
            result.status == .readyWithExistingMapConflict
                && result.ownership == .externalRecognized
                && result.replacementRequired
                && result.replacementConfirmationRequired
                && result.backupDecisionRequired
                && result.proposedFilename == "terento_freizeitkarte_ltu.img",
            "existing EXTERNAL_RECOGNIZED map requires explicit replacement and backup choice"
        )
    }

    private static func testNewMapWithEnoughStorageIsReady() {
        let result = makeEngine().evaluate(
            identity: realIdentity(),
            selectedMap: makePackage(),
            comparison: makeComparison(status: .notInstalled),
            installedMaps: [],
            inspectedFiles: [],
            availableStorage: 15 * gigabyte,
            profile: realProfile()
        )

        expect(
            result.status == .readyNewInstall
                && result.storagePlan?.isAllowed == true
                && !result.replacementConfirmationRequired,
            "new map with enough space returns READY_NEW_INSTALL"
        )
    }

    private static func testInsufficientStorageIsBlocked() {
        let result = makeEngine().evaluate(
            identity: realIdentity(),
            selectedMap: makePackage(),
            comparison: makeComparison(status: .notInstalled),
            installedMaps: [],
            inspectedFiles: [],
            availableStorage: makePackage().installSizeBytes!
                + StoragePlanner.defaultSafetyReserve - 1,
            profile: realProfile()
        )

        expect(
            result.status == .blockedInsufficientSpace
                && result.storagePlan?.isAllowed == false,
            "insufficient conservative storage is blocked"
        )
    }

    private static func testUnknownInstallSizeIsBlocked() {
        let result = makeEngine().evaluate(
            identity: realIdentity(),
            selectedMap: makePackage(includeInstallSize: false),
            comparison: makeComparison(status: .notInstalled),
            installedMaps: [],
            inspectedFiles: [],
            availableStorage: 15 * gigabyte,
            profile: realProfile()
        )

        expect(
            result.status == .blockedUnknownInstallSize,
            "missing final IMG size blocks preflight instead of using ZIP size"
        )
    }

    private static func testAmbiguousExistingMapIsBlocked() {
        let package = makePackage()
        let ambiguousMap = InstalledMap(
            name: "Unknown map",
            provider: nil,
            region: nil,
            family: nil,
            rawVersion: nil,
            version: nil,
            identifier: nil,
            productId: nil,
            familyId: nil,
            sizeBytes: 100,
            sourceFile: InstalledMapFile(
                path: "/GARMIN/terento_freizeitkarte_ltu.img",
                filename: "terento_freizeitkarte_ltu.img",
                sizeBytes: 100
            ),
            metadataStatus: .unknown,
            managementState: .unknown
        )
        let result = makeEngine().evaluate(
            identity: realIdentity(),
            selectedMap: package,
            comparison: makeComparison(installedMap: ambiguousMap, status: .unknown),
            installedMaps: [ambiguousMap],
            inspectedFiles: [ambiguousMap.sourceFile],
            availableStorage: 15 * gigabyte,
            profile: realProfile()
        )

        expect(
            result.status == .blockedAmbiguousMapIdentity,
            "ambiguous existing map identity blocks the preflight"
        )
    }

    private static func testUnknownInstallTargetIsBlocked() {
        let invalidTargetProfile = DeviceInstallProfile(
            id: "test-invalid-target",
            displayName: "Test invalid target",
            manufacturer: "Garmin",
            family: "fēnix",
            usbVendorId: 0x091e,
            usbProductIds: [0x51b8],
            modelAliases: ["fēnix 8"],
            targetDirectory: "",
            supportsMapWrite: true
        )
        let result = makeEngine().evaluate(
            identity: realIdentity(),
            selectedMap: makePackage(),
            comparison: makeComparison(status: .notInstalled),
            installedMaps: [],
            inspectedFiles: [],
            availableStorage: 15 * gigabyte,
            profile: invalidTargetProfile
        )

        expect(
            result.status == .blockedUnknownTarget,
            "profile without a safe target directory is blocked"
        )
    }

    private static func testUpToDateMapIsStillAnExistingMapConflict() {
        let installedMap = makeInstalledMap()
        let result = makeEngine().evaluate(
            identity: realIdentity(),
            selectedMap: makePackage(),
            comparison: makeComparison(installedMap: installedMap, status: .upToDate),
            installedMaps: [installedMap],
            inspectedFiles: [installedMap.sourceFile],
            availableStorage: 15 * gigabyte,
            profile: realProfile()
        )

        expect(
            result.comparisonStatus == .upToDate
                && result.status == .readyWithExistingMapConflict
                && result.status != .readyNewInstall,
            "UP_TO_DATE does not silently become a clean install"
        )
    }

    private static func testPreflightIsTransportIndependentAndReadOnly() {
        let result = makeEngine().evaluate(
            identity: realIdentity(),
            selectedMap: makePackage(),
            comparison: makeComparison(status: .notInstalled),
            installedMaps: [],
            inspectedFiles: [],
            availableStorage: 15 * gigabyte,
            profile: realProfile()
        )

        expect(
            result.status == .readyNewInstall,
            "preflight evaluates domain data without an MTP transport or write operation"
        )
    }

    private static func realIdentity() -> DeviceIdentity {
        GarminDeviceIdentityAdapter().makeIdentity(from: DeviceSnapshot(
            manufacturer: "Garmin",
            model: "fenix 8 - 47mm",
            deviceVersion: "2243",
            vendorID: 0x091e,
            productID: 0x51b8,
            storages: [StorageInfo(
                id: 1,
                description: "Garmin storage",
                volumeIdentifier: "GARMIN",
                maximumCapacity: 31 * gigabyte,
                freeSpace: 15 * gigabyte
            )]
        ))
    }

    private static func realProfile() -> DeviceInstallProfile? {
        DeviceInstallProfileRegistry.local.profile(for: realIdentity())
    }

    private static func makeEngine() -> InstallationPreflightEngine {
        InstallationPreflightEngine()
    }

    private static func makePackage(includeInstallSize: Bool = true) -> MapPackage {
        MapPackage(
            id: "freizeitkarte-ltu",
            providerId: "freizeitkarte",
            regionId: "LTU",
            name: "Lithuania",
            version: MapVersion(year: 2026, month: 5)!,
            sizeBytes: 344_000_000,
            sourceURL: nil,
            releaseDate: nil,
            identifier: nil,
            installSizeBytes: includeInstallSize ? 344_000_000 : nil
        )
    }

    private static func makeComparison(
        installedMap: InstalledMap? = nil,
        status: MapStatus
    ) -> MapComparison {
        MapComparison(
            providerName: "Freizeitkarte",
            regionName: "Lithuania",
            catalogMap: makePackage(),
            installedMap: installedMap,
            status: status
        )
    }

    private static func makeInstalledMap() -> InstalledMap {
        InstalledMap(
            name: "Freizeitkarte LTU",
            provider: "Freizeitkarte",
            region: "LTU",
            family: "Freizeitkarte_LTU+",
            rawVersion: "Release 26.05",
            version: MapVersion(year: 2026, month: 5),
            identifier: nil,
            productId: nil,
            familyId: nil,
            sizeBytes: 344_000_000,
            sourceFile: InstalledMapFile(
                path: "/GARMIN/freizeitkarte-lithuania.img",
                filename: "freizeitkarte-lithuania.img",
                sizeBytes: 344_000_000
            ),
            metadataStatus: .parsed,
            managementState: .detectedNotManaged
        )
    }

    private static let gigabyte: UInt64 = 1024 * 1024 * 1024

    private static func expect(_ condition: Bool, _ message: String) {
        guard condition else {
            fatalError("FAIL: \(message)")
        }

        print("PASS: \(message)")
    }
}
