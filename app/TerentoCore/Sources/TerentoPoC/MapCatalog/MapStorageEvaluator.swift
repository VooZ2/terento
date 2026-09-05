import Foundation

enum MapStorageStatus: String, Sendable, Equatable {
    case enoughSpace = "ENOUGH_SPACE"
    case notEnoughSpace = "NOT_ENOUGH_SPACE"

    var userLabel: String {
        switch self {
        case .enoughSpace:
            return "Enough space"
        case .notEnoughSpace:
            return "Not enough space"
        }
    }
}

struct MapStorageEvaluation: Sendable, Equatable {
    let status: MapStorageStatus
    let availableBytes: UInt64
    let requiredBytes: UInt64

    var hasEnoughSpace: Bool {
        status == .enoughSpace
    }
}

struct MapStorageEvaluator: Sendable {
    func evaluate(availableSpace: UInt64, selectedMapSize: UInt64) -> MapStorageEvaluation {
        MapStorageEvaluation(
            status: availableSpace >= selectedMapSize ? .enoughSpace : .notEnoughSpace,
            availableBytes: availableSpace,
            requiredBytes: selectedMapSize
        )
    }
}
