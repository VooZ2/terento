import Foundation

enum TerentoAppMetadata {
    static let version = "1.0.0"
    static let build = "1"
}

private enum TestError: LocalizedError {
    case offline

    var errorDescription: String? { "offline" }
}

private final class TestCounter: @unchecked Sendable {
    private(set) var value = 0

    func increment() {
        value += 1
    }
}

private final class TestResultQueue: @unchecked Sendable {
    private var results: [Result<TerentoAppUpdateResult, Error>]

    init(_ results: [Result<TerentoAppUpdateResult, Error>]) {
        self.results = results
    }

    func next() throws -> TerentoAppUpdateResult {
        guard !results.isEmpty else { throw TestError.offline }
        return try results.removeFirst().get()
    }
}

@MainActor
@main
struct AppUpdateTests {
    static func main() async throws {
        try testSameVersionIsUpToDate()
        try testHigherBuildIsAvailable()
        try testBeta9MaintenanceBuildIsAvailable()
        try testHigherMarketingVersionIsAvailable()
        try testOlderReleaseIsUpToDate()
        try testIncompatibleMinimumMacOS()
        try testManifestDecodesOptionalFields()
        try testInvalidManifestValuesAreRejected()
        try await testAutomaticCheckRunsOncePerLaunch()
        try await testManualCheckRunsAfterAutomaticCheck()
        try await testStartupFailureIsSilent()
        try await testManualFailureIsVisible()
        try await testDeferredUpdateCanOfferNewerBuild()
        try await testPromptWaitsForSafeIdle()
        try testTrustedURLsAreRestricted()
        print("PASS: 15 app update tests")
    }

    private static func testSameVersionIsUpToDate() throws {
        let result = try TerentoAppUpdateService.evaluate(
            manifest: manifest(version: "1.0.0", build: 1),
            current: installedVersion(build: 1)
        )
        expect(result == .upToDate, "same version and build remains up to date")
    }

    private static func testHigherBuildIsAvailable() throws {
        let result = try TerentoAppUpdateService.evaluate(
            manifest: manifest(version: "1.0.0", build: 2),
            current: installedVersion(build: 1)
        )
        expect(isAvailable(result, version: "1.0.0"), "higher build is available")
    }

    private static func testBeta9MaintenanceBuildIsAvailable() throws {
        let result = try TerentoAppUpdateService.evaluate(
            manifest: manifest(
                version: "1.0.0",
                build: 10,
                releaseLabel: "1.0.0-beta.9"
            ),
            current: installedVersion(build: 9)
        )
        expect(
            isAvailable(result, version: "1.0.0"),
            "beta.9 build 10 is offered to beta.9 build 9"
        )
    }

    private static func testHigherMarketingVersionIsAvailable() throws {
        let result = try TerentoAppUpdateService.evaluate(
            manifest: manifest(version: "1.1.0", build: 1),
            current: installedVersion(build: 99)
        )
        expect(isAvailable(result, version: "1.1.0"), "higher marketing version is available")
    }

    private static func testOlderReleaseIsUpToDate() throws {
        let result = try TerentoAppUpdateService.evaluate(
            manifest: manifest(version: "0.9.9", build: 99),
            current: installedVersion(build: 1)
        )
        expect(result == .upToDate, "older remote release is not offered")
    }

    private static func testIncompatibleMinimumMacOS() throws {
        let result = try TerentoAppUpdateService.evaluate(
            manifest: manifest(version: "1.0.0", build: 2, minimumMacOS: "14.0"),
            current: installedVersion(build: 1),
            currentMacOSVersion: "13.6"
        )
        guard case .incompatible = result else {
            fail("newer build requiring newer macOS is incompatible")
        }
    }

