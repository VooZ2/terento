import Foundation

enum TerentoAppLinks {
    static let website = URL(string: "https://terento.app")!
    static let documentation = URL(string: "https://github.com/VooZ2/terento#readme")!
    static let issues = URL(string: "https://github.com/VooZ2/terento/issues")!
    static let repository = URL(string: "https://github.com/VooZ2/terento")!
    static let privacy = URL(string: "https://terento.app/privacy/#compatibility-reports")!
}

struct TerentoInstalledVersion: Equatable, Sendable {
    let version: String
    let build: Int

    static func current(bundle: Bundle = .main) -> TerentoInstalledVersion {
        let version = bundle.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
            ?? TerentoAppMetadata.version
        let build = Int(
            (bundle.object(forInfoDictionaryKey: "CFBundleVersion") as? String)
                ?? TerentoAppMetadata.build
        ) ?? 0
        return TerentoInstalledVersion(version: version, build: build)
    }
}

struct TerentoAppUpdateManifest: Codable, Equatable, Sendable {
    let schemaVersion: Int
    let product: String
    let platform: String
    let architecture: String
    let version: String
    let build: Int
    let releaseLabel: String
    let downloadURL: URL
    let releaseURL: URL
    let sha256: String?
    let minimumMacOS: String?

    var displayVersion: String {
        releaseLabel.isEmpty ? version : releaseLabel
    }
}

enum TerentoAppUpdateResult: Equatable, Sendable {
    case latest
    case available(TerentoAppUpdateManifest)
}

enum TerentoAppUpdateError: LocalizedError, Equatable, Sendable {
    case unavailable
    case invalidResponse
    case invalidManifest(String)
    case invalidDownloadURL

    var errorDescription: String? {
        switch self {
        case .unavailable:
            return "The update service is unavailable. Try again later."
        case .invalidResponse:
            return "The update service returned an invalid response."
        case let .invalidManifest(reason):
            return "The update information is invalid: \(reason)"
        case .invalidDownloadURL:
            return "The update download link is not trusted."
        }
    }
}

struct TerentoAppUpdateService: Sendable {
    static let defaultManifestURL = URL(
        string: "https://terento.app/updates/macos-arm64.json"
    )!

    private static let trustedHosts: Set<String> = [
        "terento.app",
        "www.terento.app",
        "api.terento.app",
        "github.com",
        "objects.githubusercontent.com"
    ]

    let manifestURL: URL

    init(manifestURL: URL = TerentoAppUpdateService.defaultManifestURL) {
        self.manifestURL = manifestURL
    }

    func check(
        current: TerentoInstalledVersion = .current()
    ) async throws -> TerentoAppUpdateResult {
        guard isTrustedURL(manifestURL) else {
            throw TerentoAppUpdateError.invalidManifest("The manifest URL is not trusted.")
        }

        var request = URLRequest(url: manifestURL)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = 15

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch {
            throw TerentoAppUpdateError.unavailable
        }

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw TerentoAppUpdateError.unavailable
        }

        let manifest: TerentoAppUpdateManifest
        do {
            manifest = try JSONDecoder().decode(TerentoAppUpdateManifest.self, from: data)
        } catch {
            throw TerentoAppUpdateError.invalidResponse
        }

        try validate(manifest)
        return try Self.evaluate(manifest: manifest, current: current)
    }

    static func evaluate(
        manifest: TerentoAppUpdateManifest,
        current: TerentoInstalledVersion
    ) throws -> TerentoAppUpdateResult {
        guard let remoteVersion = ReleaseVersion(manifest.version),
              let installedVersion = ReleaseVersion(current.version) else {
            throw TerentoAppUpdateError.invalidManifest(
                "The release version is not semantic versioning."
            )
        }

        if remoteVersion > installedVersion
            || (remoteVersion == installedVersion && manifest.build > current.build) {
            return .available(manifest)
        }
        return .latest
    }

    private func validate(_ manifest: TerentoAppUpdateManifest) throws {
        guard manifest.schemaVersion == 1,
              manifest.product == "Terento",
              manifest.platform == "macOS",
              manifest.architecture == "arm64",
              manifest.build > 0,
              !manifest.releaseLabel.isEmpty else {
            throw TerentoAppUpdateError.invalidManifest("Unsupported product metadata.")
        }

        guard ReleaseVersion(manifest.version) != nil else {
            throw TerentoAppUpdateError.invalidManifest(
                "The release version is not semantic versioning."
            )
        }

        guard isTrustedURL(manifest.downloadURL),
              isTrustedURL(manifest.releaseURL) else {
            throw TerentoAppUpdateError.invalidDownloadURL
        }

        if let sha256 = manifest.sha256,
           !sha256.isEmpty,
           (sha256.count != 64 || sha256.contains(where: { !$0.isHexDigit })) {
            throw TerentoAppUpdateError.invalidManifest("The checksum is invalid.")
        }
    }

    private func isTrustedURL(_ url: URL) -> Bool {
        url.scheme?.lowercased() == "https"
            && url.host.map { Self.trustedHosts.contains($0.lowercased()) } == true
    }
}

private struct ReleaseVersion: Comparable, Sendable {
    let major: Int
    let minor: Int
    let patch: Int

    init?(_ rawValue: String) {
        let parts = rawValue
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count >= 3,
              let major = Int(parts[0]),
              let minor = Int(parts[1]),
              let patch = Int(parts[2].split(separator: "-", maxSplits: 1)[0]),
              major >= 0,
              minor >= 0,
              patch >= 0 else {
            return nil
        }
        self.major = major
        self.minor = minor
        self.patch = patch
    }

    static func < (lhs: ReleaseVersion, rhs: ReleaseVersion) -> Bool {
        (lhs.major, lhs.minor, lhs.patch) < (rhs.major, rhs.minor, rhs.patch)
    }
}
