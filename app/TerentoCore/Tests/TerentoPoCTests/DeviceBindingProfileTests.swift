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
