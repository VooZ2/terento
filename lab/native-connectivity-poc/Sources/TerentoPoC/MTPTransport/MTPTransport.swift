import Foundation
import LibMTPBridge

struct MTPTransport: Sendable {
    private static let errorCapacity = 1024
    private let operationGate: MTPOperationGate
    private let lifecycleLease: MTPOperationLease?

    init(
        operationGate: MTPOperationGate = .shared,
        lifecycleLease: MTPOperationLease? = nil
    ) {
        self.operationGate = operationGate
        self.lifecycleLease = lifecycleLease
    }

    func readSnapshot() throws -> DeviceSnapshot {
        try operationGate.withOperation(
            kind: lifecycleLease == nil ? .presence : .inventory,
            lifecycleLease: lifecycleLease
        ) {
            try readSnapshotUncoordinated()
        }
    }

    private func readSnapshotUncoordinated() throws -> DeviceSnapshot {
        var rawSnapshot = TerentoMTPDeviceSnapshot()
        var errorBuffer = [CChar](repeating: 0, count: Self.errorCapacity)

        let result = errorBuffer.withUnsafeMutableBufferPointer { errorPointer in
            withUnsafeMutablePointer(to: &rawSnapshot) { snapshotPointer in
                terento_mtp_read_snapshot(
                    snapshotPointer,
                    errorPointer.baseAddress,
                    errorPointer.count
                )
            }
        }

        defer {
            terento_mtp_free_snapshot(&rawSnapshot)
        }

        guard result == 0 else {
            let message = errorBuffer.withUnsafeBufferPointer { buffer in
                let bytes = buffer.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }
                return String(decoding: bytes, as: UTF8.self)
            }
            throw MTPTransportError.readFailed(
                message.isEmpty ? "Unknown MTP error" : message
            )
        }

        let storages: [StorageInfo]
        if let storagePointer = rawSnapshot.storages {
            storages = (0..<Int(rawSnapshot.storage_count)).map { index in
                let storage = storagePointer[index]
                return StorageInfo(
                    id: storage.storage_id,
                    description: string(from: storage.storage_description, fallback: "Storage"),
                    volumeIdentifier: string(from: storage.volume_identifier, fallback: ""),
                    maximumCapacity: storage.max_capacity,
                    freeSpace: storage.free_space_in_bytes
                )
            }
        } else {
            storages = []
        }

