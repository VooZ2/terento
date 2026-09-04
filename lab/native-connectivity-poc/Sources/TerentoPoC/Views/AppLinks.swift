import AppKit
import Combine
import Foundation

enum TerentoAppLinks {
    static let website = URL(string: "https://terento.app")!
    static let documentation = URL(string: "https://github.com/VooZ2/terento#readme")!
    static let issues = URL(string: "https://github.com/VooZ2/terento/issues")!
    static let repository = URL(string: "https://github.com/VooZ2/terento")!
    static let donate = URL(string: "https://buymeacoffee.com/vooz2")!
    static let privacy = URL(string: "https://terento.app/privacy/")!
    static let legal = URL(string: "https://terento.app/legal/")!

    // The public site already preserves and reports UTM campaign parameters.
    // Keep app-originated web visits distinguishable without adding analytics
    // or a tracking identifier to the native app.
    private static let appReferralQuery =
        "utm_source=terento_app&utm_medium=referral&utm_campaign=app_about"
    static let websiteFromApp = URL(string: "https://terento.app/?\(appReferralQuery)")!
    static let privacyFromApp = URL(string: "https://terento.app/privacy/?\(appReferralQuery)")!
    static let legalFromApp = URL(string: "https://terento.app/legal/?\(appReferralQuery)")!
}

enum TerentoUpdateChannel: String, Codable, Equatable, Sendable {
    case beta
    case stable
}

struct TerentoInstalledVersion: Equatable, Sendable {
    let version: String
    let build: Int
    let channel: TerentoUpdateChannel

    init(
        version: String,
        build: Int,
        channel: TerentoUpdateChannel = .beta
    ) {
        self.version = version
        self.build = build
        self.channel = channel
    }

    static func current(bundle: Bundle = .main) -> TerentoInstalledVersion {
        let version = bundle.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
            ?? TerentoAppMetadata.version
        let build = Int(
            (bundle.object(forInfoDictionaryKey: "CFBundleVersion") as? String)
                ?? TerentoAppMetadata.build
        ) ?? 0
        let channel = TerentoUpdateChannel(
            rawValue: (bundle.object(forInfoDictionaryKey: "TerentoReleaseChannel") as? String)
                ?? "beta"
        ) ?? .beta
        return TerentoInstalledVersion(version: version, build: build, channel: channel)
    }
}

struct TerentoAppUpdateManifest: Codable, Equatable, Sendable, Identifiable {
    let schemaVersion: Int
    let product: String
    let platform: String
    let architecture: String
    let version: String
    let build: Int
    let releaseLabel: String
    let downloadURL: URL
    let releaseURL: URL
    let releaseNotesURL: URL?
    let summary: String?
    let publishedAt: String?
    let channel: TerentoUpdateChannel
    let sha256: String?
    let minimumMacOS: String?

    init(
        schemaVersion: Int,
        product: String,
        platform: String,
        architecture: String,
        version: String,
        build: Int,
        releaseLabel: String,
        downloadURL: URL,
        releaseURL: URL,
        releaseNotesURL: URL? = nil,
        summary: String? = nil,
        publishedAt: String? = nil,
        channel: TerentoUpdateChannel = .beta,
        sha256: String?,
        minimumMacOS: String?
    ) {
        self.schemaVersion = schemaVersion
        self.product = product
        self.platform = platform
        self.architecture = architecture
        self.version = version
        self.build = build
        self.releaseLabel = releaseLabel
        self.downloadURL = downloadURL
        self.releaseURL = releaseURL
        self.releaseNotesURL = releaseNotesURL
        self.summary = summary
        self.publishedAt = publishedAt
        self.channel = channel
        self.sha256 = sha256
        self.minimumMacOS = minimumMacOS
    }

    var id: String {
        "\(version)-\(build)-\(downloadURL.absoluteString)"
    }

    var displayVersion: String {
        releaseLabel.isEmpty ? version : releaseLabel
    }
}

