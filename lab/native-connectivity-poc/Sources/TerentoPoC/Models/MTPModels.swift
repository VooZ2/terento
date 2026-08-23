import Foundation

struct DeviceSnapshot: Sendable {
    let manufacturer: String
    let model: String
    let deviceVersion: String
    let vendorID: UInt16
    let productID: UInt16
    let storages: [StorageInfo]

    var totalCapacity: UInt64 {
        storages.reduce(into: UInt64(0)) { total, storage in
            total = total.saturatingAddition(storage.maximumCapacity)
        }
    }

    var freeSpace: UInt64 {
        storages.reduce(into: UInt64(0)) { total, storage in
            total = total.saturatingAddition(storage.freeSpace)
        }
    }
}

struct StorageInfo: Identifiable, Sendable {
    let id: UInt32
    let description: String
    let volumeIdentifier: String
    let maximumCapacity: UInt64
    let freeSpace: UInt64
}

struct DeviceFile: Identifiable, Equatable, Sendable {
    let itemID: UInt32
    let parentID: UInt32
    let storageID: UInt32
    let path: String
    let filename: String
    let sizeBytes: UInt64
    let isFolder: Bool

    var id: String {
        "\(storageID):\(itemID)"
    }
}

private extension UInt64 {
    func saturatingAddition(_ value: UInt64) -> UInt64 {
        let result = addingReportingOverflow(value)
        return result.overflow ? UInt64.max : result.partialValue
    }
}
