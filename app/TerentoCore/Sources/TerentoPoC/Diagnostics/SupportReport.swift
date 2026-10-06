import CryptoKit
import Foundation

/// Support report sent to Terento (`POST /support/reports`, schema v1; meaning
/// owned by contracts/SUPPORT_REPORT_CONTRACT.md). It is the structured form of
/// the sanitised GitHub issue report and is sent only after the user reviews it
/// and presses Send. It is independent of the automatic sharing toggles and
/// carries no serial, Unit ID, account, local path, raw log or file content.
enum SupportReportCategory: String, Codable, CaseIterable, Sendable {
    case installFailed = "INSTALL_FAILED"
    case updateFailed = "UPDATE_FAILED"
    case removeFailed = "REMOVE_FAILED"
    case connection = "CONNECTION"
    case other = "OTHER"

    init(operation: DiagnosticMapOperation) {
        switch operation {
        case .installation: self = .installFailed
        case .update: self = .updateFailed
        case .removal: self = .removeFailed
        }
    }
}

struct SupportReportDevice: Codable, Equatable, Sendable {
    var model: String?
    var variant: String?
    var family: String?
    var firmware: String?
    var mtpModel: String?

    var isEmpty: Bool { [model, variant, family, firmware, mtpModel].allSatisfy { $0 == nil } }
}

struct SupportReportMap: Codable, Equatable, Sendable {
    let provider: String
    var region: String?
    var package: String?
    var release: String?
    var plannedBytes: UInt64?
}

struct SupportReportVerification: Codable, Equatable, Sendable {
    var originalFailure: String?
    var cleanupFailure: String?
    var transportClassification: String?
    var failedComponent: String?
    var sourceBytes: UInt64?
    var remoteBytes: UInt64?
    var transferredBytes: UInt64?
    var elapsedMilliseconds: UInt64?
    var sampledBytes: UInt64?
    var sampleCount: Int?
    var matchedSampleCount: Int?

    var isEmpty: Bool { self == SupportReportVerification() }
}

/// The closed `report` object. Unknown values are omitted, never "Unavailable".
struct SupportReportBody: Codable, Equatable, Sendable {
    enum Operation: String, Codable, Sendable {
        case installation = "INSTALLATION"
        case update = "UPDATE"
        case removal = "REMOVAL"
    }

    var macOSVersion: String
    var title: String?
    var operation: Operation?
    var stage: String?
    var failureStages: [String]?
    var errorCategory: String?
    var errorCodes: [String]?
    var message: String?
    var device: SupportReportDevice?
    var maps: [SupportReportMap]?
    var writeStarted: Bool?
    var objectCreated: Bool?
    var cleanupAttempted: Bool?
    var cleanupSucceeded: Bool?
    var transferProgressPercent: Int?
    var verification: SupportReportVerification?
    var lifecycleFacts: [String]?
    var failureContext: InstallationFailureContext?
    var originalFailureContext: InstallationFailureContext?
    var finishingTrace: [String]?

    static func minimal(macOSVersion: String = ProcessInfo.processInfo.operatingSystemVersionString) -> Self {
        SupportReportBody(macOSVersion: SupportReportText.clean(macOSVersion, max: 120) ?? "macOS")
    }
}

struct SupportReportPayload: Codable, Equatable, Identifiable, Sendable {
    static let schemaVersion = 1

    let schemaVersion: Int
    let id: String
    let createdAt: String
    let appBuild: String
    let releaseLabel: String
    let category: SupportReportCategory
    let operationId: String?
    let userMessage: String?
    let report: SupportReportBody

    init(id: UUID = UUID(), createdAt: Date = Date(), appBuild: String = TerentoTelemetryMetadata.eventBuild,
         releaseLabel: String = TerentoTelemetryMetadata.releaseLabel, category: SupportReportCategory,
         operationID: UUID?, userMessage: String?, report: SupportReportBody) {
        schemaVersion = Self.schemaVersion
        self.id = id.uuidString.lowercased()
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        self.createdAt = formatter.string(from: createdAt)
        self.appBuild = SupportReportText.clean(appBuild, max: 80) ?? "local"
        self.releaseLabel = releaseLabel
        self.category = category
        self.operationId = operationID?.uuidString.lowercased()
        self.userMessage = SupportReportText.userMessage(userMessage)
        self.report = report
    }

    /// The same report under a new id (after a reference conflict).
    func withNewID(_ id: UUID = UUID()) -> SupportReportPayload {
        SupportReportPayload(id: id, createdAt: Date(), appBuild: appBuild, releaseLabel: releaseLabel,
                             category: category, operationID: operationId.flatMap(UUID.init(uuidString:)),
                             userMessage: userMessage, report: report)
    }