    private static func testManifestDecodesOptionalFields() throws {
        let data = Data(
            """
            {
              "schemaVersion": 1,
              "product": "Terento",
              "platform": "macOS",
              "architecture": "arm64",
              "version": "1.0.0",
              "build": 2,
              "releaseLabel": "1.0.0-beta.3",
              "downloadURL": "https://github.com/VooZ2/terento/releases/download/v1.0.0-beta.3/Terento.dmg",
              "releaseURL": "https://github.com/VooZ2/terento/releases/tag/v1.0.0-beta.3",
              "summary": "A short release summary.",
              "releaseNotesURL": "https://github.com/VooZ2/terento/releases/tag/v1.0.0-beta.3",
              "publishedAt": "2026-08-26",
              "channel": "beta",
              "sha256": null,
              "minimumMacOS": "13.0"
            }
            """.utf8
        )
        let decoded = try JSONDecoder().decode(TerentoAppUpdateManifest.self, from: data)
        expect(decoded.summary == "A short release summary.", "summary is decoded")
        expect(decoded.releaseNotesURL != nil, "release notes URL is decoded")
        expect(decoded.minimumMacOS == "13.0", "minimum macOS is decoded")
        expect(decoded.channel == .beta, "update channel is decoded")
        try TerentoAppUpdateService.validate(manifest: decoded)

        let legacyJSON = Data(
            """
            {
              "schemaVersion": 1,
              "product": "Terento",
              "platform": "macOS",
              "architecture": "arm64",
              "version": "1.0.0",
              "build": 2,
              "releaseLabel": "1.0.0-beta.3",
              "downloadURL": "https://github.com/VooZ2/terento/releases/download/v1.0.0-beta.3/Terento.dmg",
              "releaseURL": "https://github.com/VooZ2/terento/releases/tag/v1.0.0-beta.3",
              "sha256": null
            }
            """.utf8
        )
        let legacyDecoded = try JSONDecoder().decode(
            TerentoAppUpdateManifest.self,
            from: legacyJSON
        )
        expect(legacyDecoded.summary == nil, "missing summary remains optional")
        expect(legacyDecoded.releaseNotesURL == nil, "missing release notes remains optional")
        expect(legacyDecoded.channel == .beta, "missing channel safely defaults to beta")
    }

    private static func testInvalidManifestValuesAreRejected() throws {
        do {
            try TerentoAppUpdateService.validate(
                manifest: manifest(version: "1.0.0", build: 0)
            )
            fail("invalid build is rejected")
        } catch TerentoAppUpdateError.invalidManifest {
            // Expected.
        }

        do {
            try TerentoAppUpdateService.validate(
                manifest: manifest(version: "1.0.0", build: 2, minimumMacOS: "macOS 14")
            )
            fail("invalid minimum macOS is rejected")
        } catch TerentoAppUpdateError.invalidManifest {
            // Expected.
        }

        do {
            try TerentoAppUpdateService.validate(
                manifest: manifest(version: "not-a-version", build: 2)
            )
            fail("invalid release version is rejected")
        } catch TerentoAppUpdateError.invalidManifest {
            // Expected.
        }
    }

    private static func testAutomaticCheckRunsOncePerLaunch() async throws {
        let counter = TestCounter()
        let controller = AppUpdateController(
            currentVersionProvider: { installedVersion(build: 1) },
            checkOperation: { _ in
                counter.increment()
                return .upToDate
            }
        )

        controller.startAutomaticCheck()
        await controller.waitForCurrentCheck()
        controller.startAutomaticCheck()
        await controller.waitForCurrentCheck()
        expect(counter.value == 1, "automatic check runs once per launch")
    }

    private static func testManualCheckRunsAfterAutomaticCheck() async throws {
        let counter = TestCounter()
        let controller = AppUpdateController(
            currentVersionProvider: { installedVersion(build: 1) },
            checkOperation: { _ in
                counter.increment()
                return .upToDate
            }
        )

        controller.startAutomaticCheck()
        await controller.waitForCurrentCheck()
        controller.checkForUpdates()
        await controller.waitForCurrentCheck()
        expect(counter.value == 2, "manual check can run after automatic check")
        expect(controller.state == .upToDate, "manual check publishes up-to-date state")
    }

    private static func testStartupFailureIsSilent() async throws {
        let controller = AppUpdateController(
            currentVersionProvider: { installedVersion(build: 1) },
            checkOperation: { _ in throw TestError.offline }
        )

        controller.startAutomaticCheck()
        await controller.waitForCurrentCheck()
        expect(controller.state == .idle, "automatic failure returns to silent idle state")
    }

    private static func testManualFailureIsVisible() async throws {
        let controller = AppUpdateController(
            currentVersionProvider: { installedVersion(build: 1) },
            checkOperation: { _ in throw TestError.offline }
        )

        controller.checkForUpdates()
        await controller.waitForCurrentCheck()
        guard case .failed("offline") = controller.state else {
            fail("manual failure is visible in the update state")
        }
    }

    private static func testDeferredUpdateCanOfferNewerBuild() async throws {
        let firstUpdate = manifest(version: "1.0.0", build: 2)
        let laterUpdate = manifest(version: "1.0.0", build: 3)
        let queue = TestResultQueue([
            .success(.available(firstUpdate)),
            .success(.available(firstUpdate)),
            .success(.available(laterUpdate))
        ])
        let controller = AppUpdateController(
            currentVersionProvider: { installedVersion(build: 1) },
            checkOperation: { _ in try queue.next() }
        )

        controller.startAutomaticCheck()
        await controller.waitForCurrentCheck()
        guard let offered = controller.claimPromptIfSafe(true) else {
            fail("available update is offered when UI is safe")
        }
        controller.deferPrompt(for: offered)
        expect(
            controller.claimPromptIfSafe(true) == nil,
            "Later suppresses the same build for this launch"
        )

        controller.checkForUpdates()
        await controller.waitForCurrentCheck()
        expect(
            controller.claimPromptIfSafe(true) == nil,
            "deferral does not immediately re-prompt the same build"
        )

        controller.checkForUpdates()
        await controller.waitForCurrentCheck()
        guard let newer = controller.claimPromptIfSafe(true), newer.build == 3 else {
            fail("newer build is eligible after an earlier deferral")
        }
    }

