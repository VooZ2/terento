import CryptoKit
import Darwin
import Foundation

private enum Stage51HardwareTestFailure: Error, CustomStringConvertible {
    case message(String)

    var description: String {
        switch self {
        case .message(let message):
            return message
        }
    }
}

@main
struct Stage51HardwareBackupMain {
    private static let expectedVendorID: UInt16 = 0x091e
    private static let expectedProductID: UInt16 = 0x51b8
    private static let expectedFirmware = "2243"

    static func main() {
        do {
            try run()
        } catch {
            print("STAGE 5.1 HARDWARE GATE: FAIL")
            print("Reason: \(error.localizedDescription)")
            exit(1)
        }
    }

    private static func run() throws {
        let transport = MTPTransport()

        print("Stage 5.1 Hardware Test: read-only mode")
        print("Stage 5.1 Hardware Test: no write, delete, move, or rename operation is available")

        let snapshot = try transport.readSnapshot()
        let identity = GarminDeviceIdentityAdapter().makeIdentity(from: snapshot)

        print("Device: \(identity.manufacturer) \(identity.model)")
        print(String(format: "VID/PID: 0x%04x / 0x%04x", identity.usbVendorId, identity.usbProductId))
        print("Firmware: \(identity.firmware ?? "Unknown")")

        guard identity.usbVendorId == Self.expectedVendorID,
              identity.usbProductId == Self.expectedProductID else {
            throw Stage51HardwareTestFailure.message(
                "The connected device is not the validated fēnix 8 profile. No map was read."
            )
        }

        guard identity.firmware == Self.expectedFirmware else {
            throw Stage51HardwareTestFailure.message(
                "Firmware \(identity.firmware ?? "Unknown") is not the validated hardware-test firmware 2243. No map was read."
            )
        }

        guard let installProfile = DeviceInstallProfileRegistry.local.profile(for: identity),
              let operationProfile = DeviceMapOperationProfile(
                identity: identity,
                installProfile: installProfile
              ) else {
            throw Stage51HardwareTestFailure.message(
                "The connected device could not be bound to the validated live operation profile. No map was read."
            )
        }

        let beforeInventory = try transport.readFileInventory()
        let manifest = try readManifest(for: identity)
        let candidates = manifest.entries.filter { entry in
            beforeInventory.contains { file in
                !file.isFolder
                    && file.path == entry.devicePath
                    && file.filename == entry.filename
                    && file.sizeBytes == entry.sizeBytes
            }
        }

        guard candidates.count == 1, let entry = candidates.first else {
            throw Stage51HardwareTestFailure.message(
                "The local manifest did not resolve exactly one installed Terento-managed map. No map was read."
            )
        }

        guard let deviceFile = beforeInventory.first(where: { file in
            !file.isFolder
                && file.path == entry.devicePath
                && file.filename == entry.filename
                && file.sizeBytes == entry.sizeBytes
        }) else {
            throw Stage51HardwareTestFailure.message(
                "The manifest-owned map disappeared before the read began."
            )
        }

        print("Map: \(entry.providerId) / \(entry.regionId) / \(entry.version)")
        print("Ownership: TERENTO_MANAGED")
        print("Object: \(entry.devicePath) (ID \(deviceFile.itemID), \(deviceFile.sizeBytes) bytes)")

        let installedMap = InstalledMap(
            name: "Freizeitkarte \(entry.regionId)",
            provider: entry.providerId,
            region: entry.regionId,
            family: entry.providerId,
            rawVersion: entry.version.description,
            version: entry.version,
            identifier: nil,
            productId: nil,
            familyId: nil,
            sizeBytes: deviceFile.sizeBytes,
            sourceFile: InstalledMapFile(
                path: deviceFile.path,
                filename: deviceFile.filename,
                sizeBytes: deviceFile.sizeBytes,
                itemID: deviceFile.itemID
            ),
            metadataStatus: .parsed,
            managementState: .managedByTerento
        )

        let lifecycleItem = MapLifecycleItem(
            id: "freizeitkarte:\(entry.regionId.lowercased())",
            title: "Freizeitkarte \(entry.regionId)",
            provider: entry.providerId,
            region: entry.regionId,
            version: entry.version,
            rawVersion: entry.version.description,
            sizeBytes: deviceFile.sizeBytes,
            installedMaps: [installedMap],
            classification: .terentoManaged
        )

        let target = ManagedMapBackupTarget(
            item: lifecycleItem,
            expectedSHA256ByItemID: [deviceFile.itemID: entry.sha256]
        )

        let result = ReadBackupAdapter(
            transport: MTPReadBackupAdapter(operationProfile: operationProfile)
        ).backup(
            target: target,
            onProgress: { progress in
                print(
                    String(
                        format: "Read progress: %.1f%% (%llu / %llu bytes)",
                        progress.fractionCompleted * 100,
                        progress.bytesTransferred,
                        progress.totalBytes
                    )
                )
            }
        )

        guard result.status == .backupSuccess,
              result.files.count == 1,
              let backup = result.files.first else {
            throw Stage51HardwareTestFailure.message(
                "ReadBackupAdapter returned \(result.status.rawValue): \(result.message)"
            )
        }

        let afterInventory = try transport.readFileInventory()
        guard inventorySignature(beforeInventory) == inventorySignature(afterInventory) else {
            throw Stage51HardwareTestFailure.message(
                "The device inventory changed during the read-only backup test."
            )
        }

        print("Backup path: \(backup.localURL.path)")
        print("Backup size: \(backup.sizeBytes) bytes")
        print("Expected/device-object SHA-256: \(entry.sha256)")
        print("Backup SHA-256: \(backup.sha256)")
        print("MTP operations executed:")
        print("- terento_mtp_read_snapshot")
        print("- terento_mtp_read_file_inventory")
        print("- terento_mtp_read_existing_file_to_local")
        print("- terento_mtp_read_file_inventory")
        print("MTP write/delete/move/rename operations executed: none")
        print("Garmin inventory unchanged: PASS")
        print("STAGE 5.1 HARDWARE GATE: PASS")
    }

    private static func readManifest(for identity: DeviceIdentity) throws -> TerentoManifest {
        guard let applicationSupport = FileManager.default.urls(
            for: .applicationSupportDirectory,
            in: .userDomainMask
        ).first else {
            throw Stage51HardwareTestFailure.message(
                "Terento local application data directory is unavailable. No map was read."
            )
        }

        let manifestURL = applicationSupport
            .appendingPathComponent("Terento", isDirectory: true)
            .appendingPathComponent("devices", isDirectory: true)
            .appendingPathComponent(identity.localManifestDeviceKey, isDirectory: true)
            .appendingPathComponent("manifest.json")

        guard FileManager.default.fileExists(atPath: manifestURL.path) else {
            throw Stage51HardwareTestFailure.message(
                "No local Terento ownership manifest exists for this device. No map was read."
            )
        }

        do {
            let data = try Data(contentsOf: manifestURL)
            return try JSONDecoder().decode(TerentoManifest.self, from: data)
        } catch {
            throw Stage51HardwareTestFailure.message(
                "The local Terento ownership manifest could not be read safely. No map was read."
            )
        }
    }

    private static func inventorySignature(_ files: [DeviceFile]) -> [String] {
        files.map { file in
            "\(file.storageID):\(file.itemID):\(file.parentID):\(file.path):\(file.filename):\(file.sizeBytes):\(file.isFolder)"
        }.sorted()
    }
}
