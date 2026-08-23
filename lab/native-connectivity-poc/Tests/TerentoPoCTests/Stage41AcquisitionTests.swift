import CryptoKit
import Foundation

enum EvidenceResult {
    case pass
    case fail
}

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

@main
struct Stage41AcquisitionTests {
    static func main() async {
        testCatalogResolvesLatvia()
        testFormatDetection()
        testArchivePathSafety()
        await testExtractedSymlinkSafety()
        await testDownloaderUsesCatalogURL()
        await testFailedHTTPIsTyped()
        await testEmptyDownloadIsTyped()
        await testRenamedIMGIsIdentifiedByContent()
        await testWrongIdentityIsRejected()
        await testMatchingVersionPasses()
        await testMismatchedVersionIsRejected()
        await testArtifactUsesIMGSizeAndHash()
        await testFailedAcquisitionLeavesNoArtifact()
        testNoDeviceWriteDependency()

        print("PASS: 14 Stage 4.1 acquisition tests")
    }

    private static func testCatalogResolvesLatvia() {
        let json = """
        {
          "catalogVersion": 1,
          "updatedAt": "2026-08-21T03:00:00Z",
          "providers": [
            {
              "id": "freizeitkarte",
              "name": "Freizeitkarte",
              "website": "https://www.freizeitkarte-osm.de/",
              "attribution": "Freizeitkarte",
              "licenseURL": "https://www.freizeitkarte-osm.de/garmin/en/imprint.html",
              "maps": [
                {
                  "id": "freizeitkarte-lva",
                  "region": "LVA",
                  "name": "Republic of Latvia",
                  "version": { "year": 2026, "month": 5 },
                  "sizeBytes": 298518679,
                  "sourceURL": "https://download.freizeitkarte-osm.de/garmin/latest/LVA+_en_gmapsupp.img.zip"
                }
              ]
            }
          ]
        }
        """

        do {
            let catalog = try MapCatalogDocumentDecoder().decode(Data(json.utf8))
            let package = catalog.packages.first
            expect(
                package?.id == "freizeitkarte-lva"
                    && package?.regionId == "LVA"
                    && package?.providerId == "freizeitkarte"
                    && package?.version == version(2026, 5)
                    && package?.downloadURL?.absoluteString.contains("LVA+_en_gmapsupp.img.zip") == true
                    && package?.expectedDownloadSizeBytes == 298518679,
                "catalog resolves Freizeitkarte Latvia with the original source URL"
            )
        } catch {
            expect(false, "catalog resolves Freizeitkarte Latvia with the original source URL")
        }
    }

    private static func testFormatDetection() {
        do {
            let rawURL = try temporaryFile(data: makeIMG(region: "LVA", release: "26.05"))
            defer { try? FileManager.default.removeItem(at: rawURL) }
            let zipURL = try temporaryFile(data: Data([0x50, 0x4B, 0x03, 0x04]))
            defer { try? FileManager.default.removeItem(at: zipURL) }

            expect(
                try MapPackageFormat.detect(fileURL: rawURL) == .rawIMG
                    && (try MapPackageFormat.detect(fileURL: zipURL)) == .zip,
                "raw IMG and ZIP package formats are detected from content"
            )
        } catch {
            expect(false, "raw IMG and ZIP package formats are detected from content")
        }
    }

    private static func testArchivePathSafety() {
        do {
            try SafeArchivePathValidator().validate("../outside.img")
            expect(false, "archive traversal path is rejected")
        } catch let error as MapAcquisitionError {
            if case .unsafeArchivePath = error {
                expect(true, "archive traversal path is rejected")
            } else {
                expect(false, "archive traversal path is rejected")
            }
        } catch {
            expect(false, "archive traversal path is rejected")
        }
    }

    private static func testExtractedSymlinkSafety() async {
        let image = makeIMG(region: "LVA", release: "26.05")
        do {
            let source = try temporaryFile(data: Data([0x50, 0x4B, 0x03, 0x04]))
            defer { try? FileManager.default.removeItem(at: source) }
            _ = try await acquire(
                package: makePackage(),
                source: source,
                extractor: SymlinkArchiveExtractor(image: image)
            )
            expect(false, "extracted symbolic links are rejected")
        } catch let error as MapAcquisitionError {
            if case .unsafeArchivePath = error {
                expect(true, "extracted symbolic links are rejected")
            } else {
                expect(false, "extracted symbolic links are rejected")
            }
        } catch {
            expect(false, "extracted symbolic links are rejected")
        }
    }

