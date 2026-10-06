import Foundation

// Whole-app test binaries have no SwiftPM resource bundle.
extension Bundle { static var module: Bundle { .main } }

private actor RecordingSupportUploader: SupportReportUploading {
    private var results: [SupportReportUploadResult]
    private(set) var sent: [SupportReportPayload] = []

    init(_ results: [SupportReportUploadResult]) { self.results = results }

    func upload(_ payload: SupportReportPayload) async -> SupportReportUploadResult {
        sent.append(payload)
        return results.isEmpty ? .retryLater : results.removeFirst()
    }

    func payloads() -> [SupportReportPayload] { sent }
}

@main
struct SupportReportTests {
    static let contracts = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .appendingPathComponent("../../../../contracts", isDirectory: true).standardizedFileURL
    static let identity = DeviceIdentity(manufacturer: "Garmin", model: "fenix 8 - 47mm", family: "fenix", variant: "47mm",
        usbVendorId: 0x091e, usbProductId: 0x51b8, firmware: "2244", storageCapacity: 32_000_000_000, freeSpace: 20_000_000_000,
        localHardwareIdentifier: "PRIVATE-UNIT-SERIAL", garminModelDescription: "fenix 8 - 47mm", garminModelPartNumber: "006-B4536-00")

    @MainActor
    static func main() async throws {
        testReference()
        try testFixturesRoundTrip()
        var produced: [SupportReportPayload] = []
        produced.append(try testInstallationReportMirrorsTheGitHubReport())
        produced.append(testUpdateReportOmitsInstallOnlyFacts())
        produced.append(testMinimalReport())
        testTextRules()
        testResponseMapping()
        try await testExplicitSendAndRetry()
        try writeProduced(produced)
        print("PASS: support report payload, sanitising, reference, responses and explicit send")
    }

    static func testReference() {
        expect(SupportReportReference.make(id: "6f1d2c3b-8a4e-4f60-9b7a-2c1d0e9f8a71") == "TR-FYMEFT",
            "the reference matches the contract example")
        expect(SupportReportReference.make(id: "6F1D2C3B-8A4E-4F60-9B7A-2C1D0E9F8A71") == "TR-FYMEFT",
            "the reference uses the lowercase canonical id")
    }

    static func testFixturesRoundTrip() throws {
        for name in ["support-report.valid", "support-report.valid-minimal", "support-report.valid-local-update"] {
            let data = try Data(contentsOf: contracts.appendingPathComponent("fixtures/\(name).json"))
            let payload = try JSONDecoder().decode(SupportReportPayload.self, from: data)
            let original = try JSONSerialization.jsonObject(with: data) as! [String: Any]
            let encoded = try JSONSerialization.jsonObject(with: payload.encoded()) as! [String: Any]
            expect(NSDictionary(dictionary: stripNulls(original)).isEqual(to: encoded),
                "\(name) decodes into the Swift payload and re-encodes to the same JSON (keys mirror the contract)")
        }
        let invalid = try Data(contentsOf: contracts.appendingPathComponent("fixtures/support-report.invalid-disallowed-field.json"))
        let decoded = try? JSONDecoder().decode(SupportReportPayload.self, from: invalid)
        let reencoded = decoded.flatMap { try? JSONSerialization.jsonObject(with: $0.encoded()) as? [String: Any] }
        let original = try JSONSerialization.jsonObject(with: invalid) as! [String: Any]
        expect(reencoded.map { !NSDictionary(dictionary: stripNulls(original)).isEqual(to: $0) } ?? true,
            "a disallowed field cannot be produced by the Swift payload")
    }

