import Foundation

private enum Stage52HardwareGateFailure: Error, LocalizedError, CustomStringConvertible {
    case message(String)

    var description: String {
        switch self {
        case .message(let message):
            return message
        }
    }

    var errorDescription: String? {
        description
    }
}

/// Controlled Stage 5.2 physical gate.
///
/// Without `--delete <exact-device-path>` this command only reads the device.
/// Deletion additionally requires typing the exact confirmation phrase shown
/// by the command. Manual removal does not create a local backup.
@main
struct Stage52HardwareDeleteMain {
    private static let expectedVendorID: UInt16 = 0x091e
    private static let expectedProductID: UInt16 = 0x51b8
    private static let previousHardwareGateFirmware = "2243"

    static func main() {
        do {
            try run(arguments: Array(CommandLine.arguments.dropFirst()))
        } catch {
            print("STAGE 5.2 HARDWARE GATE: FAIL")
            print("Reason: \(error.localizedDescription)")
            exit(1)
        }
    }

    private static func run(arguments: [String]) throws {
        let deleteRequested = arguments.contains("--delete")
        let pathArgument = arguments.first { !$0.hasPrefix("--") }

        if deleteRequested && pathArgument == nil {
            throw Stage52HardwareGateFailure.message(
                "Deletion requires the exact device path, for example /GARMIN/terento_freizeitkarte_lva.img. No map was changed."
            )
        }

        print("Stage 5.2 Hardware Gate: controlled exact-map delete test")
        print("Stage 5.2 Hardware Gate: only a manifest-owned Terento map may be selected")

        let transport = MTPTransport()
        let snapshot = try transport.readSnapshot()
        let identity = GarminDeviceIdentityAdapter().makeIdentity(from: snapshot)

        print("Device: \(identity.manufacturer) \(identity.model)")
        print(String(format: "VID/PID: 0x%04x / 0x%04x", identity.usbVendorId, identity.usbProductId))
        print("Firmware: \(identity.firmware ?? "Unknown")")

        guard identity.usbVendorId == Self.expectedVendorID,
              identity.usbProductId == Self.expectedProductID,
              let installProfile = DeviceInstallProfileRegistry.local.profile(for: identity) else {
            throw Stage52HardwareGateFailure.message(
                "The connected device is not the validated fēnix 8 profile. No map was changed."
            )
        }

        print("Install profile: \(installProfile.displayName) → \(installProfile.targetDirectory)")
        if identity.firmware != Self.previousHardwareGateFirmware {
            print(
                "Firmware variation: \(identity.firmware ?? "Unknown") "
                    + "(previous Stage 5.2 hardware evidence: \(Self.previousHardwareGateFirmware))"
            )
        }

        let beforeInventory = try transport.readFileInventory()
        let manifest = try loadManifest(for: identity)
        let candidates = manifest.entries.filter { entry in
            guard pathArgument == nil || entry.devicePath == pathArgument else {
                return false
            }

            return beforeInventory.contains { file in
                !file.isFolder
                    && file.path == entry.devicePath
                    && file.filename == entry.filename
                    && file.sizeBytes == entry.sizeBytes
            }
        }

        guard candidates.count == 1, let entry = candidates.first else {
            let requested = pathArgument.map { " for \($0)" } ?? ""
            throw Stage52HardwareGateFailure.message(
                "The local manifest did not resolve exactly one installed Terento-managed map\(requested). No map was changed."
            )
        }

        guard let deviceFile = beforeInventory.first(where: { file in
            !file.isFolder
                && file.path == entry.devicePath
                && file.filename == entry.filename
                && file.sizeBytes == entry.sizeBytes
        }) else {
            throw Stage52HardwareGateFailure.message(
                "The exact manifest-owned map disappeared before validation. No map was changed."
            )
        }

        guard let mapIdentity = MapIdentity(
            provider: entry.providerId,
            region: entry.regionId
        ) else {
            throw Stage52HardwareGateFailure.message(
                "The manifest map identity is incomplete. No map was changed."
            )
        }

        print("Map identity: \(mapIdentity.provider) / \(mapIdentity.region)")
        print("Ownership: TERENTO_MANAGED")
        print("Exact target: \(entry.devicePath)")
        print("Object ID: \(deviceFile.itemID)")
        print("Object size: \(deviceFile.sizeBytes) bytes")
        print("Manifest SHA-256: \(entry.sha256)")

        guard deleteRequested else {
            print("Read-only preflight: PASS")
            print("No local backup was created.")
            print("No DeleteObject operation was executed.")
            print("STAGE 5.2 HARDWARE GATE: READY_FOR_CONFIRMATION")
            print("To execute the delete gate later, rerun with --delete \(entry.devicePath)")
            return
        }

        print("WARNING: this will remove only the exact Terento-managed object above.")
        print("Type DELETE \(entry.devicePath) to continue:")
        guard readLine() == "DELETE \(entry.devicePath)" else {
            throw Stage52HardwareGateFailure.message(
                "The exact confirmation phrase was not entered. No map was changed."
            )
        }

        let target = SafeDeleteTarget(
            deviceKey: identity.localManifestDeviceKey,
            mapIdentity: mapIdentity,
            ownership: .managedByTerento,
            objectID: deviceFile.itemID,
            expectedPath: entry.devicePath,
            expectedFilename: entry.filename,
            expectedSizeBytes: entry.sizeBytes,
            expectedSHA256: entry.sha256,
            backup: nil
        )

        let result = MapLifecycleManager().delete(
            target: target,
            confirmed: true,
            deviceConnected: true,
            rescan: {
                try transport.readFileInventory().map {
                    InstalledMapFile(
                        path: $0.path,
                        filename: $0.filename,
                        sizeBytes: $0.sizeBytes,
                        itemID: $0.itemID
                    )
                }
            },
            transport: MTPSafeDeleteTransport(),
            requiresVerifiedBackup: false
        )

        guard result.isSuccess else {
            throw Stage52HardwareGateFailure.message(result.message)
        }

        let afterInventory = try transport.readFileInventory()
        guard !afterInventory.contains(where: { file in
            file.itemID == deviceFile.itemID || file.path == entry.devicePath
        }) else {
            throw Stage52HardwareGateFailure.message(
                "The exact target was still present after deletion verification."
            )
        }

        let beforeOtherFiles = inventorySignature(
            beforeInventory.filter { $0.itemID != deviceFile.itemID && $0.path != entry.devicePath }
        )
        let afterOtherFiles = inventorySignature(
            afterInventory.filter { $0.itemID != deviceFile.itemID && $0.path != entry.devicePath }
        )
        guard beforeOtherFiles == afterOtherFiles else {
            throw Stage52HardwareGateFailure.message(
                "A device object other than the explicitly requested target changed."
            )
        }

        print("MTP operations executed:")
        print("- read device snapshot")
        print("- read file inventory")
        print("- read exact object metadata for pre-delete identity verification")
        print("- DeleteObject for the exact manifest-owned object ID only")
        print("- read file inventory for post-delete verification")
        print("SendObject / MoveObject / RenameObject: none")
        print("Other Garmin/device files changed: none")
        print("Deleted target absent after rescan: PASS")
        print("STAGE 5.2 HARDWARE GATE: PASS")
    }

    private static func loadManifest(for identity: DeviceIdentity) throws -> TerentoManifest {
        guard let manifest = try LocalTerentoManifestStore().read(
            deviceKey: identity.localManifestDeviceKey
        ) else {
            throw Stage52HardwareGateFailure.message(
                "No local Terento ownership manifest exists for this device. No map was changed."
            )
        }

        return manifest
    }

    private static func inventorySignature(_ files: [DeviceFile]) -> [String] {
        files.map { file in
            "\(file.storageID):\(file.itemID):\(file.parentID):\(file.path):\(file.filename):\(file.sizeBytes):\(file.isFolder)"
        }.sorted()
    }
}