    private static func testPromptWaitsForSafeIdle() async throws {
        let update = manifest(version: "1.0.0", build: 2)
        let controller = AppUpdateController(
            currentVersionProvider: { installedVersion(build: 1) },
            checkOperation: { _ in .available(update) }
        )
        controller.startAutomaticCheck()
        await controller.waitForCurrentCheck()
        expect(
            controller.claimPromptIfSafe(false) == nil,
            "active UI does not present an update prompt"
        )
        expect(
            controller.claimPromptIfSafe(true)?.build == 2,
            "pending update presents when UI becomes safely idle"
        )
    }

    private static func testTrustedURLsAreRestricted() throws {
        expect(
            TerentoAppUpdateService.isTrustedDownloadURL(
                URL(string: "https://github.com/VooZ2/terento/releases/download/v1.0.0-beta.6/Terento.dmg")!
            ),
            "official Terento DMG URL is trusted"
        )
        expect(
            !TerentoAppUpdateService.isTrustedDownloadURL(
                URL(string: "https://github.com/other/repo/releases/download/v1.0.0/Terento.dmg")!
            ),
            "untrusted GitHub repository is rejected"
        )
        expect(
            !TerentoAppUpdateService.isTrustedDownloadURL(
                URL(string: "https://github.com/VooZ2/terento/archive/v1.0.0.zip")!
            ),
            "non-release distribution path is rejected"
        )
        expect(
            TerentoAppUpdateService.isTrustedReleaseNotesURL(
                URL(string: "https://github.com/VooZ2/terento/releases/tag/v1.0.0-beta.6")!
            ),
            "official GitHub release notes URL is trusted"
        )
        expect(
            TerentoAppUpdateService.isTrustedReleaseNotesURL(
                URL(string: "https://terento.app/release-notes/1.0.0-beta.6")!
            ),
            "official Terento release notes URL is trusted"
        )
        expect(
            !TerentoAppUpdateService.isTrustedReleaseNotesURL(
                URL(string: "https://example.com/notes/1.0.0-beta.6")!
            ),
            "arbitrary release notes URL is rejected"
        )

        do {
            try TerentoAppUpdateService.validate(
                manifest: manifest(
                    version: "1.0.0",
                    build: 2,
                    releaseNotesURL: URL(string: "https://example.com/notes")!
                )
            )
            fail("untrusted release notes manifest is rejected")
        } catch TerentoAppUpdateError.invalidReleaseNotesURL {
            // Expected.
        }
    }

    private static func manifest(
        version: String,
        build: Int,
        releaseLabel: String? = nil,
        minimumMacOS: String? = "13.0",
        releaseNotesURL: URL? = URL(
            string: "https://github.com/VooZ2/terento/releases/tag/test"
        )
    ) -> TerentoAppUpdateManifest {
        TerentoAppUpdateManifest(
            schemaVersion: 1,
            product: "Terento",
            platform: "macOS",
            architecture: "arm64",
            version: version,
            build: build,
            releaseLabel: releaseLabel ?? "\(version)-beta.test",
            downloadURL: URL(
                string: "https://github.com/VooZ2/terento/releases/download/test/Terento.dmg"
            )!,
            releaseURL: URL(
                string: "https://github.com/VooZ2/terento/releases/tag/test"
            )!,
            releaseNotesURL: releaseNotesURL,
            summary: "A concise test summary.",
            publishedAt: "2026-08-26",
            channel: .beta,
            sha256: nil,
            minimumMacOS: minimumMacOS
        )
    }

    nonisolated private static func installedVersion(build: Int) -> TerentoInstalledVersion {
        TerentoInstalledVersion(version: "1.0.0", build: build, channel: .beta)
    }

    private static func isAvailable(
        _ result: TerentoAppUpdateResult,
        version: String
    ) -> Bool {
        guard case let .available(manifest) = result else { return false }
        return manifest.version == version
    }

    private static func expect(_ condition: Bool, _ message: String) {
        guard condition else { fail(message) }
    }

    private static func fail(_ message: String) -> Never {
        fputs("FAIL: \(message)\n", stderr)
        exit(1)
    }
}