        return DeviceSnapshot(
            manufacturer: string(from: rawSnapshot.manufacturer, fallback: "Garmin"),
            model: string(from: rawSnapshot.model, fallback: "Garmin smartwatch"),
            deviceVersion: string(from: rawSnapshot.device_version, fallback: "Unknown"),
            vendorID: rawSnapshot.vendor_id,
            productID: rawSnapshot.product_id,
            storages: storages
        )
    }

    func readFileInventory() throws -> [DeviceFile] {
        try operationGate.withOperation(
            kind: lifecycleLease == nil ? .inventory : .inventory,
            lifecycleLease: lifecycleLease
        ) {
            try readFileInventoryUncoordinated()
        }
    }

    private func readFileInventoryUncoordinated() throws -> [DeviceFile] {
        var rawInventory = TerentoMTPFileInventory()
        var errorBuffer = [CChar](repeating: 0, count: Self.errorCapacity)

        let result = errorBuffer.withUnsafeMutableBufferPointer { errorPointer in
            withUnsafeMutablePointer(to: &rawInventory) { inventoryPointer in
                terento_mtp_read_file_inventory(
                    inventoryPointer,
                    errorPointer.baseAddress,
                    errorPointer.count
                )
            }
        }

        defer {
            terento_mtp_free_file_inventory(&rawInventory)
        }

        guard result == 0 else {
            throw MTPTransportError.readFailed(errorMessage(from: errorBuffer))
        }

        guard let filePointer = rawInventory.files else {
            return []
        }

        return (0..<Int(rawInventory.file_count)).map { index in
            let file = filePointer[index]
            return DeviceFile(
                itemID: file.item_id,
                parentID: file.parent_id,
                storageID: file.storage_id,
                path: string(from: file.path, fallback: "/"),
                filename: string(from: file.filename, fallback: "Unknown"),
                sizeBytes: file.size_bytes,
                isFolder: file.is_folder != 0
            )
        }
    }

    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8] {
        try operationGate.withOperation(
            kind: lifecycleLease == nil ? .inventory : .inventory,
            lifecycleLease: lifecycleLease
        ) {
            try readFilePrefixUncoordinated(for: file, maxLength: maxLength)
        }
    }

    private func readFilePrefixUncoordinated(for file: DeviceFile, maxLength: Int) throws -> [UInt8] {
        guard maxLength > 0, maxLength <= Int(UInt32.max) else {
            throw MTPTransportError.readFailed("File prefix length is invalid")
        }

        var rawBuffer = TerentoMTPByteBuffer()
        var errorBuffer = [CChar](repeating: 0, count: Self.errorCapacity)

        let result = errorBuffer.withUnsafeMutableBufferPointer { errorPointer in
            withUnsafeMutablePointer(to: &rawBuffer) { bufferPointer in
                terento_mtp_read_file_prefix(
                    file.itemID,
                    0,
                    UInt32(maxLength),
                    bufferPointer,
                    errorPointer.baseAddress,
                    errorPointer.count
                )
            }
        }

        defer {
            terento_mtp_free_byte_buffer(&rawBuffer)
        }

        guard result == 0 else {
            throw MTPTransportError.readFailed(errorMessage(from: errorBuffer))
        }

        guard let bytes = rawBuffer.bytes, rawBuffer.byte_count > 0 else {
            return []
        }

        return Array(UnsafeBufferPointer(start: bytes, count: rawBuffer.byte_count))
    }

    func readFilePrefixes(
        for files: [DeviceFile],
        maxLength: Int
    ) throws -> [UInt32: [UInt8]] {
        try operationGate.withOperation(
            kind: lifecycleLease == nil ? .inventory : .inventory,
            lifecycleLease: lifecycleLease
        ) {
            try readFilePrefixesUncoordinated(for: files, maxLength: maxLength)
        }
    }

    private func readFilePrefixesUncoordinated(
        for files: [DeviceFile],
        maxLength: Int
    ) throws -> [UInt32: [UInt8]] {
        guard maxLength > 0, maxLength <= Int(UInt32.max) else {
            throw MTPTransportError.readFailed("File prefix length is invalid")
        }

        guard !files.isEmpty else {
            return [:]
        }

        let itemIDs = files.map(\.itemID)
        var rawBuffers = [TerentoMTPByteBuffer](
            repeating: TerentoMTPByteBuffer(),
            count: files.count
        )
        var errorBuffer = [CChar](repeating: 0, count: Self.errorCapacity)

        let result = itemIDs.withUnsafeBufferPointer { itemPointer in
            rawBuffers.withUnsafeMutableBufferPointer { bufferPointer in
                errorBuffer.withUnsafeMutableBufferPointer { errorPointer in
                    terento_mtp_read_file_prefixes(
                        itemPointer.baseAddress,
                        itemPointer.count,
                        UInt32(maxLength),
                        bufferPointer.baseAddress,
                        errorPointer.baseAddress,
                        errorPointer.count
                    )
                }
            }
        }

        defer {
            rawBuffers.withUnsafeMutableBufferPointer { bufferPointer in
                for index in bufferPointer.indices {
                    terento_mtp_free_byte_buffer(&bufferPointer[index])
                }
            }
        }

        guard result == 0 else {
            throw MTPTransportError.readFailed(errorMessage(from: errorBuffer))
        }

        var prefixes: [UInt32: [UInt8]] = [:]
        for (index, file) in files.enumerated() {
            let rawBuffer = rawBuffers[index]
            guard let bytes = rawBuffer.bytes, rawBuffer.byte_count > 0 else {
                continue
            }
            prefixes[file.itemID] = Array(
                UnsafeBufferPointer(start: bytes, count: rawBuffer.byte_count)
            )
        }
        return prefixes
    }

    private func string(from pointer: UnsafeMutablePointer<CChar>?, fallback: String) -> String {
        guard let pointer else {
            return fallback
        }
        let value = String(cString: UnsafePointer(pointer))
        return value.isEmpty ? fallback : value
    }

    private func errorMessage(from buffer: [CChar]) -> String {
        buffer.withUnsafeBufferPointer { buffer in
            let bytes = buffer.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }
            let message = String(decoding: bytes, as: UTF8.self)
            return message.isEmpty ? "Unknown MTP error" : message
        }
    }
}

/// Read-only device presence boundary used by the lifecycle state manager.
/// Each bridge call opens and releases its own MTP handle, so no long-lived
/// session or write-capable operation is exposed here.
protocol DeviceSnapshotReader: Sendable {
    func readSnapshot() throws -> DeviceSnapshot
}

extension MTPTransport: DeviceSnapshotReader {}

protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

extension DeviceFileReader {
    func readFilePrefixes(
        for files: [DeviceFile],
        maxLength: Int
    ) throws -> [UInt32: [UInt8]] {
        var prefixes: [UInt32: [UInt8]] = [:]
        for file in files {
            prefixes[file.itemID] = try readFilePrefix(for: file, maxLength: maxLength)
        }
        return prefixes
    }
}

extension MTPTransport: DeviceFileReader {}

enum MTPTransportError: LocalizedError, Sendable {
    case readFailed(String)

    var errorDescription: String? {
        switch self {
        case .readFailed(let message):
            return message
        }
    }
}
