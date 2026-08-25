import Foundation

struct DeviceRegistryEntry: Sendable, Equatable {
    let displayName: String
    let manufacturer: String
    let modelAliases: [String]
    let family: String
    let usbVendorId: UInt16
    let usbProductIds: Set<UInt16>
    let caseSizeMm: Int?
    let displayType: String?
    let status: CompatibilityStatus
    let evidence: CompatibilityEvidence

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

        if let caseSizeMm, identity.caseSizeMm != caseSizeMm { return false }
        if let displayType,
           identity.displayType?.caseInsensitiveCompare(displayType) != .orderedSame {
            return false
        }

        return modelAliases
            .map(GarminDeviceModelNormalizer.normalize)
            .contains(GarminDeviceModelNormalizer.normalize(canonicalModel))
    }
}

struct DeviceRegistry: Sendable {
    let entries: [DeviceRegistryEntry]

    static let local = DeviceRegistry(entries: [
        DeviceRegistryEntry(
            displayName: "Garmin fēnix 8",
            manufacturer: "Garmin",
            modelAliases: ["fēnix 8", "fenix 8"],
            family: "fēnix",
            usbVendorId: 0x091e,
            usbProductIds: [0x51b8],
            caseSizeMm: 47,
            // The transport identity sometimes reports only 47 mm; do not
            // infer AMOLED when the device did not expose display evidence.
            displayType: nil,
            status: .tested,
            evidence: .nativeConnectivityTested
        )
    ])

    func entry(for identity: DeviceIdentity) -> DeviceRegistryEntry? {
        entries.first { $0.matches(identity) }
    }
}
