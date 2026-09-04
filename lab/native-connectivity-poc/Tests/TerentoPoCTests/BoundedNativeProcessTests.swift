import Foundation

@main
struct BoundedNativeProcessTests {
    static func main() throws {
        try BoundedNativeProcess.run(executable: URL(fileURLWithPath: "/usr/bin/true"),
                                    arguments: [], input: Data(), timeout: 1)
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
        print("PASS: stalled native child is terminated and reaped on deadline/cancellation")
    }
}
