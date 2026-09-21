import Foundation

@main
struct NativeMutationLedgerTests {
    static func main() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("terento-ledger-tests-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let hash = String(repeating: "a", count: 64)
        func scope(_ filename: String = "terento_test_map.img", hash: String? = nil, device: String = "TEST-DEVICE") -> NativeMutationLedger.Scope {
            .init(physicalIdentifierSource: 1, physicalIdentifier: device, expectedStorageID: 7,
                  filename: filename, size: 1024, sha256: hash)
        }
        var count = 0
        func check(_ condition: Bool, _ label: String) {
            precondition(condition, label); count += 1
        }
        func denied(_ action: () throws -> Void) {
            do { try action(); preconditionFailure("invalid operation accepted") }
            catch { count += 1 }
        }
        func record(_ ledger: NativeMutationLedger) throws -> [String: Any] {
            let url = URL(fileURLWithPath: ledger.claimPath).deletingLastPathComponent()
                .appendingPathComponent("record-\(ledger.sequence).json")
            return try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
        }
        func outcome(_ purpose: MapMutationPurpose = .install, authorized: Bool = true,
                     attempted: Bool = true, completed: Bool = true, result: Int32 = 0,
                     object: UInt32 = 12, session: UInt64 = 42, sequence: UInt32 = 1,
                     kind: UInt32? = nil) -> NativeMutationLedger.Outcome {
            .init(authorized: authorized, attempted: attempted, completed: completed,
                  nativeResult: result, resultingObjectID: object, sessionID: session,
                  sequence: sequence, purpose: purpose.rawValue, kind: kind ?? purpose.kind)
        }
        let operation = NativeMutationOperation(mode: .install, root: root)
        var ledger = try operation.begin(purpose: .install, scope: scope())
        check(try record(ledger)["phase"] as? String == "prepared", "prepared record persisted")
        let savedScope = try record(ledger)["scope"] as! [String: Any]
        check(savedScope["physicalIdentifier"] as? String == "TEST-DEVICE", "local device binding persisted")
        check(savedScope["filename"] as? String == "terento_test_map.img", "exact target persisted")
        check(try record(ledger)["exactPath"] as? String == "/GARMIN/terento_test_map.img", "exact path persisted")
        check(!FileManager.default.fileExists(atPath: ledger.claimPath), "Swift does not consume native claim")
        try ledger.dispatch()
        check(try record(ledger)["phase"] as? String == "dispatched", "dispatch persisted")
        try ledger.finish(outcome(), returnedResult: 0)
        check(try record(ledger)["phase"] as? String == "completed", "coherent outcome completed")
        denied { try ledger.finish(outcome(), returnedResult: 0) }
        denied { _ = try operation.begin(purpose: .install, scope: scope()) }
        let directory = URL(fileURLWithPath: ledger.claimPath).deletingLastPathComponent()
        for (url, expected) in [(directory, 0o700), (directory.appendingPathComponent("record-1.json"), 0o600)] {
            let permissions = try FileManager.default.attributesOfItem(atPath: url.path)[.posixPermissions] as! NSNumber
            check(permissions.intValue & 0o777 == expected, "private evidence permissions")
        }
        let invalid = [outcome(authorized: false), outcome(attempted: false), outcome(completed: false),
            outcome(result: -1), outcome(object: 0), outcome(session: 0), outcome(sequence: 2),
            outcome(.removeManaged), outcome(kind: 2)]
        for value in invalid {
            let op = NativeMutationOperation(mode: .install, root: root)
            var candidate = try op.begin(purpose: .install, scope: scope())
            try candidate.dispatch()
            denied { try candidate.finish(value, returnedResult: 0) }
            check(try record(candidate)["phase"] as? String != "completed", "invalid result retained")
            denied { _ = try op.begin(purpose: .install, scope: scope()) }
        }
        let old = scope("terento_test_old.img", hash: hash)
        let new = scope("terento_test_new.img")
        let update = NativeMutationOperation(mode: .updateNew, root: root)
        try update.bindOldTarget(scope: old)
        var send = try update.begin(purpose: .updateNew, scope: new)
        try send.dispatch()
        try send.finish(outcome(.updateNew), returnedResult: 0)
        try update.markUpdateVerified(filename: new.filename, size: new.size, sha256: hash)
        let marker = URL(fileURLWithPath: send.claimPath).deletingLastPathComponent()
            .appendingPathComponent("\(send.operationID)-verified-new")
        check(try String(contentsOf: marker, encoding: .utf8) == send.operationID, "native verification marker exact")
        var delete = try update.begin(purpose: .updateOld, scope: old)
        check(delete.operationID == send.operationID && delete.sequence == 2, "shared operation ordered steps")
        try delete.dispatch()
        try delete.finish(outcome(.updateOld, sequence: 2), returnedResult: 0)
        denied { _ = try update.begin(purpose: .updateOld, scope: old) }
        for mode in [MapMutationPurpose.removeManaged, .removeExternal] {
            let removal = NativeMutationOperation(mode: mode, root: root)
            var step = try removal.begin(purpose: mode, scope: old)
            try step.dispatch(); try step.finish(outcome(mode), returnedResult: 0)
            denied { _ = try removal.begin(purpose: mode, scope: old) }
        }
        let unordered = NativeMutationOperation(mode: .updateNew, root: root)
        try unordered.bindOldTarget(scope: old)
        denied { _ = try unordered.begin(purpose: .updateOld, scope: old) }
        denied { _ = try unordered.begin(purpose: .updateNew, scope: new) }
        let unbound = NativeMutationOperation(mode: .updateNew, root: root)
        denied { _ = try unbound.begin(purpose: .updateNew, scope: new) }
        let wrongDevice = NativeMutationOperation(mode: .updateNew, root: root)
        try wrongDevice.bindOldTarget(scope: old)
        denied { _ = try wrongDevice.begin(purpose: .updateNew, scope: scope(new.filename, device: "OTHER")) }
        let premature = NativeMutationOperation(mode: .updateNew, root: root)
        try premature.bindOldTarget(scope: old)
        denied { try premature.markUpdateVerified(filename: new.filename, size: new.size, sha256: hash) }
        let failed = NativeMutationOperation(mode: .updateNew, root: root)
        try failed.bindOldTarget(scope: old)
        var failure = try failed.begin(purpose: .updateNew, scope: new)
        try failure.dispatch()
        try failure.finish(outcome(.updateNew, completed: false, result: -1), returnedResult: -1)
        check(try record(failure)["phase"] as? String == "unknown", "interrupted operation unknown")
        denied { try failed.markUpdateVerified(filename: new.filename, size: new.size, sha256: hash) }
        denied { _ = try failed.begin(purpose: .updateOld, scope: old) }
        let abandoned = NativeMutationOperation(mode: .install, root: root)
        _ = try abandoned.begin(purpose: .install, scope: scope())
        denied { _ = try abandoned.begin(purpose: .install, scope: scope()) }
        let duplicate = NativeMutationOperation(mode: .install, root: root)
        var duplicateStep = try duplicate.begin(purpose: .install, scope: scope())
        try duplicateStep.dispatch()
        denied { try duplicateStep.dispatch() }
        denied { try duplicateStep.finish(outcome(), returnedResult: 0) }
        check(try record(duplicateStep)["phase"] as? String == "failed", "invalid transition poisons result")
        let early = NativeMutationOperation(mode: .install, root: root)
        var earlyStep = try early.begin(purpose: .install, scope: scope())
        denied { try earlyStep.finish(outcome(), returnedResult: 0) }
        denied { _ = try early.begin(purpose: .install, scope: scope()) }
        let cleanup = NativeMutationOperation(mode: .cleanup, root: root)
        denied { _ = try cleanup.begin(purpose: .cleanup, scope: old) }
        print("PASS: \(count) lifecycle-scoped native mutation ledger checks")
    }
}
