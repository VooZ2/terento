import Foundation

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

struct SafeUpdateProgress: Equatable, Sendable {
    let value: Int
}

@main
struct Stage2CustomMapImportTests {
    static func main() {
        testRawIMGIsPreparedAsCustomSource()
        testNonIMGContentIsRejectedWithConfirmationWarning()
        testNonRegularFileIsRejected()
        testUnchangedCachedCustomIMGIsRevalidated()
        testCachedCustomIMGIsRevalidatedBeforeInstall()
        testCustomArtifactPassesSharedArtifactGate()
        testCustomManifestRecordRestoresOwnership()
        testCustomLifecycleHasRemoveButNoUpdate()
        print("PASS: 8 Stage 2 custom map import tests")
    }

    private static func testRawIMGIsPreparedAsCustomSource() {
        let fixture = makeFixture(name: "valid")
        defer { cleanup(fixture.root) }

        do {
            let candidate = try acquirer(root: fixture.root).prepare(fileURL: fixture.file)
            expect(candidate.package.sourceKind == .custom, "custom import creates an explicit custom package")
            expect(candidate.package.name == "Custom map", "custom import uses the Custom map display name")
            expect(candidate.package.sourceURL == nil, "custom import has no provider download URL")
            expect(candidate.artifact.sourceKind == .custom, "custom import creates a custom validated artifact")
            expect(candidate.artifact.packageFormat == .rawIMG, "custom import records the raw IMG format")
            expect(candidate.artifact.installSizeBytes == 8192, "custom import measures the IMG size")
            expect(candidate.artifact.sha256.count == 64, "custom import records a full SHA-256")
            expect(
                TerentoManagedFilenameGenerator().isValid(candidate.artifact.targetFilename),
                "custom import produces a safe Terento-managed filename"
            )
        } catch {
            fail("valid custom IMG should be prepared: \(error)")
        }
    }

    private static func testNonIMGContentIsRejectedWithConfirmationWarning() {
        let fixture = makeFixture(name: "installer")
        defer { cleanup(fixture.root) }
        try? Data("not a Garmin map".utf8).write(to: fixture.file)

        do {
            _ = try acquirer(root: fixture.root).prepare(fileURL: fixture.file)
            fail("content without a Garmin IMG header must not be accepted")
        } catch MapAcquisitionError.customMapNotConfirmed {
            expect(true, "unconfirmed IMG content produces the user warning error")
        } catch {
            fail("unconfirmed IMG content should use the confirmation warning: \(error)")
        }
    }

    private static func testNonRegularFileIsRejected() {
        let fixture = makeFixture(name: "symlink")
        cleanup(fixture.root)
        let root = fixture.root
        let valid = root.appendingPathComponent("source.img")
        let link = root.appendingPathComponent("linked.img")
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try? makeIMGData().write(to: valid)
        try? FileManager.default.createSymbolicLink(at: link, withDestinationURL: valid)
        defer { cleanup(root) }

        do {
            _ = try acquirer(root: root).prepare(fileURL: link)
            fail("symbolic links must not enter the custom import workspace")
        } catch MapAcquisitionError.invalidPackage {
            expect(true, "symbolic link input is rejected before content preparation")
        } catch {
            fail("symbolic link input should be rejected as an invalid file: \(error)")
        }
    }

    private static func testCachedCustomIMGIsRevalidatedBeforeInstall() {
        let fixture = makeFixture(name: "toctou")
        defer { cleanup(fixture.root) }

        do {
            let candidate = try acquirer(root: fixture.root).prepare(fileURL: fixture.file)
            var changed = try Data(contentsOf: candidate.artifact.localIMGURL)
            changed[0] ^= 0xFF
            try changed.write(to: candidate.artifact.localIMGURL)

            do {
                _ = try CustomMapSourceAcquirer().revalidate(candidate)
                fail("changed cached IMG must not pass the preflight revalidation")
            } catch MapAcquisitionError.invalidPackage {
                expect(true, "custom cached content is protected by a second hash check")
            } catch {
                fail("changed cached IMG should fail closed: \(error)")
            }
        } catch {
            fail("valid custom IMG should be prepared for revalidation: \(error)")
        }
    }

    private static func testUnchangedCachedCustomIMGIsRevalidated() {
        let fixture = makeFixture(name: "revalidate")
        defer { cleanup(fixture.root) }

        do {
            let candidate = try acquirer(root: fixture.root).prepare(fileURL: fixture.file)
            _ = try CustomMapSourceAcquirer().revalidate(candidate)
            expect(
                candidate.artifact.localIMGURL.pathExtension == "img",
                "custom cache keeps the IMG extension for the preflight recheck"
            )
            expect(true, "unchanged cached custom IMG passes the preflight revalidation")
        } catch {
            fail("unchanged custom IMG should pass revalidation: \(error)")
        }
    }