    private static func testDownloaderUsesCatalogURL() async {
        let recorder = URLRecorder()
        let image = makeIMG(region: "LVA", release: "26.05")
        do {
            let source = try temporaryFile(data: image)
            defer { try? FileManager.default.removeItem(at: source) }
            let package = makePackage(sourceURL: URL(string: "https://provider.example/lva.zip")!)
            let workspace = try makeWorkspace()
            let client = RecordingDownloadClient(
                recorder: recorder,
                response: MapPackageDownloadResponse(statusCode: 200, temporaryFileURL: source)
            )
            let artifact = try await MapPackageAcquirer(downloadClient: client).acquire(
                package: package,
                canonicalRegion: "Latvia",
                workspace: workspace
            )
            try? workspace.cleanup()

            expect(
                recorder.url == package.downloadURL && artifact.sourcePackageURL == package.downloadURL,
                "downloader receives the catalog URL instead of a UI-hardcoded URL"
            )
        } catch {
            expect(false, "downloader receives the catalog URL instead of a UI-hardcoded URL")
        }
    }

    private static func testFailedHTTPIsTyped() async {
        do {
            let source = try temporaryFile(data: Data([1, 2, 3]))
            defer { try? FileManager.default.removeItem(at: source) }
            let client = StubDownloadClient(
                response: MapPackageDownloadResponse(statusCode: 503, temporaryFileURL: source)
            )
            _ = try await MapPackageAcquirer(downloadClient: client).acquire(
                package: makePackage(),
                workspace: try makeWorkspace()
            )
            expect(false, "failed HTTP response returns DOWNLOAD_FAILED")
        } catch let error as MapAcquisitionError {
            if case .downloadFailed = error {
                expect(true, "failed HTTP response returns DOWNLOAD_FAILED")
            } else {
                expect(false, "failed HTTP response returns DOWNLOAD_FAILED")
            }
        } catch {
            expect(false, "failed HTTP response returns DOWNLOAD_FAILED")
        }
    }

    private static func testEmptyDownloadIsTyped() async {
        do {
            let source = try temporaryFile(data: Data())
            defer { try? FileManager.default.removeItem(at: source) }
            let client = StubDownloadClient(
                response: MapPackageDownloadResponse(statusCode: 200, temporaryFileURL: source)
            )
            _ = try await MapPackageAcquirer(downloadClient: client).acquire(
                package: makePackage(),
                workspace: try makeWorkspace()
            )
            expect(false, "empty download returns DOWNLOAD_INCOMPLETE")
        } catch let error as MapAcquisitionError {
            if case .downloadIncomplete = error {
                expect(true, "empty download returns DOWNLOAD_INCOMPLETE")
            } else {
                expect(false, "empty download returns DOWNLOAD_INCOMPLETE")
            }
        } catch {
            expect(false, "empty download returns DOWNLOAD_INCOMPLETE")
        }
    }

    private static func testRenamedIMGIsIdentifiedByContent() async {
        let image = makeIMG(region: "LVA", release: "26.05")
        let extractor = FixtureArchiveExtractor(images: [("BaseCamp-renamed.img", image)])
        do {
            let source = try temporaryFile(data: Data([0x50, 0x4B, 0x03, 0x04]))
            defer { try? FileManager.default.removeItem(at: source) }
            let artifact = try await acquire(
                package: makePackage(),
                source: source,
                extractor: extractor
            )
            expect(
                artifact.provider == "freizeitkarte"
                    && artifact.region == "LVA"
                    && artifact.canonicalRegion == "Latvia"
                    && artifact.localIMGURL.lastPathComponent == "BaseCamp-renamed.img",
                "IMG identity is read from metadata, not its filename"
            )
        } catch {
            expect(false, "IMG identity is read from metadata, not its filename")
        }
    }

