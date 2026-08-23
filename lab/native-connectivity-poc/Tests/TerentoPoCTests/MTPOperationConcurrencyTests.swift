import Foundation

private final class OperationCounter: @unchecked Sendable {
    private let lock = NSLock()
    private(set) var completed = 0
    private(set) var active = 0
    private(set) var maximumActive = 0

    func enter() {
        lock.lock()
        active += 1
        maximumActive = max(maximumActive, active)
        lock.unlock()
    }

    func leave() {
        lock.lock()
        active -= 1
        completed += 1
        lock.unlock()
    }
}

@main
struct MTPOperationConcurrencyTests {
    static func main() async throws {
        try testIdlePresenceIsAllowed()
        try testLifecyclePausesPresence()
        try await testAsyncLifecycleWaitsForPreviousOperation()
        try await testCatalogOperationWaitsForLifecycle()
        try testNativeOperationsAreSerialized()
        try testDisconnectInvalidatesMutationLease()
        try testStaleLifecycleCompletionIsRejected()

        print("PASS: 7 MTP operation concurrency and disconnect tests")
    }

    private static func testIdlePresenceIsAllowed() throws {
        let gate = MTPOperationGate()
        var bodyRan = false
        try gate.withOperation(kind: .presence) {
            bodyRan = true
        }
        guard bodyRan else {
            throw Failure("idle presence was blocked even though no lifecycle lease exists")
        }
        print("PASS: idle presence can probe when no lifecycle operation is active")
    }

    private static func testLifecyclePausesPresence() throws {
        let gate = MTPOperationGate()
        let lease = try gate.beginLifecycle()
        defer { gate.endLifecycle(lease) }

        var bodyRan = false
        do {
            try gate.withOperation(kind: .presence) {
                bodyRan = true
            }
            throw Failure("presence operation was allowed during lifecycle lease")
        } catch let error as MTPOperationGateError {
            guard error == .lifecycleBusy else {
                throw Failure("presence was blocked with the wrong gate error")
            }
        }

        guard !bodyRan else {
            throw Failure("blocked presence operation entered native body")
        }
        print("PASS: lifecycle lease pauses presence monitoring")
    }

    private static func testAsyncLifecycleWaitsForPreviousOperation() async throws {
        let gate = MTPOperationGate()
        let first = try gate.beginLifecycle()
        let waiting = Task { try await gate.beginLifecycleAsync() }

        try await Task.sleep(for: .milliseconds(80))
        guard !waiting.isCancelled else {
            throw Failure("queued lifecycle operation was cancelled unexpectedly")
        }

        gate.endLifecycle(first)
        let second = try await waiting.value
        guard gate.isValid(second) else {
            throw Failure("queued lifecycle operation did not receive a valid lease")
        }
        gate.endLifecycle(second)
        print("PASS: queued lifecycle waits without blocking the caller")
    }

    private static func testCatalogOperationWaitsForLifecycle() async throws {
        let gate = MTPOperationGate()
        let lifecycle = try gate.beginLifecycle()
        let catalog = Task {
            try await gate.withAsyncOperation(kind: .catalog) {
                true
            }
        }

        try await Task.sleep(for: .milliseconds(80))
        guard !catalog.isCancelled else {
            throw Failure("catalog operation was cancelled while waiting")
        }
        gate.endLifecycle(lifecycle)
        guard try await catalog.value else {
            throw Failure("catalog operation did not complete after lifecycle release")
        }
        print("PASS: catalog loading shares the serialized operation gate")
    }

    private static func testNativeOperationsAreSerialized() throws {
        let gate = MTPOperationGate()
        let counter = OperationCounter()
        let group = DispatchGroup()
        let queue = DispatchQueue(label: "terento.mtp-gate-test", attributes: .concurrent)

        for _ in 0..<8 {
            group.enter()
            queue.async {
                defer { group.leave() }
                do {
                    try gate.withOperation(kind: .inventory) {
                        counter.enter()
                        usleep(12_000)
                        counter.leave()
                    }
                } catch {
                    return
                }
            }
        }

        group.wait()
        guard counter.completed == 8, counter.maximumActive == 1 else {
            throw Failure("native operation gate allowed overlapping native work")
        }
        print("PASS: native operations are serialized process-wide")
    }

    private static func testDisconnectInvalidatesMutationLease() throws {
        let gate = MTPOperationGate()
        let lease = try gate.beginLifecycle()
        gate.invalidateLifecycleOperations()
        defer { gate.endLifecycle(lease) }

        var bodyRan = false
        do {
            try gate.withOperation(kind: .remove, lifecycleLease: lease) {
                bodyRan = true
            }
            throw Failure("remove entered native body after disconnect invalidation")
        } catch let error as MTPOperationGateError {
            guard error == .lifecycleInvalidated else {
                throw Failure("disconnect invalidation returned the wrong gate error")
            }
        }

        guard !bodyRan else {
            throw Failure("invalidated mutation lease reached native transport")
        }
        print("PASS: disconnect invalidates pending mutation before native entry")
    }

    private static func testStaleLifecycleCompletionIsRejected() throws {
        let controller = MapLifecycleOperationController()
        guard let token = controller.begin() else {
            throw Failure("could not start lifecycle operation")
        }

        controller.invalidate()
        guard !controller.isCurrent(token), controller.isBusy, !controller.canEject else {
            throw Failure("disconnect did not invalidate stale completion while retaining the active handle")
        }

        controller.finish(token)
        guard let replacement = controller.begin() else {
            throw Failure("controller did not accept a fresh operation after disconnect")
        }
        controller.finish(replacement)
        print("PASS: stale lifecycle completion cannot repopulate state")
    }

    private struct Failure: Error {
        let message: String

        init(_ message: String) {
            self.message = message
        }
    }
}
