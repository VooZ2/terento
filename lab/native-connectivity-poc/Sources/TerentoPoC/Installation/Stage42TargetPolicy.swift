import Foundation

enum Stage42TargetPolicyError: LocalizedError, Equatable, Sendable {
    case policyConfigurationInvalid
    case unsupportedPackage
    case unsupportedVersion
    case unsupportedFilename
    case unsupportedDeviceProfile

    var errorDescription: String? {
        switch self {
        case .policyConfigurationInvalid:
            return "The map installation target policy is incomplete."
        case .unsupportedPackage:
            return "Only validated Freizeitkarte catalog packages are enabled for this installation path."
        case .unsupportedVersion:
            return "The selected map version does not match the validated source artifact."
        case .unsupportedFilename:
            return "The selected map filename is not a valid Terento-managed target."
        case .unsupportedDeviceProfile:
            return "This device does not match the validated Terento installation profile."
        }
    }
}

/// Swift-side fail-closed policy for catalog-driven writes. The C bridge has a
/// matching filename grammar check, but invalid input must be rejected before
/// any transport call is reached.
struct Stage42TargetPolicy: Sendable {
    static let allowedProvider = "freizeitkarte"

    func validate(
        package: MapPackage,
        artifact: ValidatedMapArtifact,
        profile: DeviceInstallProfile?,
        identity: DeviceIdentity,
        deviceFiles: [DeviceFile]
    ) throws {
        guard !package.id.isEmpty,
              MapIdentity.normalizeProvider(package.providerId) == Self.allowedProvider,
              !package.regionId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              artifact.catalogPackageID == package.id,
              MapIdentity.normalizeProvider(artifact.provider) == Self.allowedProvider,
              let expectedIdentity = package.identity,
              MapIdentity.normalizeRegion(artifact.region)
                == expectedIdentity.region else {
            throw Stage42TargetPolicyError.unsupportedPackage
        }

        guard package.version == artifact.version else {
            throw Stage42TargetPolicyError.unsupportedVersion
        }

        let expectedFilename = try TerentoManagedFilenameGenerator().filename(
            providerId: package.providerId,
            regionId: package.canonicalRegionId
        )
        guard artifact.targetFilename == expectedFilename,
              TerentoManagedFilenameGenerator().isValid(artifact.targetFilename) else {
            throw Stage42TargetPolicyError.unsupportedFilename
        }

        guard identity.usbVendorId == 0x091e,
              GarminMapCapabilityRegistry.local.evaluate(identity: identity).canUseTerentoMaps,
              DeviceInstallProfileRegistry.hasSingleGarminRootFolder(in: deviceFiles),
              let profile,
              profile.matches(identity),
              profile.targetDirectory == "/GARMIN",
              profile.supportsMapWrite else {
            throw Stage42TargetPolicyError.unsupportedDeviceProfile
        }
    }
}