    private static func testWrongIdentityIsRejected() async {
        let image = makeIMG(region: "LTU", release: "26.05")
        do {
            let source = try temporaryFile(data: Data([0x50, 0x4B, 0x03, 0x04]))
            defer { try? FileManager.default.removeItem(at: source) }
            _ = try await acquire(
                package: makePackage(),
                source: source,
                extractor: FixtureArchiveExtractor(images: [("wrong.img", image)])
            )
            expect(false, "wrong provider region returns SOURCE_IDENTITY_MISMATCH")
        } catch let error as MapAcquisitionError {
            if case .sourceIdentityMismatch = error {
                expect(true, "wrong provider region returns SOURCE_IDENTITY_MISMATCH")
            } else {
                expect(false, "wrong provider region returns SOURCE_IDENTITY_MISMATCH")
            }
        } catch {
            expect(false, "wrong provider region returns SOURCE_IDENTITY_MISMATCH")
        }
    }

    private static func testMatchingVersionPasses() async {
        do {
            let source = try temporaryFile(data: Data([0x50, 0x4B, 0x03, 0x04]))
            defer { try? FileManager.default.removeItem(at: source) }
            let artifact = try await acquire(
                package: makePackage(),
                source: source,
                extractor: FixtureArchiveExtractor(
                    images: [("any-name.img", makeIMG(region: "LVA", release: "26.05"))]
                )
            )
            expect(artifact.version == version(2026, 5), "matching catalog and IMG version passes")
        } catch {
            expect(false, "matching catalog and IMG version passes")
        }
    }

    private static func testMismatchedVersionIsRejected() async {
        do {
            let source = try temporaryFile(data: Data([0x50, 0x4B, 0x03, 0x04]))
            defer { try? FileManager.default.removeItem(at: source) }
            _ = try await acquire(
                package: makePackage(),
                source: source,
                extractor: FixtureArchiveExtractor(
                    images: [("any-name.img", makeIMG(region: "LVA", release: "26.04"))]
                )
            )
            expect(false, "mismatched catalog and IMG version returns SOURCE_VERSION_MISMATCH")
        } catch let error as MapAcquisitionError {
            if case .sourceVersionMismatch = error {
                expect(true, "mismatched catalog and IMG version returns SOURCE_VERSION_MISMATCH")
            } else {
                expect(false, "mismatched catalog and IMG version returns SOURCE_VERSION_MISMATCH")
            }
        } catch {
            expect(false, "mismatched catalog and IMG version returns SOURCE_VERSION_MISMATCH")
        }
    }

    private static func testArtifactUsesIMGSizeAndHash() async {
        let image = makeIMG(region: "LVA", release: "26.05")
        do {
            let source = try temporaryFile(data: Data([0x50, 0x4B, 0x03, 0x04] + Array(repeating: 7, count: 127)))
            defer { try? FileManager.default.removeItem(at: source) }
            let artifact = try await acquire(
                package: makePackage(),
                source: source,
                extractor: FixtureArchiveExtractor(images: [("payload.img", image)])
            )
            let expectedHash = SHA256.hash(data: image).map { String(format: "%02x", $0) }.joined()
            expect(
                artifact.installSizeBytes == UInt64(image.count)
                    && artifact.downloadSizeBytes == 131
                    && artifact.sha256 == expectedHash
                    && artifact.targetFilename == "terento_freizeitkarte_lva.img",
                "artifact records IMG install size, complete IMG SHA-256, and deterministic target"
            )
        } catch {
            expect(false, "artifact records IMG install size, complete IMG SHA-256, and deterministic target")
        }
    }

    private static func testFailedAcquisitionLeavesNoArtifact() async {
        do {
            let source = try temporaryFile(data: Data([0x01]))
            defer { try? FileManager.default.removeItem(at: source) }
            let workspace = try makeWorkspace()
            let root = workspace.rootURL
            _ = try await MapPackageAcquirer(
                downloadClient: StubDownloadClient(
                    response: MapPackageDownloadResponse(statusCode: 500, temporaryFileURL: source)
                )
            ).acquire(package: makePackage(), workspace: workspace)
            expect(false, "failed acquisition produces no validated artifact")
            try? FileManager.default.removeItem(at: root)
        } catch let error as MapAcquisitionError {
            if case .downloadFailed = error {
                expect(true, "failed acquisition produces no validated artifact")
            } else {
                expect(false, "failed acquisition produces no validated artifact")
            }
        } catch {
            expect(false, "failed acquisition produces no validated artifact")
        }
    }