    @MainActor
    static func testInstallationReportMirrorsTheGitHubReport() throws -> SupportReportPayload {
        let operationID = UUID()
        let draft = InstallationIssueReport.generate(
            identity: identity,
            maps: [InstallationIssueMap(provider: "MapRando", region: "Lithuania", package: "maprando-lituanie",
                                        release: "2026-09-02", artifactSizeBytes: 182_239_232)],
            stage: "Finishing",
            lifecycleFacts: ["Technical detail: read failed at /Users/alice/Library/Caches/x.img", "Unavailable"],
            error: "The map was written, but Terento could not confirm it.\nserial: ABC123",
            operationID: operationID,
            failureStages: ["verify"],
            errorCategory: "device",
            errorCodes: ["INSTALL_FAILED_HASH_MISMATCH", "bad code with spaces", "INSTALL_FAILED_HASH_MISMATCH"],
            writeStarted: true, transferProgressPercent: 140, remoteObjectCreated: true,
            verification: InstallationIssueVerification(originalFailure: "INSTALL_FAILED_HASH_MISMATCH",
                transportClassification: "READBACK_FAILED", artifactKind: "main", sourceSize: 182_239_232,
                remoteSize: 182_239_232, transferredBytes: 182_239_232, elapsedMilliseconds: 418_211,
                sampledBytes: 29_229_056, sampleCount: 12, matchedSampleCount: 4),
            failureContext: InstallationFailureContext(boundary: .readback, classificationSource: .native,
                devicePresence: .present, operation: .fileRange, executionMode: .worker, resultKind: .nativeError,
                retryCount: 2),
            operatingSystem: "Version 15.6 (Build 24G84)")
        guard let saved = draft.supportReport else {
            fail("the GitHub draft carries the structured support report")
            fatalError()
        }
        expect(saved.title == draft.title && saved.category == .installFailed && saved.operationID == operationID,
            "the structured report keeps the GitHub title, category and operation id")
        let report = saved.report
        expect(report.macOSVersion == "Version 15.6 (Build 24G84)" && report.operation == .installation
            && report.stage == "Finishing" && report.failureStages == ["verify"] && report.errorCategory == "device",
            "summary fields mirror the GitHub report")
        expect(report.errorCodes == ["INSTALL_FAILED_HASH_MISMATCH"], "error codes are closed identifiers, de-duplicated")
        expect(report.message?.contains("\n") == false && report.message?.contains("ABC123") == false,
            "the message is one sanitised line without the serial")
        expect(report.device == SupportReportDevice(model: identity.presentationModel, variant: "47mm", family: "fenix",
            firmware: "2244", mtpModel: "fenix 8 - 47mm"), "device fields are model strings only")
        expect(report.maps == [SupportReportMap(provider: "MapRando", region: "Lithuania", package: "maprando-lituanie",
            release: "2026-09-02", plannedBytes: 182_239_232)], "map packages mirror the GitHub report")
        expect(report.writeStarted == true && report.objectCreated == true && report.cleanupAttempted == false
            && report.transferProgressPercent == 100, "installation facts are booleans and a bounded percentage")
        expect(report.verification?.sampleCount == 12 && report.verification?.failedComponent == "main",
            "verification details are carried")
        expect(report.lifecycleFacts?.count == 1 && report.lifecycleFacts?.first?.contains("/Users/") == false,
            "lifecycle facts drop Unavailable values and redact local paths")
        expect(report.failureContext?.boundary == .readback, "the structured failure context is carried")
        let payload = SupportReportPayload(category: saved.category, operationID: saved.operationID,
                                           userMessage: "It stopped at the end.", report: report)
        let json = String(data: try payload.encoded(), encoding: .utf8) ?? ""
        for forbidden in ["PRIVATE-UNIT-SERIAL", "006-B4536-00", "/Users/", "Unavailable", "Diagnostic ID", "\"Transport\""] {
            expect(!json.contains(forbidden), "the payload never contains \(forbidden)")
        }
        expect(payload.previewText.contains("\"userMessage\" : \"It stopped at the end.\""),
            "the preview is exactly the JSON that is sent, including the description")
        let size = try payload.encoded().count
        expect(size <= 64 * 1024, "the payload fits the 64 KiB limit")
        return payload
    }

    @MainActor
    static func testUpdateReportOmitsInstallOnlyFacts() -> SupportReportPayload {
        let draft = InstallationIssueReport.generate(identity: nil,
            maps: [InstallationIssueMap(provider: "freizeitkarte", region: "Germany", package: "freizeitkarte-deu",
                                        release: "2026-09", artifactSizeBytes: nil)],
            stage: "failedInsufficientSpace", operation: .update, error: nil, operationID: nil,
            errorCodes: ["failedInsufficientSpace"])
        let report = draft.supportReport!.report
        expect(draft.supportReport?.category == .updateFailed && report.operation == .update,
            "an update report is categorised as UPDATE_FAILED")
        expect(report.writeStarted == nil && report.transferProgressPercent == nil && report.device == nil
            && report.message == nil && report.maps?.first?.plannedBytes == nil,
            "facts the GitHub report marks Unavailable are omitted")
        return SupportReportPayload(category: .updateFailed, operationID: nil, userMessage: "   ", report: report)
    }

    static func testMinimalReport() -> SupportReportPayload {
        let payload = SupportReportPayload(category: .connection, operationID: nil, userMessage: nil,
                                           report: .minimal(macOSVersion: "Version 26.0 (Build 25A354)"))
        expect(payload.report == SupportReportBody(macOSVersion: "Version 26.0 (Build 25A354)"),
            "without a saved failure only macOSVersion is sent")
        expect(payload.releaseLabel.hasSuffix("-local") && payload.appBuild.hasSuffix("-local"),
            "local builds are marked through the existing release label")
        return payload
    }

    static func testTextRules() {
        expect(SupportReportText.clean("  file:///Users/me/a.img\tline\u{7}  ", max: 120)?.contains("file://") == false,
            "path markers are redacted")
        expect(SupportReportText.clean("a\u{0}b\nc", max: 120) == "a b c", "control characters become spaces")
        expect(SupportReportText.clean("Unavailable", max: 120) == nil, "Unavailable is omitted")
        expect(SupportReportText.clean(String(repeating: "é", count: 600), max: 500)?.unicodeScalars.count == 500,
            "text is bounded in Unicode scalars")
        expect(SupportReportText.userMessage("  \n ") == nil, "a blank description is omitted")
        expect(SupportReportText.userMessage("Line 1\nLine 2\t/Volumes/USB/x")
            .map { $0.contains("\n") && !$0.lowercased().contains("/volumes/") } == true,
            "descriptions keep newlines and lose local paths")
        expect(SupportReportText.userMessage(String(repeating: "x", count: 2500))?.count == 2000,
            "descriptions are limited to 2000 characters")
        let trace = """
        FINISH_TRACE swift event=installation_begin
        FINISH_TRACE native event=read_failed offset=1 rc=-1
        FINISH_TRACE swift note=/Users/me event=x
        unrelated line
        """
        expect(SupportReportText.traceLines(trace) == ["FINISH_TRACE swift event=installation_begin",
            "FINISH_TRACE native event=read_failed offset=1 rc=-1"], "trace lines that do not match are dropped")
        expect(SupportReportText.code("READBACK_FAILED") != nil && SupportReportText.code("-x") == nil,
            "codes follow the closed identifier pattern")
    }

