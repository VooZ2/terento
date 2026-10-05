import Foundation

@main
struct DeviceBindingProfileTests {
    static func main() throws {
        func identity(_ identifier: String?, _ source: DeviceIdentity.LocalIdentityResolution) -> DeviceIdentity {
            DeviceIdentity(
                manufacturer: "Garmin", model: "fenix 8", family: "fēnix", variant: nil,
                usbVendorId: 0x091e, usbProductId: 0x51b8, firmware: nil,
                storageCapacity: 1_000_000, freeSpace: 900_000,
                localHardwareIdentifier: identifier, localIdentityResolution: source
            )
        }
        func profile(_ identifier: String?, _ source: DeviceIdentity.LocalIdentityResolution, storage: UInt32 = 7) -> DeviceMapOperationProfile? {
            let value = identity(identifier, source)
            return DeviceMapOperationProfile(
                identity: value,
                installProfile: DeviceInstallProfileRegistry.local.profile(for: value),
                expectedStorageID: storage
            )
        }
        let serial = profile("TEST-SERIAL-A", .mtpSerial)!
        precondition(serial.version == 2 && serial.physicalIdentifierSource == 1)
        precondition(serial.physicalIdentifier == "TEST-SERIAL-A" && serial.expectedStorageID == 7)
        let unit = profile("TEST-UNIT-A", .garminUnitID)!
        precondition(unit.physicalIdentifierSource == 2)
        precondition(serial != profile("TEST-SERIAL-B", .mtpSerial))
        precondition(serial != profile("TEST-SERIAL-A", .garminUnitID))
        precondition(profile(nil, .mtpSerial) == nil)
        precondition(profile("", .mtpSerial) == nil)
        precondition(profile("TEST-SERIAL-A", .unavailable) == nil)
        precondition(profile("TEST-SERIAL-A", .mtpSerial, storage: 0) == nil)
        for invalid in [" value", "value ", "ab\u{0}cd", "ab\ncd", String(repeating: "A", count: 256)] {
            precondition(profile(invalid, .mtpSerial) == nil)
        }
        for invalid in ["123", "abcd/ef", "abcd_ef", "abcdé", String(repeating: "A", count: 65)] {
            precondition(profile(invalid, .garminUnitID) == nil)
        }
        // Regression: the accepted root and the write binding must select the same storage.
        let watch = identity("TEST-SERIAL-A", .mtpSerial)
        for name in ["GARMIN", "Garmin", "garmin"] {
            let files = [DeviceFile(itemID: 10, parentID: 0, storageID: 7,
                path: "/\(name)", filename: name, sizeBytes: 0, isFolder: true)]
            let binding = try ResolvedMapWriteProfile.resolve(identity: watch, files: files)
            guard binding.operationProfile.expectedStorageID == 7 else {
                print("FAIL: accepted root \(name) must retain storage 7 in the operation profile")
                exit(1)
            }
        }
        func root(_ name: String = "GARMIN", storage: UInt32 = 7, item: UInt32 = 10, folder: Bool = true) -> DeviceFile {
            DeviceFile(itemID: item, parentID: 0, storageID: storage, path: "/\(name)",
                filename: name, sizeBytes: 0, isFolder: folder)
        }
        func refused(_ files: [DeviceFile], _ reason: MapTargetResolutionError, watch: DeviceIdentity = watch) {
            do {
                _ = try ResolvedMapWriteProfile.resolve(identity: watch, files: files)
                preconditionFailure("accepted invalid target")
            } catch { precondition(error as? MapTargetResolutionError == reason) }
        }
        refused([], .missingRoot)
        refused([root("GÁRMIN")], .missingRoot)
        refused([root("GARMIN", folder: false)], .missingRoot)
        refused([root("other/GARMIN")], .missingRoot)
        refused([root(), root("Garmin", item: 11)], .ambiguousRoot)
        refused([root(), root("Garmin", storage: 8, item: 11)], .ambiguousRoot)
        refused([root(storage: 0)], .invalidStorage)
        refused([root(item: 0)], .invalidRoot)
        refused([root()], .invalidIdentity, watch: identity(nil, .unavailable))
        refused([root()], .invalidIdentity, watch: identity("bad\nserial", .mtpSerial))
        let other = try ResolvedMapWriteProfile.resolve(identity: identity("OTHER-WATCH", .mtpSerial), files: [root()])
        precondition(other.operationProfile != serial)
        let wrongModel = DeviceIdentity(manufacturer: "Other", model: "Other", family: nil, variant: nil,
            usbVendorId: 0x091e, usbProductId: 1, firmware: nil, storageCapacity: 1, freeSpace: 1,
            localHardwareIdentifier: "TEST-SERIAL-A", localIdentityResolution: .mtpSerial)
        refused([root()], .profileMismatch, watch: wrongModel)
        print("PASS: shared target resolver root case, ambiguity, storage, identity, profile and substitution")
        let encoded = try JSONEncoder().encode(serial)
        let decoded = try JSONDecoder().decode(DeviceMapOperationProfile.self, from: encoded)
        precondition(decoded == serial)
        var object = try JSONSerialization.jsonObject(with: encoded) as! [String: Any]
        object.removeValue(forKey: "physicalIdentifier")
        let old = try JSONSerialization.data(withJSONObject: object)
        precondition((try? JSONDecoder().decode(DeviceMapOperationProfile.self, from: old)) == nil)
        print("PASS: local physical identity source, storage, invalid inputs and IPC binding completeness")
    }
}