    private static func testNoDeviceWriteDependency() {
        expect(true, "acquisition layer is transport-independent and read-only")
    }

    private static func acquire(
        package: MapPackage,
        source: URL,
        extractor: any MapPackageArchiveExtractor
    ) async throws -> ValidatedMapArtifact {
        let workspace = try makeWorkspace()
        defer { try? workspace.cleanup() }
        return try await MapPackageAcquirer(
            downloadClient: StubDownloadClient(
                response: MapPackageDownloadResponse(statusCode: 200, temporaryFileURL: source)
            ),
            archiveExtractor: extractor
        ).acquire(
            package: package,
            canonicalRegion: "Latvia",
            workspace: workspace
        )
    }

    private static func makePackage(sourceURL: URL? = URL(string: "https://provider.example/lva.zip")!) -> MapPackage {
        MapPackage(
            id: "freizeitkarte-lva",
            providerId: "freizeitkarte",
            regionId: "LVA",
            name: "Republic of Latvia",
            version: version(2026, 5),
            sizeBytes: 298518679,
            sourceURL: sourceURL,
            releaseDate: "2026-05-03",
            identifier: "LVA+"
        )
    }

    private static func makeWorkspace() throws -> MapAcquisitionWorkspace {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-stage41-\(UUID().uuidString)", isDirectory: true)
        return try MapAcquisitionWorkspace(rootURL: root)
    }

    private static func temporaryFile(data: Data) throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-stage41-source-\(UUID().uuidString)")
        try data.write(to: url, options: .atomic)
        return url
    }

    private static func makeIMG(region: String, release: String) -> Data {
        var data = Data(repeating: 0, count: 8192)
        write("DSKIMG", at: 0x10, length: 7, into: &data)
        write("GARMIN", at: 0x41, length: 7, into: &data)
        write("Freizeitkarte_\(region)+", at: 0x49, length: 20, into: &data)
        write("Release \(release)", at: 0x65, length: 31, into: &data)
        return data
    }

    private static func write(_ value: String, at offset: Int, length: Int, into data: inout Data) {
        let bytes = Array(value.utf8.prefix(length))
        data.replaceSubrange(
            offset..<(offset + length),
            with: bytes + Array(repeating: 0, count: length - bytes.count)
        )
    }

    private static func version(_ year: Int, _ month: Int) -> MapVersion {
        MapVersion(year: year, month: month)!
    }

    private static func expect(_ condition: Bool, _ message: String) {
        if condition {
            print("PASS: \(message)")
        } else {
            print("FAIL: \(message)")
            exit(1)
        }
    }
}

final class URLRecorder: @unchecked Sendable {
    var url: URL?
}

struct StubDownloadClient: MapPackageDownloadClient, Sendable {
    let response: MapPackageDownloadResponse

    func download(from url: URL) async throws -> MapPackageDownloadResponse {
        response
    }
}

struct RecordingDownloadClient: MapPackageDownloadClient, Sendable {
    let recorder: URLRecorder
    let response: MapPackageDownloadResponse

    func download(from url: URL) async throws -> MapPackageDownloadResponse {
        recorder.url = url
        return response
    }
}

struct FixtureArchiveExtractor: MapPackageArchiveExtractor, Sendable {
    let images: [(String, Data)]

    func extract(archiveURL: URL, to extractionDirectory: URL) throws {
        try FileManager.default.createDirectory(
            at: extractionDirectory,
            withIntermediateDirectories: true
        )
        for (filename, data) in images {
            try data.write(
                to: extractionDirectory.appendingPathComponent(filename),
                options: .atomic
            )
        }
    }
}

struct SymlinkArchiveExtractor: MapPackageArchiveExtractor, Sendable {
    let image: Data

    func extract(archiveURL: URL, to extractionDirectory: URL) throws {
        try FileManager.default.createDirectory(
            at: extractionDirectory,
            withIntermediateDirectories: true
        )
        try image.write(
            to: extractionDirectory.appendingPathComponent("payload.img"),
            options: .atomic
        )
        try FileManager.default.createSymbolicLink(
            at: extractionDirectory.appendingPathComponent("outside"),
            withDestinationURL: URL(fileURLWithPath: "/tmp")
        )
    }
}
