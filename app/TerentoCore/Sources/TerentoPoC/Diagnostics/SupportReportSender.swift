import Combine
import Foundation

enum SupportReportUploadResult: Equatable, Sendable {
    /// 201 stored or 200 duplicate (replay of the same id).
    case accepted(reference: String)
    /// 409: another report owns this reference; send again with a new id.
    case referenceConflict
    /// 429 rate limit, 503 or a network failure: keep it and offer Try again.
    case retryLater
    /// 400/413/415: the server will not accept this report.
    case rejected(status: Int)
}

protocol SupportReportUploading: Sendable {
    func upload(_ payload: SupportReportPayload) async -> SupportReportUploadResult
}

struct HTTPSupportReportUploader: SupportReportUploading {
    let endpoint: URL
    let session: URLSession

    init(endpoint: URL = URL(string: "https://api.terento.app/support/reports")!, session: URLSession = .shared) {
        self.endpoint = endpoint
        self.session = session
    }

    func upload(_ payload: SupportReportPayload) async -> SupportReportUploadResult {
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.timeoutInterval = 20
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        guard let body = try? payload.encoded(), body.count <= 64 * 1024 else { return .rejected(status: 413) }
        request.httpBody = body
        guard let (data, response) = try? await session.data(for: request),
              let http = response as? HTTPURLResponse else { return .retryLater }
        return Self.result(statusCode: http.statusCode, body: data)
    }

    static func result(statusCode: Int, body: Data) -> SupportReportUploadResult {
        switch statusCode {
        case 200, 201:
            struct Accepted: Decodable { let reference: String }
            guard let accepted = try? JSONDecoder().decode(Accepted.self, from: body),
                  accepted.reference.range(of: "^TR-[A-Z2-7]{6}$", options: .regularExpression) != nil
            else { return .retryLater }
            return .accepted(reference: accepted.reference)
        case 409: return .referenceConflict
        case 429, 500...599: return .retryLater
        default: return .rejected(status: statusCode)
        }
    }
}

/// Unsent reports stay on this Mac (one file, private, writable while the
/// screen is locked) until they are sent or replaced by a newer report.
struct SupportReportOutbox {
    let fileURL: URL

    init(rootURL: URL? = nil) {
        let root = rootURL ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)
            .first!.appendingPathComponent("Terento", isDirectory: true)
        fileURL = root.appendingPathComponent("support-report-unsent.json")
    }

    func load() -> SupportReportPayload? {
        guard let data = try? Data(contentsOf: fileURL) else { return nil }
        return try? JSONDecoder().decode(SupportReportPayload.self, from: data)
    }

    func save(_ payload: SupportReportPayload) {
        guard let data = try? payload.encoded() else { return }
        try? FileManager.default.createDirectory(at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? data.write(to: fileURL, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        try? FileManager.default.setAttributes([.posixPermissions: NSNumber(value: 0o600)], ofItemAtPath: fileURL.path)
    }

    func clear() {
        try? FileManager.default.removeItem(at: fileURL)
    }
}

/// Drives one explicit send from the review sheet. Nothing is sent without
/// `send()`, and the automatic sharing preferences are never consulted.
@MainActor
final class SupportReportController: ObservableObject {
    enum State: Equatable {
        case editing
        case sending
        case sent(reference: String)
        case failed(message: String)
    }

    static let maximumDescriptionLength = 2000

    @Published private(set) var state: State = .editing
    @Published var userMessage = "" {
        didSet {
            if userMessage.unicodeScalars.count > Self.maximumDescriptionLength {
                userMessage = SupportReportText.bounded(userMessage, max: Self.maximumDescriptionLength)
            }
        }
    }
    @Published var category: SupportReportCategory
    let allowsCategoryChoice: Bool
    private var basePayload: SupportReportPayload
    private let uploader: any SupportReportUploading
    private let outbox: SupportReportOutbox

    init(payload: SupportReportPayload, allowsCategoryChoice: Bool = false,
         uploader: any SupportReportUploading = HTTPSupportReportUploader(),
         outbox: SupportReportOutbox = SupportReportOutbox()) {
        basePayload = payload
        category = payload.category
        userMessage = payload.userMessage ?? ""
        self.allowsCategoryChoice = allowsCategoryChoice
        self.uploader = uploader
        self.outbox = outbox
    }

    /// The exact payload Send uploads, including the current description.
    var payload: SupportReportPayload {
        SupportReportPayload(id: UUID(uuidString: basePayload.id) ?? UUID(),
                             createdAt: Self.date(basePayload.createdAt), appBuild: basePayload.appBuild,
                             releaseLabel: basePayload.releaseLabel, category: category,
                             operationID: basePayload.operationId.flatMap(UUID.init(uuidString:)),
                             userMessage: userMessage, report: basePayload.report)
    }

    var canSend: Bool { state == .editing || isFailed }
    var isFailed: Bool { if case .failed = state { return true }; return false }

    func send() async {
        guard canSend else { return }
        state = .sending
        var current = payload
        var result = await uploader.upload(current)
        if result == .referenceConflict {
            current = current.withNewID()
            basePayload = current
            result = await uploader.upload(current)
        }
        switch result {
        case .accepted(let reference):
            outbox.clear()
            state = .sent(reference: reference)
        case .retryLater, .referenceConflict:
            // The same id is resent by Try again; the server de-duplicates it.
            basePayload = current
            outbox.save(current)
            state = .failed(message: "Couldn't send the report right now. It's kept on this Mac. Try again later.")
        case .rejected:
            outbox.save(current)
            state = .failed(message: "Terento couldn't accept this report. It's kept on this Mac; you can still report the issue on GitHub.")
        }
    }

    private static func date(_ value: String) -> Date {
        ISO8601DateFormatter().date(from: value) ?? Date()
    }
}
