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

    // Model identity is resolved from the device and API catalog. This empty
    // compatibility registry supplies no model-specific display override.
    static let local = DeviceRegistry(entries: [])

    func entry(for identity: DeviceIdentity) -> DeviceRegistryEntry? {
        entries.first { $0.matches(identity) }
    }
}
