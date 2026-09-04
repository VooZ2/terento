import Foundation
import Darwin

/// A native call cannot be safely cancelled by abandoning a Swift thread.
/// Own the child until exit, including on timeout, before releasing the MTP lease.
enum BoundedNativeProcess {
    static func run(
        executable: URL, arguments: [String], input: Data,
        timeout: TimeInterval, cancelled: () -> Bool = { Task<Never, Never>.isCancelled }
    ) throws {
        let process = Process()
        process.executableURL = executable
        process.arguments = arguments
        let stdin = Pipe()
        process.standardInput = stdin
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.standardError
        let exited = DispatchSemaphore(value: 0)
        process.terminationHandler = { _ in exited.signal() }
        try process.run()
        defer {
            try? stdin.fileHandleForWriting.close()
            if process.isRunning {
                kill(process.processIdentifier, SIGKILL)
                process.waitUntilExit()
            }
        }
        try stdin.fileHandleForWriting.write(contentsOf: input)
        try stdin.fileHandleForWriting.close()
        let deadline = ProcessInfo.processInfo.systemUptime + timeout
        while exited.wait(timeout: .now() + 0.05) == .timedOut {
            if cancelled() || ProcessInfo.processInfo.systemUptime >= deadline {
                // Only our own child is killed. No other MTP client or app is touched.
                kill(process.processIdentifier, SIGKILL)
                process.waitUntilExit()
                throw NativeProcessFailure.deadlineOrCancellation
            }
        }
        guard process.terminationStatus == 0 else { throw NativeProcessFailure.failed }
    }
}

enum NativeProcessFailure: Error {
    case deadlineOrCancellation
    case failed
}
