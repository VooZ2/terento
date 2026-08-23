import Foundation

enum StorageGateStatus: String, Equatable, Sendable {
    case allowed = "ALLOWED"
    case blockedInsufficientSpace = "INSTALL_BLOCKED_INSUFFICIENT_SPACE"
    case blockedUnknownInstallSize = "INSTALL_BLOCKED_UNKNOWN_INSTALL_SIZE"
}

struct StoragePlan: Equatable, Sendable {
    let currentFreeSpace: UInt64
    let selectedMapBytes: UInt64
    let requiredTemporarySpace: UInt64
    let safetyReserve: UInt64
    let projectedFreeSpace: UInt64
    let status: StorageGateStatus
    let hasUnresolvedInstallSize: Bool

    var isAllowed: Bool {
        status == .allowed
    }
}

struct StoragePlanner: Sendable {
    static let defaultSafetyReserve: UInt64 = 1 * 1024 * 1024 * 1024

    let safetyReserve: UInt64

    init(safetyReserve: UInt64 = StoragePlanner.defaultSafetyReserve) {
        self.safetyReserve = safetyReserve
    }

    /// The conservative update strategy keeps the old map until the new
    /// transfer is verified, so the selected package remains temporary space
    /// that must be available in full.
    func plan(currentFreeSpace: UInt64, selectedMapSizes: [UInt64]) -> StoragePlan {
        plan(
            currentFreeSpace: currentFreeSpace,
            selectedMapSizes: selectedMapSizes.map(Optional.some)
        )
    }

    /// A catalog download size is not a Garmin IMG install size. Unknown
    /// install sizes are therefore preserved as unknown and cannot pass the
    /// storage gate by using a package/archive-size fallback.
    func plan(currentFreeSpace: UInt64, selectedMapSizes: [UInt64?]) -> StoragePlan {
        let (selectedMapBytes, selectedOverflow) = selectedMapSizes.reduce(
            into: (UInt64(0), false)
        ) { result, optionalSize in
            guard let size = optionalSize else {
                return
            }

            let addition = result.0.addingReportingOverflow(size)
            result.0 = addition.overflow ? UInt64.max : addition.partialValue
            result.1 = result.1 || addition.overflow
        }

        let hasUnresolvedInstallSize = selectedMapSizes.contains { $0 == nil }

        let projectedFreeSpace = currentFreeSpace >= selectedMapBytes
            ? currentFreeSpace - selectedMapBytes
            : 0
        let hasReserve = !selectedOverflow && projectedFreeSpace >= safetyReserve
        let status: StorageGateStatus
        if hasUnresolvedInstallSize {
            status = .blockedUnknownInstallSize
        } else if hasReserve {
            status = .allowed
        } else {
            status = .blockedInsufficientSpace
        }

        return StoragePlan(
            currentFreeSpace: currentFreeSpace,
            selectedMapBytes: selectedMapBytes,
            requiredTemporarySpace: selectedMapBytes,
            safetyReserve: safetyReserve,
            projectedFreeSpace: projectedFreeSpace,
            status: status,
            hasUnresolvedInstallSize: hasUnresolvedInstallSize
        )
    }
}