extension TerentoAppUpdateManifest {
    private enum CodingKeys: String, CodingKey {
        case schemaVersion
        case product
        case platform
        case architecture
        case version
        case build
        case releaseLabel
        case downloadURL
        case releaseURL
        case releaseNotesURL
        case summary
        case publishedAt
        case channel
        case sha256
        case minimumMacOS
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            schemaVersion: try container.decode(Int.self, forKey: .schemaVersion),
            product: try container.decode(String.self, forKey: .product),
            platform: try container.decode(String.self, forKey: .platform),
            architecture: try container.decode(String.self, forKey: .architecture),
            version: try container.decode(String.self, forKey: .version),
            build: try container.decode(Int.self, forKey: .build),
            releaseLabel: try container.decode(String.self, forKey: .releaseLabel),
            downloadURL: try container.decode(URL.self, forKey: .downloadURL),
            releaseURL: try container.decode(URL.self, forKey: .releaseURL),
            releaseNotesURL: try container.decodeIfPresent(URL.self, forKey: .releaseNotesURL),
            summary: try container.decodeIfPresent(String.self, forKey: .summary),
            publishedAt: try container.decodeIfPresent(String.self, forKey: .publishedAt),
            channel: try container.decodeIfPresent(TerentoUpdateChannel.self, forKey: .channel)
                ?? .beta,
            sha256: try container.decodeIfPresent(String.self, forKey: .sha256),
            minimumMacOS: try container.decodeIfPresent(String.self, forKey: .minimumMacOS)
        )
    }
}

enum TerentoAppUpdateResult: Equatable, Sendable {
    case upToDate
    case available(TerentoAppUpdateManifest)
    case incompatible(TerentoAppUpdateManifest)
}

enum TerentoAppUpdateState: Equatable, Sendable {
    case idle
    case checking
    case upToDate
    case available(TerentoAppUpdateManifest)
    case incompatible(TerentoAppUpdateManifest)
    case failed(String)
}

enum TerentoAppUpdateError: LocalizedError, Equatable, Sendable {
    case unavailable
    case invalidResponse
    case invalidManifest(String)
    case invalidDownloadURL
    case invalidReleaseNotesURL

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
        case .invalidReleaseNotesURL:
            return "The release notes link is not trusted."
        }
    }
}

struct TerentoAppUpdateService: Sendable {
    static let defaultManifestURL = URL(
        string: "https://terento.app/updates/macos-arm64.json"
    )!

    private static let trustedWebsiteHosts: Set<String> = [
        "terento.app",
        "www.terento.app"
    ]
    private static let trustedGitHubHost = "github.com"
    private static let trustedGitHubOwner = "VooZ2"
    private static let trustedGitHubRepository = "terento"

    let manifestURL: URL

    init(manifestURL: URL = TerentoAppUpdateService.defaultManifestURL) {
        self.manifestURL = manifestURL
    }

    func check(
        current: TerentoInstalledVersion = .current(),
        currentMacOSVersion: String = Self.currentMacOSVersion
    ) async throws -> TerentoAppUpdateResult {
        guard Self.isTrustedManifestURL(manifestURL) else {
            throw TerentoAppUpdateError.invalidManifest("The manifest URL is not trusted.")
        }

        var request = URLRequest(url: manifestURL)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = 8

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

        try Self.validate(manifest: manifest)
        return try Self.evaluate(
            manifest: manifest,
            current: current,
            currentMacOSVersion: currentMacOSVersion
        )
    }

    static func evaluate(
        manifest: TerentoAppUpdateManifest,
        current: TerentoInstalledVersion,
        currentMacOSVersion: String = Self.currentMacOSVersion
    ) throws -> TerentoAppUpdateResult {
        try validate(manifest: manifest)

        guard let remoteVersion = ReleaseVersion(manifest.version),
              let installedVersion = ReleaseVersion(current.version) else {
            throw TerentoAppUpdateError.invalidManifest(
                "The release version is not semantic versioning."
            )
        }

        let isEligibleChannel = manifest.channel == current.channel
            || (current.channel == .beta && manifest.channel == .stable)
        guard isEligibleChannel else {
            return .upToDate
        }

        guard remoteVersion > installedVersion
                || (remoteVersion == installedVersion && manifest.build > current.build) else {
            return .upToDate
        }

        guard let minimumMacOS = manifest.minimumMacOS else {
            return .available(manifest)
        }

        guard let requiredVersion = PlatformVersion(minimumMacOS),
              let installedMacOSVersion = PlatformVersion(currentMacOSVersion) else {
            throw TerentoAppUpdateError.invalidManifest(
                "The minimum macOS version is invalid."
            )
        }

        return installedMacOSVersion < requiredVersion
            ? .incompatible(manifest)
            : .available(manifest)
    }