    func withUserMessage(_ message: String?) -> SupportReportPayload {
        SupportReportPayload(id: UUID(uuidString: id) ?? UUID(), createdAt: Date(), appBuild: appBuild,
                             releaseLabel: releaseLabel, category: category,
                             operationID: operationId.flatMap(UUID.init(uuidString:)),
                             userMessage: message, report: report)
    }

    var reference: String { SupportReportReference.make(id: id) }

    func encoded(pretty: Bool = false) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = pretty ? [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes] : [.sortedKeys]
        return try encoder.encode(self)
    }

    /// Exactly the JSON that Send uploads, for the review sheet.
    var previewText: String {
        (try? encoded(pretty: true)).flatMap { String(data: $0, encoding: .utf8) } ?? ""
    }
}

/// "TR-" + the first six RFC 4648 base32 characters of SHA-256(lowercase id).
enum SupportReportReference {
    private static let alphabet = Array("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")

    static func make(id: String) -> String {
        let digest = Array(SHA256.hash(data: Data(id.lowercased().utf8)))
        // Six characters need 30 bits: the first four bytes.
        let bits = digest.prefix(4).reduce(UInt64(0)) { ($0 << 8) | UInt64($1) }
        let characters = (0..<6).map { index -> Character in
            alphabet[Int((bits >> UInt64(32 - 5 * (index + 1))) & 0x1F)]
        }
        return "TR-" + String(characters)
    }
}

