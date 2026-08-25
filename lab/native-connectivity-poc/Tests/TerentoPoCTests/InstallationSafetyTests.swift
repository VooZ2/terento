import Foundation

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

@main
struct InstallationSafetyTests {
    static func main() async throws {
        var passed = 0

        passed += expect(
            TransferRateCalculator.sample(
                deltaBytes: 850_000,
                elapsedSeconds: 1
            ) == 850_000,
            "transfer rate uses cumulative byte delta over elapsed time"
        )
        passed += expect(
            TransferRateCalculator.sample(
                deltaBytes: 8_600_000,
                elapsedSeconds: 1
            )?.isFinite == true
                && TransferRateCalculator.sample(
                    deltaBytes: 1_200_000_000,
                    elapsedSeconds: 1
                )?.isFinite == true,
            "KB, MB, and GB-sized transfer rates remain finite"
        )
        passed += expect(
            TransferRateCalculator.sample(deltaBytes: 1_000, elapsedSeconds: 0.01) == nil
                && TransferRateCalculator.sample(deltaBytes: 0, elapsedSeconds: 1) == nil
                && TransferRateCalculator.sample(deltaBytes: 1_000, elapsedSeconds: .infinity) == nil
                && TransferRateCalculator.sample(deltaBytes: 1_000, elapsedSeconds: .nan) == nil,
            "near-zero, zero-byte, infinite, and NaN samples are ignored"
        )
        let clock = ContinuousClock()
        let firstSample = clock.now
        var estimator = TransferSpeedEstimator()
        _ = estimator.update(bytes: 1_150_000, now: firstSample)
        let earlyRate = estimator.update(
            bytes: 2_000_000,
            now: firstSample.advanced(by: .milliseconds(100))
        )
        let measuredRate = estimator.update(
            bytes: 2_850_000,
            now: firstSample.advanced(by: .seconds(1))
        )
        passed += expect(
            earlyRate == 0 && measuredRate.isFinite && measuredRate > 0,
            "cumulative callbacks wait for a meaningful interval before reporting speed"
        )

        passed += expect(
            StoragePlanner().plan(
                currentFreeSpace: 3 * gigabyte,
                selectedMapSizes: [1 * gigabyte]
            ).isAllowed,
            "storage allows installation with more than 1 GB reserve"
        )
        passed += expect(
            StoragePlanner().plan(
                currentFreeSpace: 2 * gigabyte,
                selectedMapSizes: [1 * gigabyte]
            ).isAllowed,
            "storage allows installation at exactly 1 GB reserve"
        )
        passed += expect(
            !StoragePlanner().plan(
                currentFreeSpace: 1 * gigabyte,
                selectedMapSizes: [1]
            ).isAllowed,
            "storage blocks below the 1 GB reserve"
        )

        let multipleMapPlan = StoragePlanner().plan(
            currentFreeSpace: 5 * gigabyte,
            selectedMapSizes: [1 * gigabyte, 2 * gigabyte]
        )
        passed += expect(
            multipleMapPlan.selectedMapBytes == 3 * gigabyte
                && multipleMapPlan.requiredTemporarySpace == 3 * gigabyte
                && multipleMapPlan.projectedFreeSpace == 2 * gigabyte,
            "storage sums selected maps and uses conservative temporary space"
        )

        let filenameGenerator = TerentoManagedFilenameGenerator()
        passed += expect(
            try filenameGenerator.filename(
                providerId: "Freizeitkarte",
                regionId: "LTU+"
            ) == "terento_freizeitkarte_ltu.img",
            "managed filename is deterministic and safe"
        )
        passed += expect(
            filenameGenerator.isValid("terento_freizeitkarte_ltu.img"),
            "managed filename passes policy"
        )
        passed += expect(
            try filenameGenerator.filename(
                providerId: "Freezeit Karte",
                regionId: "LTU+"
            ) == "terento_freezeit_karte_ltu.img"
                && filenameGenerator.isValid("terento_freezeit_karte_ltu.img"),
            "normalized internal separators remain valid in managed filenames"
        )
        passed += expect(
            !filenameGenerator.isValid("terento_freizeitkarte_ltu/evil.img")
                && !filenameGenerator.isValid("../terento_freizeitkarte_ltu.img")
                && !filenameGenerator.isValid("terento_freizeitkarte_ltu\\evil.img")
                && !filenameGenerator.isValid("terento_freizeitkarte_ltu.img\0"),
            "managed filename policy rejects traversal, separators, and NUL"
        )
        passed += expectThrows(
            { try filenameGenerator.filename(providerId: "///", regionId: "LTU") },
            "empty normalized provider is rejected"
        )

        let knownIdentity = DeviceIdentity(
            manufacturer: "Garmin",
            model: "fenix 8 - 47mm",
            family: "fēnix",
            variant: "47mm",
            usbVendorId: 0x091e,
            usbProductId: 0x51b8,
            firmware: "2243",
            storageCapacity: 31 * gigabyte,
            freeSpace: 15 * gigabyte
        )
        passed += expect(
            DeviceInstallProfileRegistry.local.profile(for: knownIdentity)?.targetDirectory == "/GARMIN",
            "known fēnix 8 profile resolves /GARMIN"
        )

        let unknownIdentity = DeviceIdentity(
            manufacturer: "Garmin",
            model: "unknown watch",
            family: "unknown",
            variant: nil,
            usbVendorId: 0x091e,
            usbProductId: 0xffff,
            firmware: nil,
            storageCapacity: 0,
            freeSpace: 0
        )
        passed += expect(
            DeviceInstallProfileRegistry.local.profile(for: unknownIdentity) == nil,
            "unknown device has no install target"
        )

        let package = makePackage()
        let existingMap = makeInstalledMap()
        let conflictResolver = MapConflictResolver()
        let targetPath = try conflictResolver.targetPath(
            profile: DeviceInstallProfileRegistry.local.profiles[0],
            selectedPackage: package
        )
        passed += expect(
            conflictResolver.resolve(
                selectedPackage: package,
                targetPath: targetPath,
                installedMaps: [],
                inspectedFiles: []
            ) == .noConflict,
            "no existing map allows a new install plan"
        )
        passed += expect(
            isReplacement(
                conflictResolver.resolve(
                    selectedPackage: package,
                    targetPath: targetPath,
                    installedMaps: [existingMap],
                    inspectedFiles: [existingMap.sourceFile]
                )
            ),
            "recognized existing map requires explicit replacement"
        )

        let unknownTargetFile = InstalledMapFile(
            path: targetPath,
            filename: "terento_freizeitkarte_ltu.img",
            sizeBytes: 100
        )
        passed += expect(
            conflictResolver.resolve(
                selectedPackage: package,
                targetPath: targetPath,
                installedMaps: [],
                inspectedFiles: [unknownTargetFile]
            ) == .blockedAmbiguous,
            "unknown object at target path blocks installation"
        )

        let ownershipVerifier = OwnershipVerifier()
        passed += expect(
            ownershipVerifier.classify(
                map: existingMap,
                deviceKey: "fenix8-local",
                actualSHA256: nil,
                manifest: TerentoManifest(entries: [])
            ) == .externalRecognized,
            "parsed manual map remains externally recognized without manifest proof"
        )

        let managedMap = makeInstalledMap(
            path: "/GARMIN/terento_freizeitkarte_ltu.img",
            filename: "terento_freizeitkarte_ltu.img"
        )
        let manifest = TerentoManifest(entries: [
            TerentoManifestEntry(
                deviceKey: "fenix8-local",
                devicePath: managedMap.sourceFile.path,
                filename: managedMap.sourceFile.filename,
                providerId: "freizeitkarte",
                regionId: "LTU",
                version: package.version,
                sizeBytes: managedMap.sizeBytes,
                sha256: "abc123",
                installedAt: Date(timeIntervalSince1970: 0)
            )
        ])
        passed += expect(
            ownershipVerifier.classify(
                map: managedMap,
                deviceKey: "fenix8-local",
                actualSHA256: "ABC123",
                manifest: manifest
            ) == .terentoManaged,
            "manifest path, identity, size and hash prove Terento ownership"
        )

        let sourceURL = try makeValidIMGFile()
        defer { try? FileManager.default.removeItem(at: sourceURL) }
        let validator = MapSourceValidator()
        let validatedSource = try validator.validate(
            fileURL: sourceURL,
            expectedPackage: package
        )
        passed += expect(
            validatedSource.metadata.version == package.version
                && validatedSource.sizeBytes > 0
                && validatedSource.sha256.count == 64,
            "valid IMG source is fully read, parsed and hashed"
        )

        passed += expectThrows(
            {
                try validator.validate(
                    fileURL: sourceURL,
                    expectedPackage: makePackage(region: "LVA")
                )
            },
            "source region mismatch is blocked"
        )
        passed += expectThrows(
            {
                try validator.validate(
                    fileURL: sourceURL,
                    expectedPackage: makePackage(version: MapVersion(year: 2026, month: 6)!)
                )
            },
            "source version mismatch is blocked"
        )

        let invalidURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-stage3-invalid-\(UUID().uuidString).img")
        try Data([0, 1, 2, 3]).write(to: invalidURL)
        defer { try? FileManager.default.removeItem(at: invalidURL) }
        passed += expectThrows(
            {
                try validator.validate(fileURL: invalidURL, expectedPackage: package)
            },
            "invalid IMG source is blocked"
        )

        let verifier = TransferVerifier()
        passed += expect(
            verifier.verify(
                sourceSizeBytes: 10,
                sourceSHA256: "abc",
                remoteSizeBytes: 10,
                remoteSHA256: "ABC"
            ).isVerified,
            "matching remote size and hash verify the transfer"
        )
        passed += expect(
            verifier.verify(
                sourceSizeBytes: 10,
                sourceSHA256: "abc",
                remoteSizeBytes: 9,
                remoteSHA256: "abc"
            ).status == .sizeMismatch,
            "remote size mismatch fails verification"
        )
        passed += expect(
            verifier.verify(
                sourceSizeBytes: 10,
                sourceSHA256: "abc",
                remoteSizeBytes: 10,
                remoteSHA256: "def"
            ).status == .hashMismatch,
            "remote hash mismatch fails verification"
        )

        let recoveryPolicy = InstallationFailureRecoveryPolicy()
        let interruptedRecovery = recoveryPolicy.plan(
            for: .deviceDisconnected,
            remoteObjectID: 42,
            remoteObjectWasCreated: true
        )
        passed += expect(
            interruptedRecovery.existingMapMustBePreserved
                && interruptedRecovery.cleanup == .removeExactRemoteObject(objectID: 42)
                && interruptedRecovery.retryRequiresNewTransaction,
            "interrupted transfer preserves the existing map and scopes cleanup to the new object"
        )
        let failedBeforeObjectRecovery = recoveryPolicy.plan(
            for: .writeFailed,
            remoteObjectWasCreated: false
        )
        passed += expect(
            failedBeforeObjectRecovery.cleanup == .none
                && failedBeforeObjectRecovery.existingMapMustBePreserved,
            "failed transfer without a new object performs no remote cleanup"
        )

        var transaction = InstallationTransaction(id: UUID())
        try transaction.begin()
        passed += expectThrows(
            { try transaction.begin() },
            "a transaction cannot start twice"
        )
        try transaction.transition(to: .downloading)
        try transaction.transition(to: .preparing)
        try transaction.recordSource(sizeBytes: 10, sha256: "abc")
        try transaction.transition(to: .readyToWrite)
        try transaction.transition(to: .writing)
        try transaction.transition(to: .verifying)
        passed += expectThrows(
            { try transaction.transition(to: .completed) },
            "a transaction cannot complete before verification"
        )
        try transaction.recordTransferVerification(
            verifier.verify(
                sourceSizeBytes: 10,
                sourceSHA256: "abc",
                remoteSizeBytes: 10,
                remoteSHA256: "abc"
            )
        )
        try transaction.transition(to: .completed)
        passed += expect(
            transaction.state == .completed,
            "a transaction completes only after verified transfer"
        )

        var interruptedTransaction = InstallationTransaction(id: UUID())
        try interruptedTransaction.begin()
        try interruptedTransaction.transition(to: .downloading)
        try interruptedTransaction.transition(to: .preparing)
        try interruptedTransaction.recordSource(sizeBytes: 10, sha256: "abc")
        try interruptedTransaction.transition(to: .readyToWrite)
        try interruptedTransaction.transition(to: .writing)
        try interruptedTransaction.fail(.deviceDisconnected)
        passed += expect(
            interruptedTransaction.state == .failed
                && interruptedTransaction.failure == .deviceDisconnected,
            "interrupted transaction records a failed state and human-readable failure reason"
        )
        passed += expectThrows(
            { try interruptedTransaction.transition(to: .verifying) },
            "interrupted transaction cannot continue the transfer"
        )
        passed += expectThrows(
            { try interruptedTransaction.transition(to: .completed) },
            "interrupted transaction cannot report completion"
        )
        passed += expectThrows(
            { try interruptedTransaction.begin() },
            "interrupted transaction cannot be reused for a retry"
        )

        var mismatchedTransaction = InstallationTransaction(id: UUID())
        try mismatchedTransaction.begin()
        try mismatchedTransaction.transition(to: .downloading)
        try mismatchedTransaction.transition(to: .preparing)
        try mismatchedTransaction.recordSource(sizeBytes: 10, sha256: "abc")
        try mismatchedTransaction.transition(to: .readyToWrite)
        try mismatchedTransaction.transition(to: .writing)
        try mismatchedTransaction.transition(to: .verifying)
        try mismatchedTransaction.recordTransferVerification(
            verifier.verify(
                sourceSizeBytes: 10,
                sourceSHA256: "abc",
                remoteSizeBytes: 10,
                remoteSHA256: "def"
            )
        )
        try mismatchedTransaction.fail(.hashMismatch)
        passed += expect(
            mismatchedTransaction.state == .failed
                && mismatchedTransaction.failure == .hashMismatch,
            "verification mismatch fails closed before completion"
        )

        let gate = InstallationTransactionGate()
        let firstID = UUID()
        let secondID = UUID()
        try gate.acquire(transactionID: firstID)
        passed += expectThrows(
            { try gate.acquire(transactionID: secondID) },
            "transaction gate blocks simultaneous installs"
        )
        gate.release(transactionID: firstID)
        try gate.acquire(transactionID: secondID)
        gate.release(transactionID: secondID)

        print("PASS: \(passed) Stage 3 safety tests")
    }