    static func validate(manifest: TerentoAppUpdateManifest) throws {
        guard manifest.schemaVersion == 1,
              manifest.product == "Terento",
              manifest.platform == "macOS",
              manifest.architecture == "arm64",
              manifest.build > 0,
              !manifest.releaseLabel.isEmpty,
              isPlainText(manifest.releaseLabel, maximumLength: 160) else {
            throw TerentoAppUpdateError.invalidManifest("Unsupported product metadata.")
        }

        guard ReleaseVersion(manifest.version) != nil else {
            throw TerentoAppUpdateError.invalidManifest(
                "The release version is not semantic versioning."
            )
        }

        guard isTrustedDownloadURL(manifest.downloadURL) else {
            throw TerentoAppUpdateError.invalidDownloadURL
        }

        guard isTrustedReleaseURL(manifest.releaseURL) else {
            throw TerentoAppUpdateError.invalidReleaseNotesURL
        }

        if let releaseNotesURL = manifest.releaseNotesURL,
           !isTrustedReleaseNotesURL(releaseNotesURL) {
            throw TerentoAppUpdateError.invalidReleaseNotesURL
        }

        if let summary = manifest.summary,
           !summary.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
           !isPlainText(summary, maximumLength: 240) {
            throw TerentoAppUpdateError.invalidManifest("The release summary is invalid.")
        }

        if let minimumMacOS = manifest.minimumMacOS,
           PlatformVersion(minimumMacOS) == nil {
            throw TerentoAppUpdateError.invalidManifest(
                "The minimum macOS version is invalid."
            )
        }

        if let sha256 = manifest.sha256,
           !sha256.isEmpty,
           (sha256.count != 64 || sha256.contains(where: { !$0.isHexDigit })) {
            throw TerentoAppUpdateError.invalidManifest("The checksum is invalid.")
        }
    }

    static func isTrustedDownloadURL(_ url: URL) -> Bool {
        guard isHTTPSURL(url),
              url.host?.lowercased() == trustedGitHubHost,
              url.user == nil,
              url.password == nil,
              url.port == nil || url.port == 443 else {
            return false
        }

        let components = normalizedPathComponents(url)
        guard components.count == 6,
              components[0] == trustedGitHubOwner.lowercased(),
              components[1] == trustedGitHubRepository,
              components[2] == "releases",
              components[3] == "download",
              !components[4].isEmpty else {
            return false
        }

        return components[5].lowercased().hasSuffix(".dmg")
    }

    static func isTrustedReleaseNotesURL(_ url: URL) -> Bool {
        guard isHTTPSURL(url),
              url.user == nil,
              url.password == nil,
              url.port == nil || url.port == 443 else {
            return false
        }

        if url.host?.lowercased() == trustedGitHubHost {
            let components = normalizedPathComponents(url)
            return components.count == 5
                && components[0] == trustedGitHubOwner.lowercased()
                && components[1] == trustedGitHubRepository
                && components[2] == "releases"
                && components[3] == "tag"
                && !components[4].isEmpty
        }

        guard trustedWebsiteHosts.contains(url.host?.lowercased() ?? "") else {
            return false
        }

        let path = url.path.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        return path == "releases"
            || path == "release-notes"
            || path == "changelog"
            || path.hasPrefix("releases/")
            || path.hasPrefix("release-notes/")
            || path.hasPrefix("changelog/")
    }

    static func isCompatibleWithCurrentMacOS(
        minimumMacOS: String?,
        currentMacOSVersion: String = Self.currentMacOSVersion
    ) -> Bool {
        guard let minimumMacOS else { return true }
        guard let requiredVersion = PlatformVersion(minimumMacOS),
              let installedVersion = PlatformVersion(currentMacOSVersion) else {
            return false
        }
        return installedVersion >= requiredVersion
    }

    private static func isTrustedManifestURL(_ url: URL) -> Bool {
        isHTTPSURL(url)
            && trustedWebsiteHosts.contains(url.host?.lowercased() ?? "")
            && url.path == "/updates/macos-arm64.json"
            && url.user == nil
            && url.password == nil
            && (url.port == nil || url.port == 443)
    }

    private static func isTrustedReleaseURL(_ url: URL) -> Bool {
        isTrustedReleaseNotesURL(url)
    }

    private static func isHTTPSURL(_ url: URL) -> Bool {
        url.scheme?.lowercased() == "https"
    }

    private static func normalizedPathComponents(_ url: URL) -> [String] {
        url.path.split(separator: "/", omittingEmptySubsequences: true)
            .map { $0.lowercased() }
    }

    private static func isPlainText(_ value: String, maximumLength: Int) -> Bool {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed.count <= maximumLength else { return false }
        return !trimmed.contains("<")
            && !trimmed.contains(">")
            && !trimmed.unicodeScalars.contains(where: CharacterSet.controlCharacters.contains)
    }

    private static var currentMacOSVersion: String {
        let version = ProcessInfo.processInfo.operatingSystemVersion
        return "\(version.majorVersion).\(version.minorVersion).\(version.patchVersion)"
    }
}

@MainActor
final class AppUpdateController: ObservableObject {
    typealias CheckOperation = @Sendable (
        TerentoInstalledVersion
    ) async throws -> TerentoAppUpdateResult

