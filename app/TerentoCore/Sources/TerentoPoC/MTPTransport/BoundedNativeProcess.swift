import Foundation
import Darwin

/// A native call cannot be safely cancelled by abandoning a Swift thread.
/// Own the child until exit, including on timeout, before releasing the MTP lease.
enum BoundedNativeProcess {
    static func run(
        executable: URL, arguments: [String], input: Data,
        timeout: TimeInterval, inactivityTimeout: TimeInterval? = nil, verifiedProgress: () -> UInt64? = { nil }, diagnosticFile: URL? = nil, onPoll: () -> Void = {}, cancelled: () -> Bool = { Task<Never, Never>.isCancelled }
    ) throws {
        let process = Process()
        process.executableURL = executable
        process.arguments = arguments
        if let diagnosticFile {
            var environment = ProcessInfo.processInfo.environment
            environment["TERENTO_FINISHING_TRACE_FILE"] = diagnosticFile.path
            process.environment = environment
        }
        let stdin = Pipe()
        process.standardInput = stdin
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.standardError
        let exited = DispatchSemaphore(value: 0)
        process.terminationHandler = { _ in exited.signal() }
        try process.run()
        FinishingTrace.event("worker_started", "child=\(process.processIdentifier) timeout=\(timeout)")
        defer {
            try? stdin.fileHandleForWriting.close()
            if process.isRunning {
                kill(process.processIdentifier, SIGKILL)
                process.waitUntilExit()
            }
        }
        try stdin.fileHandleForWriting.write(contentsOf: input)
        try stdin.fileHandleForWriting.close()
        var deadline = NativeProcessDeadline(start: ProcessInfo.processInfo.systemUptime,
                                             timeout: timeout, inactivityTimeout: inactivityTimeout)
        while exited.wait(timeout: .now() + 0.05) == .timedOut {
            onPoll()
            let cancellationRequested = cancelled()
            let now = ProcessInfo.processInfo.systemUptime
            let expired = deadline.isExpired(at: now, verifiedBytes: verifiedProgress())
            if cancellationRequested || expired {
                FinishingTrace.event(cancellationRequested ? "worker_cancelled" : "worker_deadline",
                                     "child=\(process.processIdentifier)")
                // Only our own child is killed. No other MTP client or app is touched.
                kill(process.processIdentifier, SIGKILL)
                process.waitUntilExit()
                throw NativeProcessFailure.deadlineOrCancellation
            }
        }
        FinishingTrace.event("worker_exited", "child=\(process.processIdentifier) status=\(process.terminationStatus) reason=\(process.terminationReason.rawValue)")
        guard process.terminationStatus == 0 else { throw NativeProcessFailure.failed }
    }
}

/// Only new verified bytes renew the inactivity budget; the absolute ceiling
/// always wins, including when progress arrives after a deadline has expired.
struct NativeProcessDeadline {
    let absoluteDeadline: TimeInterval
    let inactivityTimeout: TimeInterval?
    private(set) var lastProgressAt: TimeInterval
    private(set) var maximumVerifiedBytes: UInt64 = 0

    init(start: TimeInterval, timeout: TimeInterval, inactivityTimeout: TimeInterval?) {
        absoluteDeadline = start + timeout
        self.inactivityTimeout = inactivityTimeout
        lastProgressAt = start
    }

    mutating func isExpired(at now: TimeInterval, verifiedBytes: UInt64?) -> Bool {
        if now >= absoluteDeadline { return true }
        if let inactivityTimeout, now - lastProgressAt >= inactivityTimeout { return true }
        if let verifiedBytes, verifiedBytes > maximumVerifiedBytes {
            maximumVerifiedBytes = verifiedBytes
            lastProgressAt = now
        }
        return false
    }
}

enum NativeProcessFailure: Error {
    case deadlineOrCancellation
    case failed
}

