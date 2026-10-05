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
    static let currentVersion: UInt32 = 2

    let version: UInt32
    let vendorID: UInt16
    let productID: UInt16
    let manufacturer: String
    let rawModel: String
    let targetDirectory: String
    /// Sensitive local-only binding. Never include this profile in diagnostics.
    let physicalIdentifier: String
    let physicalIdentifierSource: UInt32
    let expectedStorageID: UInt32

    init?(
        identity: DeviceIdentity,
        installProfile: DeviceInstallProfile?,
        expectedStorageID: UInt32
    ) {
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

        guard expectedStorageID != 0,
              let identifier = identity.localHardwareIdentifier,
              Self.validPhysicalIdentifier(identifier, source: identity.localIdentityResolution) else {
            return nil
        }

        self.physicalIdentifier = identifier
        self.physicalIdentifierSource = identity.localIdentityResolution == .mtpSerial ? 1 : 2
        self.expectedStorageID = expectedStorageID
        self.version = Self.currentVersion
        self.vendorID = identity.usbVendorId
        self.productID = identity.usbProductId
        self.manufacturer = manufacturer
        self.rawModel = rawModel
        self.targetDirectory = installProfile.targetDirectory
    }

    fileprivate static func validPhysicalIdentifier(
        _ value: String,
        source: DeviceIdentity.LocalIdentityResolution
    ) -> Bool {
        guard value == value.trimmingCharacters(in: .whitespacesAndNewlines),
              !value.isEmpty, value.utf8.count <= 255,
              !value.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }) else {
            return false
        }
        switch source {
        case .mtpSerial:
            return true
        case .garminUnitID:
            return (4...64).contains(value.count) && value.allSatisfy {
                $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "-")
            }
        case .unavailable:
            return false
        }
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
        (try? GarminMapTarget.resolve(in: deviceFiles)) != nil
    }
}

/// Fixed local-only reasons; error values contain no device identifiers or paths.
enum MapTargetResolutionError: String, Error, LocalizedError, Sendable {
    case missingRoot = "root_missing"
    case ambiguousRoot = "root_ambiguous"
    case invalidStorage = "storage_invalid"
    case invalidRoot = "root_invalid"
    case invalidIdentity = "identity_invalid"
    case profileMismatch = "profile_mismatch"

    var errorDescription: String? {
        "Terento could not verify a safe place to install maps. Reconnect your device and try again."
    }
}

/// A unique root, not a model allowlist. The native inventory exposes a canonical
/// path for this root's storage only; filename and all other object facts stay exact.
struct GarminMapTarget: Equatable, Sendable {
    let root: DeviceFile

    static func resolve(in files: [DeviceFile]) throws -> Self {
        let candidates = files.filter {
            $0.isFolder && asciiGarmin($0.filename)
                && $0.path.first == "/" && asciiGarmin(String($0.path.dropFirst()))
        }
        guard !candidates.isEmpty else { throw MapTargetResolutionError.missingRoot }
        guard candidates.count == 1 else { throw MapTargetResolutionError.ambiguousRoot }
        let root = candidates[0]
        guard root.storageID != 0 else { throw MapTargetResolutionError.invalidStorage }
        guard root.itemID != 0 else { throw MapTargetResolutionError.invalidRoot }
        return Self(root: root)
    }

    private static func asciiGarmin(_ text: String) -> Bool {
        let bytes = Array(text.utf8)
        return bytes.count == 6 && zip(bytes, "GARMIN".utf8).allSatisfy {
            ($0.0 >= 97 && $0.0 <= 122 ? $0.0 - 32 : $0.0) == $0.1
        }
    }
}

struct ResolvedMapWriteProfile: Sendable {
    let target: GarminMapTarget
    let installProfile: DeviceInstallProfile
    let operationProfile: DeviceMapOperationProfile

    static func resolve(identity: DeviceIdentity, files: [DeviceFile]) throws -> Self {
        let target = try GarminMapTarget.resolve(in: files)
        guard let identifier = identity.localHardwareIdentifier,
              DeviceMapOperationProfile.validPhysicalIdentifier(identifier, source: identity.localIdentityResolution)
        else { throw MapTargetResolutionError.invalidIdentity }
        guard let install = DeviceInstallProfileRegistry.local.profile(for: identity, deviceFiles: files),
              let operation = DeviceMapOperationProfile(identity: identity, installProfile: install,
                  expectedStorageID: target.root.storageID)
        else { throw MapTargetResolutionError.profileMismatch }
        return Self(target: target, installProfile: install, operationProfile: operation)
    }
}
