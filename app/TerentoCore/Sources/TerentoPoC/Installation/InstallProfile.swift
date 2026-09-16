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
    var requiresValidatedCanonicalModel: Bool = true

    func matches(_ identity: DeviceIdentity) -> Bool {
        guard identity.usbVendorId == usbVendorId,
              (usbProductIds.isEmpty || usbProductIds.contains(identity.usbProductId)),
              identity.manufacturer.compare(
                  manufacturer,
                  options: [.caseInsensitive, .diacriticInsensitive]
              ) == .orderedSame else {
            return false
        }

        let familyMatches = family == "Garmin"
            || identity.family == Optional(family)
            || (!requiresValidatedCanonicalModel && identity.family == nil)
        guard familyMatches else { return false }

        let model = requiresValidatedCanonicalModel
            ? identity.canonicalModel
            : (identity.catalogCanonicalModel ?? identity.canonicalModel ?? identity.model)
        guard let model, !GarminDeviceModelNormalizer.normalize(model).isEmpty else {
            return false
        }

        return modelAliases.isEmpty
            || modelAliases
                .map(GarminDeviceModelNormalizer.normalize)
                .contains(GarminDeviceModelNormalizer.normalize(model))
    }
}

/// Per-operation production authorization. Unlike compatibility identity, all
/// values here come from the live snapshot and can be compared again by C
/// after it opens the device in a new MTP session.
struct DeviceMapOperationProfile: Codable, Equatable, Sendable {
    static let currentVersion: UInt32 = 1

    let version: UInt32
    let vendorID: UInt16
    let productID: UInt16
    let manufacturer: String
    let rawModel: String
    let targetDirectory: String

    init?(identity: DeviceIdentity, installProfile: DeviceInstallProfile?) {
        guard let installProfile,
              installProfile.supportsMapWrite,
              installProfile.matches(identity),
              installProfile.targetDirectory == "/GARMIN" else {
            return nil
        }

        let manufacturer = identity.manufacturer.trimmingCharacters(in: .whitespacesAndNewlines)
        let rawModel = identity.model.trimmingCharacters(in: .whitespacesAndNewlines)
        guard identity.usbVendorId == 0x091e,
              identity.usbProductId != 0,
              !manufacturer.isEmpty,
              !rawModel.isEmpty,
              manufacturer.utf8.count <= 255,
              rawModel.utf8.count <= 255 else {
            return nil
        }

        self.version = Self.currentVersion
        self.vendorID = identity.usbVendorId
        self.productID = identity.usbProductId
        self.manufacturer = manufacturer
        self.rawModel = rawModel
        self.targetDirectory = installProfile.targetDirectory
    }
}

struct DeviceInstallProfileRegistry: Sendable {
    let profiles: [DeviceInstallProfile]

    /// The registry contains one provider-neutral Garmin template. It is not
    /// a model allowlist. A write profile is bound to the exact live USB
    /// product, model text, and `/GARMIN` inventory by the overload below.
    static let local = DeviceInstallProfileRegistry(profiles: [
        DeviceInstallProfile(
            id: "garmin-live-map-device",
            displayName: "Garmin map device",
            manufacturer: "Garmin",
            family: "Garmin",
            usbVendorId: 0x091e,
            usbProductIds: [],
            modelAliases: [],
            targetDirectory: "/GARMIN",
            supportsMapWrite: true,
            requiresValidatedCanonicalModel: false
        )
    ])

    func profile(for identity: DeviceIdentity) -> DeviceInstallProfile? {
        guard identity.usbProductId != 0,
              !identity.model.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return nil
        }
        return profiles.first { $0.matches(identity) && $0.supportsMapWrite }
    }

    /// Binds a provider-neutral profile to the exact live Garmin identity.
    /// No model list is consulted: a write target is returned only after the
    /// read-only inventory proves that exactly one root `/GARMIN` folder
    /// exists. The safe update transaction performs its own final live
    /// identity, ownership, artifact, storage, and post-write checks.
    func profile(
        for identity: DeviceIdentity,
        deviceFiles: [DeviceFile]
    ) -> DeviceInstallProfile? {
        guard let template = profile(for: identity),
              identity.usbProductId != 0,
              !identity.model.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              Self.hasSingleGarminRootFolder(in: deviceFiles) else {
            return nil
        }

        return DeviceInstallProfile(
            id: "garmin-live-map-device",
            displayName: "Garmin \(identity.model)",
            manufacturer: identity.manufacturer,
            family: identity.family ?? "Garmin",
            usbVendorId: identity.usbVendorId,
            usbProductIds: [identity.usbProductId],
            modelAliases: [identity.catalogCanonicalModel ?? identity.canonicalModel ?? identity.model],
            targetDirectory: template.targetDirectory,
            supportsMapWrite: true,
            requiresValidatedCanonicalModel: false
        )
    }

    static func hasSingleGarminRootFolder(in deviceFiles: [DeviceFile]) -> Bool {
        deviceFiles.filter { file in
            file.isFolder
                && file.path.compare(
                    "/GARMIN",
                    options: [.caseInsensitive, .diacriticInsensitive]
                ) == .orderedSame
                && file.filename.compare(
                    "GARMIN",
                    options: [.caseInsensitive, .diacriticInsensitive]
                ) == .orderedSame
        }.count == 1
    }
}