    @Published private(set) var state: TerentoAppUpdateState = .idle

    private let currentVersionProvider: @Sendable () -> TerentoInstalledVersion
    private let checkOperation: CheckOperation
    private var activeCheckTask: Task<Void, Never>?
    private var automaticCheckStarted = false
    private var deferredPromptKey: String?
    private var claimedPromptKey: String?

    init(
        currentVersionProvider: @escaping @Sendable () -> TerentoInstalledVersion = {
            .current()
        },
        checkOperation: @escaping CheckOperation = { current in
            try await TerentoAppUpdateService().check(current: current)
        }
    ) {
        self.currentVersionProvider = currentVersionProvider
        self.checkOperation = checkOperation
    }

    var isChecking: Bool {
        if case .checking = state { return true }
        return false
    }

    func startAutomaticCheck() {
        guard !automaticCheckStarted else { return }
        automaticCheckStarted = true
        runCheck(isManual: false)
    }

    func checkForUpdates() {
        guard activeCheckTask == nil else { return }
        runCheck(isManual: true)
    }

    func claimPromptIfSafe(_ isSafe: Bool) -> TerentoAppUpdateManifest? {
        guard isSafe,
              case let .available(update) = state,
              deferredPromptKey != update.id,
              claimedPromptKey != update.id else {
            return nil
        }

        claimedPromptKey = update.id
        return update
    }

    func deferPrompt(for update: TerentoAppUpdateManifest) {
        deferredPromptKey = update.id
        claimedPromptKey = nil
    }

    func openDownload(for update: TerentoAppUpdateManifest) -> Bool {
        guard Self.validateDownloadURL(update.downloadURL) else {
            state = .failed(TerentoAppUpdateError.invalidDownloadURL.localizedDescription)
            return false
        }
        guard TerentoAppUpdateService.isCompatibleWithCurrentMacOS(
            minimumMacOS: update.minimumMacOS
        ) else {
            state = .incompatible(update)
            return false
        }
        guard NSWorkspace.shared.open(update.downloadURL) else {
            state = .failed("The update download could not be opened. Try again later.")
            return false
        }
        return true
    }

    func openReleaseNotes(for update: TerentoAppUpdateManifest) -> Bool {
        guard let releaseNotesURL = update.releaseNotesURL,
              Self.validateReleaseNotesURL(releaseNotesURL) else {
            return false
        }
        return NSWorkspace.shared.open(releaseNotesURL)
    }

    /// Test-only synchronization point used by the deterministic standalone
    /// update tests. Production callers do not wait for update checks.
    func waitForCurrentCheck() async {
        await activeCheckTask?.value
    }

    private func runCheck(isManual: Bool) {
        guard activeCheckTask == nil else { return }
        state = .checking

        let currentVersionProvider = self.currentVersionProvider
        let checkOperation = self.checkOperation
        activeCheckTask = Task { @MainActor [weak self] in
            do {
                let result = try await checkOperation(currentVersionProvider())
                guard let self, !Task.isCancelled else { return }
                self.apply(result)
            } catch {
                guard let self, !Task.isCancelled else { return }
                self.state = isManual
                    ? .failed(error.localizedDescription)
                    : .idle
            }
            self?.activeCheckTask = nil
        }
    }

    private func apply(_ result: TerentoAppUpdateResult) {
        switch result {
        case .upToDate:
            state = .upToDate
        case let .available(update):
            state = .available(update)
        case let .incompatible(update):
            state = .incompatible(update)
        }
    }

    private static func validateDownloadURL(_ url: URL) -> Bool {
        TerentoAppUpdateService.isTrustedDownloadURL(url)
    }

    private static func validateReleaseNotesURL(_ url: URL) -> Bool {
        TerentoAppUpdateService.isTrustedReleaseNotesURL(url)
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

private struct PlatformVersion: Comparable, Sendable {
    let components: [Int]

    init?(_ rawValue: String) {
        let parts = rawValue
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .split(separator: ".", omittingEmptySubsequences: false)
        guard (1...3).contains(parts.count),
              parts.allSatisfy({ part in
                  guard let value = Int(part) else { return false }
                  return value >= 0
              }) else {
            return nil
        }
        components = parts.map { Int($0)! }
    }

    static func < (lhs: PlatformVersion, rhs: PlatformVersion) -> Bool {
        let count = max(lhs.components.count, rhs.components.count)
        let left = lhs.components + Array(repeating: 0, count: count - lhs.components.count)
        let right = rhs.components + Array(repeating: 0, count: count - rhs.components.count)
        return left.lexicographicallyPrecedes(right)
    }
}
