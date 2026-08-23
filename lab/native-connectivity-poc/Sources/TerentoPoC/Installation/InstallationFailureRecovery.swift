import Foundation

enum InstallationRecoveryCleanup: Equatable, Sendable {
    case none
    case removeExactRemoteObject(objectID: UInt32)
}

struct InstallationRecoveryPlan: Equatable, Sendable {
    let failure: InstallationFailure
    let existingMapMustBePreserved: Bool
    let cleanup: InstallationRecoveryCleanup
    let retryRequiresNewTransaction: Bool
}

struct InstallationFailureRecoveryPolicy: Sendable {
    func plan(
        for failure: InstallationFailure,
        remoteObjectID: UInt32? = nil,
        remoteObjectWasCreated: Bool = false
    ) -> InstallationRecoveryPlan {
        let cleanup: InstallationRecoveryCleanup
        if remoteObjectWasCreated,
           let remoteObjectID,
           remoteObjectID != 0 {
            cleanup = .removeExactRemoteObject(objectID: remoteObjectID)
        } else {
            cleanup = .none
        }

        return InstallationRecoveryPlan(
            failure: failure,
            existingMapMustBePreserved: true,
            cleanup: cleanup,
            retryRequiresNewTransaction: true
        )
    }
}