    private static let gigabyte: UInt64 = 1024 * 1024 * 1024

    private static func makePackage(
        region: String = "LTU",
        version: MapVersion = MapVersion(year: 2026, month: 5)!
    ) -> MapPackage {
        MapPackage(
            id: "freizeitkarte-\(region.lowercased())",
            providerId: "freizeitkarte",
            regionId: region,
            name: region == "LTU" ? "Lithuania" : "Latvia",
            version: version,
            sizeBytes: 344_000_000,
            sourceURL: nil,
            releaseDate: nil,
            identifier: nil
        )
    }

    private static func makeInstalledMap(
        path: String = "/GARMIN/gmapsupp.img",
        filename: String = "gmapsupp.img"
    ) -> InstalledMap {
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
                path: path,
                filename: filename,
                sizeBytes: 344_000_000
            ),
            metadataStatus: .parsed,
            managementState: .detectedNotManaged
        )
    }

    private static func isReplacement(_ resolution: MapConflictResolution) -> Bool {
        guard case .requiresExplicitReplacement(_, ownership: .externalRecognized) = resolution else {
            return false
        }

        return true
    }

    private static func makeValidIMGFile() throws -> URL {
        var bytes = [UInt8](repeating: 0, count: 4096)
        write("DSKIMG", at: 0x10, into: &bytes)
        write("GARMIN", at: 0x41, into: &bytes)
        write("Freizeitkarte_LTU+", at: 0x100, into: &bytes)
        write("Release 26.05", at: 0x200, into: &bytes)

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-stage3-valid-\(UUID().uuidString).img")
        try Data(bytes).write(to: url)
        return url
    }

    private static func write(_ value: String, at offset: Int, into bytes: inout [UInt8]) {
        for (index, byte) in value.utf8.enumerated() {
            bytes[offset + index] = byte
        }
    }

    @discardableResult
    private static func expect(_ condition: Bool, _ message: String) -> Int {
        guard condition else {
            fatalError("FAIL: \(message)")
        }

        print("PASS: \(message)")
        return 1
    }

    @discardableResult
    private static func expectThrows<T>(
        _ operation: () throws -> T,
        _ message: String
    ) -> Int {
        do {
            _ = try operation()
            fatalError("FAIL: \(message)")
        } catch {
            print("PASS: \(message)")
            return 1
        }
    }

    @discardableResult
    private static func expectAsyncThrows<T>(
        _ operation: () async throws -> T,
        _ message: String
    ) async -> Int {
        do {
            _ = try await operation()
            fatalError("FAIL: \(message)")
        } catch {
            print("PASS: \(message)")
            return 1
        }
    }
}