/// Normal builds retain bounded, fixed-field diagnostics locally. Debug launches
/// can also mirror them to stderr. No raw native errors enter this stream.
/// Call sites supply fixed labels and numeric counters, never error descriptions.
enum FinishingTrace {
    static let enabled: Bool = {
        #if DEBUG
        ProcessInfo.processInfo.environment["TERENTO_FINISHING_TRACE"] == "1"
        #else
        false
        #endif
    }()

    static func event(_ name: String, _ details: @autoclosure () -> String = "") {
        let line = "FINISH_TRACE swift t=\(ProcessInfo.processInfo.systemUptime) pid=\(ProcessInfo.processInfo.processIdentifier) event=\(name) \(details())\n"
        if let path = ProcessInfo.processInfo.environment["TERENTO_FINISHING_TRACE_FILE"] {
            appendFile(Data(line.utf8), to: URL(fileURLWithPath: path))
        } else {
            record(line)
        }
        if enabled { try? FileHandle.standardError.write(contentsOf: Data(line.utf8)) }
    }
}


extension FinishingTrace {
    private static let lock = NSLock()
    // Every access to these fields is protected by lock.
    nonisolated(unsafe) private static var entries: [String] = []
    nonisolated(unsafe) private static var frozenReport = ""
    static let fileURL = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Logs/Terento/finishing.log")

    static func beginInstallation() {
        lock.lock()
        entries.removeAll(keepingCapacity: true)
        frozenReport = ""
        lock.unlock()
        event("installation_begin")
    }

    /// Freeze before later inventory/Remove activity can change the report.
    static func freezeFailure() {
        lock.lock(); defer { lock.unlock() }
        let significant = entries.filter {
            !$0.contains("event=read_checkpoint") && !$0.contains("event=region_begin")
        }
        let first = significant.firstIndex { line in
            line.contains("event=read_failed") || line.contains("event=compare_failed") ||
            ["open_end", "identity_end", "target_end", "verify_result"].contains { event in
                line.contains("event=\(event) ") && line.contains("rc=-")
            }
        } ?? significant.firstIndex { line in
            line.contains("event=worker_deadline") || line.contains("event=worker_cancelled")
        }
        var selected: [String] = []
        if let first {
            selected += significant[first...min(significant.count - 1, first + 5)]
        }
        if let checkpoint = entries.last(where: { $0.contains("event=read_checkpoint") }) {
            selected.append(checkpoint)
        }
        // Keep attempt context and final outcomes; never export raw logs or paths.
        selected += significant.prefix(8)
        selected += significant.suffix(36)
        var seen = Set<String>()
        var reportLines = selected.filter { seen.insert($0).inserted }.map { line in
            line.split(separator: " ").filter { token in
                !["pid=", "child=", "trace=", "t="].contains { token.hasPrefix($0) }
            }.joined(separator: " ")
        }
        // Drop middle context before either the first failure or final cleanup;
        // the report budget must not cut an event or discard its ending.
        while reportLines.joined(separator: "\n").count > 10000 && reportLines.count > 3 {
            reportLines.remove(at: 2)
        }
        frozenReport = reportLines.joined(separator: "\n")
    }

    static var failureReport: String {
        lock.lock(); defer { lock.unlock() }
        return String(frozenReport.prefix(10000))
    }

    /// The file contains only our own trace writers, never libmtp stderr.
    /// Strict parsing is still mandatory before local retention or sharing.
    static func captureWorker(_ url: URL) {
        guard let handle = try? FileHandle(forReadingFrom: url) else { return }
        defer { try? handle.close() }
        guard let data = try? handle.read(upToCount: 512 * 1024),
              let text = String(data: data, encoding: .utf8) else { return }
        record(text.split(separator: "\n").map(String.init))
    }

