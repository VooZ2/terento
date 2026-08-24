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
    // Kept as compatibility constants for the Stage 4.2 regression fixtures.
    // They are no longer used as a production allowlist.
    static let expectedPackageID = "freizeitkarte-lva"
    static let expectedProvider = "freizeitkarte"
    static let expectedRegion = "LVA"
    static let expectedProfileID = "garmin-fenix8-amoled-47mm"
    static let expectedFilename = "terento_freizeitkarte_lva.img"
    static let expectedVersion = MapVersion(year: 2026, month: 5)

    func validate(
        package: MapPackage,
        artifact: ValidatedMapArtifact,
        profile: DeviceInstallProfile?
    ) throws {
        guard !package.id.isEmpty,
              MapIdentity.normalizeProvider(package.providerId) == Self.expectedProvider,
              !package.regionId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              artifact.catalogPackageID == package.id,
              MapIdentity.normalizeProvider(artifact.provider) == Self.expectedProvider,
              MapIdentity.normalizeRegion(artifact.region)
                == MapIdentity.normalizeRegion(package.regionId) else {
            throw Stage42TargetPolicyError.unsupportedPackage
        }

        guard package.version == artifact.version else {
            throw Stage42TargetPolicyError.unsupportedVersion
        }

        let expectedFilename = try TerentoManagedFilenameGenerator().filename(
            providerId: package.providerId,
            regionId: package.regionId
        )
        guard artifact.targetFilename == expectedFilename,
              TerentoManagedFilenameGenerator().isValid(artifact.targetFilename) else {
            throw Stage42TargetPolicyError.unsupportedFilename
        }

        guard profile?.id == Self.expectedProfileID,
              profile?.targetDirectory == "/GARMIN",
              profile?.supportsMapWrite == true else {
            throw Stage42TargetPolicyError.unsupportedDeviceProfile
        }
    }
}