    private static func testCustomArtifactPassesSharedArtifactGate() {
        let fixture = makeFixture(name: "artifact")
        defer { cleanup(fixture.root) }

        do {
            let candidate = try acquirer(root: fixture.root).prepare(fileURL: fixture.file)
            try Stage42ArtifactValidator().validate(
                artifact: candidate.artifact,
                package: candidate.package
            )
            expect(true, "custom artifact passes the shared exact-source gate")
        } catch {
            fail("prepared custom artifact should pass the shared gate: \(error)")
        }
    }

    private static func testCustomManifestRecordRestoresOwnership() {
        let file = InstalledMapFile(
            path: "/GARMIN/terento_custom_img_abc.img",
            filename: "terento_custom_img_abc.img",
            sizeBytes: 8192,
            itemID: 7
        )
        let metadata = GarminIMGMetadata(
            name: "Unknown custom header",
            provider: nil,
            region: nil,
            family: "Unknown custom header",
            rawVersion: nil,
            version: nil,
            identifier: nil,
            productId: nil,
            familyId: nil
        )
        let record = MapOwnershipRecord(
            devicePath: file.path,
            filename: file.filename,
            providerId: "custom",
            regionId: "img_abc",
            version: version(2000, 1),
            sizeBytes: file.sizeBytes
        )
        expect(
            MapOwnershipMatcher().managementState(
                for: file,
                metadata: metadata,
                records: [record]
            ) == .managedByTerento,
            "an exact custom manifest record restores Terento ownership"
        )
    }

    private static func testCustomLifecycleHasRemoveButNoUpdate() {
        let file = InstalledMapFile(
            path: "/GARMIN/terento_custom_img_abc.img",
            filename: "terento_custom_img_abc.img",
            sizeBytes: 8192,
            itemID: 7
        )
        let installed = InstalledMap(
            name: "Custom map",
            provider: nil,
            region: nil,
            family: "Custom map",
            rawVersion: nil,
            version: version(2000, 1),
            identifier: nil,
            productId: nil,
            familyId: nil,
            sizeBytes: file.sizeBytes,
            sourceFile: file,
            metadataStatus: .parsed,
            managementState: .managedByTerento
        )
        let item = MapLifecycleItem(
            id: file.path,
            title: "Custom map",
            provider: nil,
            region: nil,
            version: installed.version,
            rawVersion: nil,
            sizeBytes: installed.sizeBytes,
            installedMaps: [installed],
            classification: .terentoManaged
        )
        let availability = MapLifecyclePresentationResolver().resolve(
            item: item,
            comparison: nil,
            hasIntegrityRecord: true,
            hasValidatedUpdateProfile: true,
            hasStableWatchIdentity: true
        )

        expect(
            availability.actions == [.backup, .remove, .transferOwnership]
                && !availability.actions.contains(.update),
            "custom managed maps expose removal but never expose Update"
        )
        expect(
            item.manageDetailLabel == "Installed · From this Mac",
            "custom managed maps show their local source without an update claim"
        )
    }

    private static func acquirer(root: URL) -> CustomMapSourceAcquirer {
        CustomMapSourceAcquirer {
            try MapAcquisitionWorkspace(rootURL: root.appendingPathComponent(UUID().uuidString))
        }
    }

    private static func makeFixture(name: String) -> (root: URL, file: URL) {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-stage2-\(name)-\(UUID().uuidString)")
        let file = root.appendingPathComponent("\(name).img")
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try? makeIMGData().write(to: file)
        return (root, file)
    }

    private static func makeIMGData() -> Data {
        var bytes = Array(repeating: UInt8(0), count: 8192)
        for (offset, byte) in Array("DSKIMG".utf8).enumerated() {
            bytes[0x10 + offset] = byte
        }
        for (offset, byte) in Array("GARMIN".utf8).enumerated() {
            bytes[0x41 + offset] = byte
        }
        for (offset, byte) in Array("USER MAP".utf8).enumerated() {
            bytes[0x49 + offset] = byte
        }
        return Data(bytes)
    }

    private static func cleanup(_ url: URL) {
        try? FileManager.default.removeItem(at: url)
    }

    private static func version(_ year: Int, _ month: Int) -> MapVersion {
        MapVersion(year: year, month: month)!
    }

    private static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        guard condition() else { fail(message) }
        print("PASS: \(message)")
    }

    private static func fail(_ message: String) -> Never {
        print("FAIL: \(message)")
        exit(1)
    }
}
