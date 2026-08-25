import Foundation

enum TerentoAppMetadata {
    static let version = "1.0.0"
    static let build = "1"
}

@main
struct AppUpdateTests {
    static func main() throws {
        try testSameVersionIsLatest()
        try testHigherBuildIsAvailable()
        try testHigherMarketingVersionIsAvailable()
        try testOlderReleaseIsLatest()
        try testManifestDecodes()
        try testInvalidVersionIsRejected()
        print("PASS: 6 app update tests")
    }

    private static func testSameVersionIsLatest() throws {
        let result = try TerentoAppUpdateService.evaluate(
            manifest: manifest(version: "1.0.0", build: 1),
            current: TerentoInstalledVersion(version: "1.0.0", build: 1)
        )
        expect(result == .latest, "same version and build remains latest")
    }

    private static func testHigherBuildIsAvailable() throws {
        let result = try TerentoAppUpdateService.evaluate(
            manifest: manifest(version: "1.0.0", build: 2),
            current: TerentoInstalledVersion(version: "1.0.0", build: 1)
        )
        expect(isAvailable(result, version: "1.0.0"), "higher build is available")
    }

    private static func testHigherMarketingVersionIsAvailable() throws {
        let result = try TerentoAppUpdateService.evaluate(
            manifest: manifest(version: "1.1.0", build: 1),
            current: TerentoInstalledVersion(version: "1.0.0", build: 99)
        )
        expect(isAvailable(result, version: "1.1.0"), "higher marketing version is available")
    }

    private static func testOlderReleaseIsLatest() throws {
        let result = try TerentoAppUpdateService.evaluate(
            manifest: manifest(version: "0.9.9", build: 99),
            current: TerentoInstalledVersion(version: "1.0.0", build: 1)
        )
        expect(result == .latest, "older remote release is not offered")
    }

    private static func testManifestDecodes() throws {
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
              "sha256": null,
              "minimumMacOS": "13.0"
            }
            """.utf8
        )
        let decoded = try JSONDecoder().decode(TerentoAppUpdateManifest.self, from: data)
        expect(decoded.displayVersion == "1.0.0-beta.3", "release label is preserved")
    }

    private static func testInvalidVersionIsRejected() throws {
        do {
            _ = try TerentoAppUpdateService.evaluate(
                manifest: manifest(version: "not-a-version", build: 2),
                current: TerentoInstalledVersion(version: "1.0.0", build: 1)
            )
            fail("invalid release version is rejected")
        } catch TerentoAppUpdateError.invalidManifest {
            return
        }
    }

    private static func manifest(version: String, build: Int) -> TerentoAppUpdateManifest {
        TerentoAppUpdateManifest(
            schemaVersion: 1,
            product: "Terento",
            platform: "macOS",
            architecture: "arm64",
            version: version,
            build: build,
            releaseLabel: "(version)-beta.test",
            downloadURL: URL(string: "https://github.com/VooZ2/terento/releases/download/test/Terento.dmg")!,
            releaseURL: URL(string: "https://github.com/VooZ2/terento/releases/tag/test")!,
            sha256: nil,
            minimumMacOS: "13.0"
        )
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
        fputs("FAIL: (message)\n", stderr)
        exit(1)
    }
}