/// Text rules of the contract: sanitised, no control characters or local path
/// markers, trimmed, bounded in Unicode scalars; unknown values are omitted.
enum SupportReportText {
    static let pathMarkers = ["/users/", "file://", "/private/", "/volumes/", "\\users\\"]
    static let codePattern = try! NSRegularExpression(pattern: "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
    static let tracePattern = try! NSRegularExpression(pattern:
        "^FINISH_TRACE (swift|native)( [a-z][a-z0-9_]{0,39}=[A-Za-z0-9_.-]{0,80})*( event=[A-Za-z0-9_.-]{1,80})( [a-z][a-z0-9_]{0,39}=[A-Za-z0-9_.-]{0,80})*$")

    static func clean(_ value: String?, max: Int) -> String? {
        guard let value else { return nil }
        let sanitized = redactMarkers(DiagnosticReportSanitizer.sanitize(value))
        let scalars = sanitized.unicodeScalars.map { scalar -> Character in
            CharacterSet.controlCharacters.contains(scalar) || scalar.value == 0x7F ? " " : Character(scalar)
        }
        let text = bounded(String(scalars).trimmingCharacters(in: .whitespacesAndNewlines), max: max)
        guard !text.isEmpty, text.caseInsensitiveCompare("Unavailable") != .orderedSame else { return nil }
        return text
    }

    /// The optional description: newlines and tabs are kept, at most 2000
    /// Unicode scalars, `nil` when empty.
    static func userMessage(_ value: String?) -> String? {
        guard let value else { return nil }
        let sanitized = redactMarkers(DiagnosticReportSanitizer.sanitize(value))
        let scalars = sanitized.unicodeScalars.compactMap { scalar -> Character? in
            if scalar == "\n" || scalar == "\t" { return Character(scalar) }
            if scalar == "\r" { return nil }
            return CharacterSet.controlCharacters.contains(scalar) || scalar.value == 0x7F ? nil : Character(scalar)
        }
        let text = bounded(String(scalars), max: 2000)
        return text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : text
    }

    static func code(_ value: String?) -> String? {
        guard let value else { return nil }
        let range = NSRange(value.startIndex..., in: value)
        return codePattern.firstMatch(in: value, range: range) == nil ? nil : value
    }

    static func traceLines(_ report: String) -> [String]? {
        let lines = report.components(separatedBy: "\n").compactMap { line -> String? in
            guard line.unicodeScalars.count <= 300 else { return nil }
            let range = NSRange(line.startIndex..., in: line)
            return tracePattern.firstMatch(in: line, range: range) == nil ? nil : line
        }
        return lines.isEmpty ? nil : Array(lines.suffix(64))
    }

    static func bounded(_ value: String, max: Int) -> String {
        guard value.unicodeScalars.count > max else { return value }
        var view = String.UnicodeScalarView()
        view.append(contentsOf: value.unicodeScalars.prefix(max))
        return String(view).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func redactMarkers(_ value: String) -> String {
        var result = value
        for marker in pathMarkers {
            result = result.replacingOccurrences(of: marker, with: "[LOCAL PATH REDACTED]",
                                                 options: .caseInsensitive)
        }
        return result
    }
}

extension SupportReportBody {
    /// Builds the structured report from the same inputs as the GitHub issue
    /// report, with the same sanitising and omissions.
    static func make(
        title: String,
        identity: DeviceIdentity?,
        maps: [InstallationIssueMap],
        stage: String,
        operation: DiagnosticMapOperation,
        lifecycleFacts: [String],
        error: String?,
        failureStages: [String],
        errorCategory: String?,
        errorCodes: [String],
        writeStarted: Bool,
        transferProgressPercent: Int,
        remoteObjectCreated: Bool,
        cleanupAttempted: Bool,
        cleanupSucceeded: Bool,
        verification: InstallationIssueVerification,
        failureContext: InstallationFailureContext?,
        originalFailureContext: InstallationFailureContext?,
        finishingTrace: String,
        operatingSystem: String
    ) -> SupportReportBody {
        var body = SupportReportBody.minimal(macOSVersion: operatingSystem)
        body.title = SupportReportText.clean(title, max: 180)
        switch operation {
        case .installation: body.operation = .installation
        case .update: body.operation = .update
        case .removal: body.operation = .removal
        }
        body.stage = SupportReportText.clean(stage, max: 120)
        let stages = failureStages.compactMap { SupportReportText.clean($0, max: 120) }.prefix(8)
        body.failureStages = stages.isEmpty ? nil : Array(stages)
        body.errorCategory = SupportReportText.clean(errorCategory, max: 80)
        var seenCodes = Set<String>()
        let codes = errorCodes.compactMap(SupportReportText.code).filter { seenCodes.insert($0).inserted }
        body.errorCodes = codes.isEmpty ? nil : Array(codes.prefix(8))
        body.message = SupportReportText.clean(error, max: 500)
        if let identity {
            let device = SupportReportDevice(
                model: SupportReportText.clean(identity.presentationModel, max: 120),
                variant: SupportReportText.clean(identity.variant, max: 120),
                family: SupportReportText.clean(identity.family, max: 120),
                firmware: SupportReportText.clean(identity.firmware, max: 40),
                mtpModel: SupportReportText.clean(identity.model, max: 120))
            body.device = device.isEmpty ? nil : device
        }
        let reportedMaps = maps.prefix(8).compactMap { map -> SupportReportMap? in
            guard let provider = SupportReportText.clean(map.provider, max: 80) else { return nil }
            return SupportReportMap(provider: provider,
                                    region: SupportReportText.clean(map.region, max: 200),
                                    package: SupportReportText.clean(map.package, max: 200),
                                    release: SupportReportText.clean(map.release, max: 80),
                                    plannedBytes: map.artifactSizeBytes.flatMap { $0 <= maximumInteger ? $0 : nil })
        }
        body.maps = reportedMaps.isEmpty ? nil : reportedMaps
        // The GitHub report states these only for installations.
        if operation == .installation {
            body.writeStarted = writeStarted
            body.objectCreated = remoteObjectCreated
            body.cleanupAttempted = cleanupAttempted
            body.cleanupSucceeded = cleanupSucceeded
            body.transferProgressPercent = min(100, max(0, transferProgressPercent))
        }
        let checks = SupportReportVerification(
            originalFailure: SupportReportText.code(verification.originalFailure),
            cleanupFailure: SupportReportText.code(verification.cleanupFailure),
            transportClassification: SupportReportText.code(verification.transportClassification),
            failedComponent: SupportReportText.code(verification.artifactKind),
            sourceBytes: bounded(verification.sourceSize),
            remoteBytes: bounded(verification.remoteSize),
            transferredBytes: bounded(verification.transferredBytes),
            elapsedMilliseconds: bounded(verification.elapsedMilliseconds),
            sampledBytes: bounded(verification.sampledBytes),
            sampleCount: verification.sampleCount.flatMap { (0...Int(Int32.max)).contains($0) ? $0 : nil },
            matchedSampleCount: verification.matchedSampleCount.flatMap { (0...Int(Int32.max)).contains($0) ? $0 : nil })
        body.verification = checks.isEmpty ? nil : checks
        let facts = lifecycleFacts.compactMap { SupportReportText.clean($0, max: 500) }.prefix(16)
        body.lifecycleFacts = facts.isEmpty ? nil : Array(facts)
        body.failureContext = failureContext
        body.originalFailureContext = originalFailureContext
        body.finishingTrace = SupportReportText.traceLines(finishingTrace)
        return body
    }

    static let maximumInteger: UInt64 = (1 << 53) - 1

    private static func bounded(_ value: UInt64?) -> UInt64? {
        value.flatMap { $0 <= maximumInteger ? $0 : nil }
    }
}

/// What a saved failure report adds for "Send report to Terento": the
/// structured report and the ids of the failed operation, kept beside
/// failure-report.md.
struct SavedSupportReport: Codable, Equatable, Sendable {
    let title: String
    let category: SupportReportCategory
    let operationID: UUID?
    let report: SupportReportBody
}
