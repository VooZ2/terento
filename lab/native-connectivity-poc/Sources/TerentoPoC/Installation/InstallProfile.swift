import Foundation

struct DeviceInstallProfile: Equatable, Sendable {
    let id: String
    let displayName: String
    let manufacturer: String
    let family: String
    let usbVendorId: UInt16
    let usbProductIds: Set<UInt16>
    let modelAliases: [String]
    let targetDirectory: String
    let supportsMapWrite: Bool

    func matches(_ identity: DeviceIdentity) -> Bool {
        guard identity.usbVendorId == usbVendorId,
              usbProductIds.contains(identity.usbProductId),
              identity.manufacturer.compare(
                  manufacturer,
                  options: [.caseInsensitive, .diacriticInsensitive]
              ) == .orderedSame,
              identity.family == Optional(family),
              let canonicalModel = identity.canonicalModel else {
            return false
        }

        return modelAliases
            .map(GarminDeviceModelNormalizer.normalize)
            .contains(GarminDeviceModelNormalizer.normalize(canonicalModel))
    }
}

struct DeviceInstallProfileRegistry: Sendable {
    let profiles: [DeviceInstallProfile]

    static let local = DeviceInstallProfileRegistry(profiles: [
        DeviceInstallProfile(
            id: "garmin-fenix8-amoled-47mm",
            displayName: "Garmin fēnix 8 AMOLED 47mm",
            manufacturer: "Garmin",
            family: "fēnix",
            usbVendorId: 0x091e,
            usbProductIds: [0x51b8],
            modelAliases: ["fēnix 8", "fenix 8"],
            targetDirectory: "/GARMIN",
            supportsMapWrite: true
        )
    ])

    func profile(for identity: DeviceIdentity) -> DeviceInstallProfile? {
        profiles.first { $0.matches(identity) && $0.supportsMapWrite }
    }
}