    private static let allowedEvents: Set<String> = [
        "installation_begin", "source_validation", "operation_begin", "operation_worker_failed", "operation_failed",
        "operation_complete", "worker_operation_begin", "worker_operation_failed", "worker_started",
        "worker_exited", "worker_deadline", "worker_cancelled", "readback_attempt", "readback_failed",
        "verify_begin", "region_begin", "open_begin", "open_end", "identity_begin", "identity_end",
        "read_chunk_limit", "abort_close_begin", "abort_close_returned", "target_begin", "target_end", "read_failed", "read_error_code", "read_ptp_response", "retry_close_begin",
        "retry_close_returned", "compare_failed", "verify_result", "final_close_begin",
        "final_close_returned", "read_checkpoint", "target_matches", "target_size", "final_inventory", "installation_failure", "cleanup_result"
    ]
    private static let numericKeys: Set<String> = [
        "t", "pid", "child", "timeout", "attempt", "delay", "status", "reason", "offset", "rc",
        "detail", "last_verified_end", "verified_bytes", "elapsed", "matches", "expected_size", "actual_size", "folder", "zero_id", "filename_match", "succeeded"
    ]
    static func safeLine(_ line: String) -> String? {
        guard line.utf8.count < 1024 else { return nil }
        let parts = line.split(whereSeparator: { $0.isWhitespace }).map(String.init)
        guard parts.count >= 3, parts[0] == "FINISH_TRACE", ["swift", "native"].contains(parts[1]) else { return nil }
        var hasEvent = false
        for part in parts.dropFirst(2) {
            let pair = part.split(separator: "=", omittingEmptySubsequences: false).map(String.init)
            guard pair.count == 2 else { return nil }
            let key = pair[0], value = pair[1]
            if key == "event" { guard allowedEvents.contains(value) else { return nil }; hasEvent = true }
            else if numericKeys.contains(key) {
                guard !value.isEmpty, value.utf8.allSatisfy({ (48...57).contains($0) || $0 == 45 || $0 == 46 }),
                      let number = Double(value), number.isFinite else { return nil }
            } else if key == "operation" {
                guard ["samples", "cleanup", "inventory", "snapshot"].contains(value) else { return nil }
            } else if key == "validation" {
                guard ["notExactValidatedArtifact", "sourceUnavailable", "sourceSizeMismatch",
                       "sourceHashMismatch", "sourceFormatMismatch", "unknown"].contains(value) else { return nil }
            } else if key == "worker" { guard ["true", "false"].contains(value) else { return nil } }
            else if key == "trace" { guard UUID(uuidString: value) != nil else { return nil } }
            else if key == "error" {
                guard ["other", "deviceDisconnected", "operationFailed", "remoteFileMissing",
                       "objectIdentityMismatch", "targetAlreadyExists", "unsupportedDevice", "liveIdentityMismatch"].contains(value) else { return nil }
            } else { return nil }
        }
        return hasEvent ? parts.joined(separator: " ") : nil
    }

    private static func record(_ line: String) {
        record([line])
    }

    private static func record(_ lines: [String]) {
        let safe = lines.compactMap(safeLine)
        guard !safe.isEmpty else { return }
        let data = Data((safe.joined(separator: "\n") + "\n").utf8)
        lock.lock(); defer { lock.unlock() }
        // Keep early failure evidence and the final cleanup outcome.
        for line in safe {
            if entries.count >= 2048 { entries.remove(at: 1024) }
            entries.append(line)
        }
        let fm = FileManager.default
        try? fm.createDirectory(at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        if let size = (try? fm.attributesOfItem(atPath: fileURL.path)[.size]) as? NSNumber,
           size.intValue + data.count > 512 * 1024 {
            let previous = fileURL.appendingPathExtension("previous")
            try? fm.removeItem(at: previous)
            try? fm.moveItem(at: fileURL, to: previous)
        }
        appendFile(data, to: fileURL)
    }

    private static func appendFile(_ data: Data, to url: URL) {
        let fd = open(url.path, O_WRONLY | O_APPEND | O_CREAT | O_NOFOLLOW, 0o600)
        guard fd >= 0 else { return }
        defer { close(fd) }
        data.withUnsafeBytes { buffer in
            if let address = buffer.baseAddress { _ = write(fd, address, buffer.count) }
        }
    }
}