    static func testResponseMapping() {
        let accepted = Data(#"{"reference":"TR-FYMEFT","status":"stored"}"#.utf8)
        let duplicate = Data(#"{"reference":"TR-FYMEFT","status":"duplicate"}"#.utf8)
        expect(HTTPSupportReportUploader.result(statusCode: 201, body: accepted) == .accepted(reference: "TR-FYMEFT"),
            "201 stored returns the reference")
        expect(HTTPSupportReportUploader.result(statusCode: 200, body: duplicate) == .accepted(reference: "TR-FYMEFT"),
            "200 duplicate returns the same reference")
        expect(HTTPSupportReportUploader.result(statusCode: 409, body: Data()) == .referenceConflict, "409 is a reference conflict")
        expect(HTTPSupportReportUploader.result(statusCode: 429, body: Data()) == .retryLater, "429 retries later")
        expect(HTTPSupportReportUploader.result(statusCode: 503, body: Data()) == .retryLater, "503 retries later")
        expect(HTTPSupportReportUploader.result(statusCode: 400, body: Data()) == .rejected(status: 400), "400 is rejected")
        expect(HTTPSupportReportUploader.result(statusCode: 201, body: Data("{}".utf8)) == .retryLater,
            "a malformed success body is not shown as sent")
    }

    @MainActor
    static func testExplicitSendAndRetry() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("terento-support-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let outbox = SupportReportOutbox(rootURL: root)
        let base = SupportReportPayload(category: .installFailed, operationID: UUID(), userMessage: nil,
                                        report: .minimal(macOSVersion: "Version 15.6"))

        let uploader = RecordingSupportUploader([.retryLater, .accepted(reference: base.reference)])
        let controller = SupportReportController(payload: base, uploader: uploader, outbox: outbox)
        let nothingSent = await uploader.payloads().isEmpty
        expect(nothingSent, "opening the sheet sends nothing")
        controller.userMessage = String(repeating: "y", count: 2100)
        expect(controller.userMessage.count == 2000, "the description field stops at 2000 characters")
        controller.userMessage = "Watch was on a hub."
        await controller.send()
        expect(controller.isFailed && outbox.load()?.id == base.id && outbox.load()?.userMessage == "Watch was on a hub.",
            "a failed send keeps the report locally and offers Try again")
        await controller.send()
        let sent = await uploader.payloads()
        expect(controller.state == .sent(reference: base.reference) && sent.count == 2 && sent[0].id == sent[1].id,
            "Try again resends the same id and shows the server reference")
        expect(outbox.load() == nil, "a sent report leaves no local copy")

        let conflict = RecordingSupportUploader([.referenceConflict, .accepted(reference: "TR-AAAAAA")])
        let retried = SupportReportController(payload: base, uploader: conflict, outbox: outbox)
        await retried.send()
        let conflictSent = await conflict.payloads()
        expect(conflictSent.count == 2 && conflictSent[0].id != conflictSent[1].id
            && retried.state == .sent(reference: "TR-AAAAAA"), "a reference conflict is resent once with a new id")

        let source = try String(contentsOfFile: "Sources/TerentoPoC/Diagnostics/SupportReportSender.swift", encoding: .utf8)
        expect(!source.contains("consent") && !source.contains("sharingEnabled"),
            "sending a report the user chose is independent of the sharing toggles")
    }

    static func writeProduced(_ payloads: [SupportReportPayload]) throws {
        guard let path = ProcessInfo.processInfo.environment["TERENTO_SUPPORT_REPORT_PAYLOADS"] else { return }
        let objects = try payloads.map { try JSONSerialization.jsonObject(with: $0.encoded()) }
        try JSONSerialization.data(withJSONObject: objects).write(to: URL(fileURLWithPath: path))
    }

    static func stripNulls(_ value: [String: Any]) -> [String: Any] {
        value.compactMapValues { item -> Any? in
            if item is NSNull { return nil }
            if let nested = item as? [String: Any] { return stripNulls(nested) }
            if let array = item as? [Any] { return array.map { ($0 as? [String: Any]).map(stripNulls) ?? $0 } }
            return item
        }
    }

    static func fail(_ message: String) {
        fputs("FAIL: \(message)\n", stderr)
        exit(1)
    }

    static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        guard condition() else { fail(message); return }
    }
}
