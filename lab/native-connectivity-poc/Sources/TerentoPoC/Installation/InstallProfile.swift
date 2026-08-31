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
              usbProductIds.contains(identity.usbProductId),
              identity.manufacturer.compare(
                  manufacturer,
                  options: [.caseInsensitive, .diacriticInsensitive]
              ) == .orderedSame,
              let canonicalModel = requiresValidatedCanonicalModel
                ? identity.canonicalModel
                : identity.catalogCanonicalModel else {
            return false
        }

        let familyMatches = identity.family == Optional(family)
            || (!requiresValidatedCanonicalModel
                && identity.family == nil
                && family == "Garmin")
        guard familyMatches else { return false }

        return modelAliases
            .map(GarminDeviceModelNormalizer.normalize)
            .contains(GarminDeviceModelNormalizer.normalize(canonicalModel))
    }
}

/// Per-operation production authorization. Unlike compatibility identity, all
/// values here come from the live snapshot and can be compared again by C
/// after it opens the device in a new MTP session.
struct DeviceMapOperationProfile: Equatable, Sendable {
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

    /// Beta enrollment path for a newly connected Garmin smartwatch. It does
    /// not generalize from another device's USB product ID: the generated
    /// profile is bound to the exact live VID/PID, catalog model and family.
    /// A write target is returned only after the read-only inventory proves
    /// that exactly one root `/GARMIN` folder exists.
    func profile(
        for identity: DeviceIdentity,
        deviceFiles: [DeviceFile]
    ) -> DeviceInstallProfile? {
        let family = identity.family ?? "Garmin"
        guard identity.usbVendorId == 0x091e,
              identity.manufacturer.range(
                  of: "garmin",
                  options: [.caseInsensitive, .diacriticInsensitive]
              ) != nil,
              GarminMapCapabilityRegistry.local.evaluate(identity: identity).canAttemptTerentoMapInstall,
              let canonicalModel = identity.catalogCanonicalModel,
              Self.hasSingleGarminRootFolder(in: deviceFiles) else {
            return nil
        }

        return DeviceInstallProfile(
            id: "garmin-map-capable-beta",
            displayName: "Garmin \(identity.model)",
            manufacturer: identity.manufacturer,
            family: family,
            usbVendorId: identity.usbVendorId,
            usbProductIds: [identity.usbProductId],
            modelAliases: [canonicalModel],
            targetDirectory: "/GARMIN",
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
