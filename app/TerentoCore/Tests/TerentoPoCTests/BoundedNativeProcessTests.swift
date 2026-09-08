import Foundation

@main
struct BoundedNativeProcessTests {
    static func main() throws {
        try BoundedNativeProcess.run(executable: URL(fileURLWithPath: "/usr/bin/true"),
                                    arguments: [], input: Data(), timeout: 1)
        var polls = 0
        try BoundedNativeProcess.run(executable: URL(fileURLWithPath: "/bin/sleep"),
            arguments: ["0.2"], input: Data(), timeout: 1, onPoll: { polls += 1 })
        precondition(polls > 0, "worker progress must be observable before completion")
        for cancel in [false, true] {
            let start = ProcessInfo.processInfo.systemUptime
            do {
                try BoundedNativeProcess.run(executable: URL(fileURLWithPath: "/bin/sleep"),
                    arguments: ["30"], input: Data(), timeout: 0.15, cancelled: { cancel })
                fatalError("stalled child incorrectly succeeded")
            } catch NativeProcessFailure.deadlineOrCancellation {
                precondition(ProcessInfo.processInfo.systemUptime - start < 2)
            }
        }
        // A subsequent process can run only after the cancelled native child exits.
        try BoundedNativeProcess.run(executable: URL(fileURLWithPath: "/usr/bin/true"),
                                    arguments: [], input: Data(), timeout: 1)
        let native = "FINISH_TRACE native t=1.25 pid=12 event=read_failed offset=182108160 rc=-1 detail=0 last_verified_end=182108160 verified_bytes=29229056"
        precondition(FinishingTrace.safeLine(native) == native)
        for unsafe in [native + " path=/Users/private/map.img", native + " serial=1234",
                       "FINISH_TRACE swift event=operation_failed error=secret",
                       "FINISH_TRACE native event=read_failed rc=nan",
                       "LIBMTP raw device serial 1234"] {
            precondition(FinishingTrace.safeLine(unsafe) == nil)
        }
        let trace = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: trace) }
        try BoundedNativeProcess.run(executable: URL(fileURLWithPath: "/bin/sh"),
            arguments: ["-c", "printf '%s\\n' 'FINISH_TRACE native t=1 pid=1 event=read_failed offset=64 rc=-1 detail=0' > \"$TERENTO_FINISHING_TRACE_FILE\""],
            input: Data(), timeout: 1, diagnosticFile: trace)
        do {
            try BoundedNativeProcess.run(executable: URL(fileURLWithPath: "/bin/sh"),
                arguments: ["-c", "printf '%s\\n' 'FINISH_TRACE native t=1 pid=1 event=read_failed offset=64 rc=-1 detail=0' > \"$TERENTO_FINISHING_TRACE_FILE\"; exec /bin/sleep 30"],
                input: Data(), timeout: 0.15, diagnosticFile: trace)
            fatalError("worker must time out")
        } catch NativeProcessFailure.deadlineOrCancellation { }
        let captured = try String(contentsOf: trace, encoding: .utf8)
        precondition(captured.contains("event=read_failed"))
        FinishingTrace.beginInstallation()
        FinishingTrace.captureWorker(trace)
        FinishingTrace.event("worker_deadline", "child=1")
        FinishingTrace.freezeFailure()
        precondition(FinishingTrace.failureReport.contains("event=read_failed"))
        precondition(FinishingTrace.failureReport.contains("event=worker_deadline"))
        let frozen = FinishingTrace.failureReport
        FinishingTrace.event("operation_complete", "operation=inventory")
        precondition(FinishingTrace.failureReport == frozen)
        FinishingTrace.beginInstallation()
        precondition(FinishingTrace.failureReport.isEmpty)
        // Successful cleanup must not displace a failed target/identity lookup.
        for event in ["target_end", "identity_end", "verify_result"] {
            FinishingTrace.beginInstallation()
            FinishingTrace.event(event, "offset=0 rc=-21 detail=0")
            FinishingTrace.event("operation_begin", "operation=cleanup")
            FinishingTrace.event("worker_started", "child=1")
            FinishingTrace.event("worker_operation_begin", "operation=cleanup")
            FinishingTrace.event("worker_exited", "child=1 status=0")
            FinishingTrace.event("operation_complete", "operation=cleanup")
            FinishingTrace.freezeFailure()
            precondition(FinishingTrace.failureReport.contains("event=\(event)"))
            precondition(FinishingTrace.failureReport.contains("rc=-21"))
            precondition(FinishingTrace.failureReport.contains("operation=cleanup"))
        }
        FinishingTrace.beginInstallation()
        FinishingTrace.beginInstallation()
        FinishingTrace.event("target_matches", "offset=1794965504 rc=0 detail=0")
        FinishingTrace.event("final_inventory", "attempt=2 matches=0 expected_size=1794965504 actual_size=0 folder=0 zero_id=0 filename_match=0")
        FinishingTrace.event("target_end", "offset=0 rc=-21 detail=0")
        for _ in 0..<100 { FinishingTrace.event("operation_complete", "operation=cleanup elapsed=1") }
        FinishingTrace.freezeFailure()
        precondition(FinishingTrace.failureReport.contains("event=target_end"))
        precondition(FinishingTrace.failureReport.contains("event=final_inventory"))
        precondition(!FinishingTrace.failureReport.contains("pid="))
        precondition(!FinishingTrace.failureReport.contains("trace="))
        precondition(FinishingTrace.failureReport.count <= 10000)
        precondition(FinishingTrace.safeLine("FINISH_TRACE native event=target_size offset=1 detail=1 path=/Users/private") == nil)
        print("PASS: strict diagnostic fields, release worker file, frozen failure and reset")
        print("PASS: stalled native child is terminated and reaped on deadline/cancellation")
    }
}
