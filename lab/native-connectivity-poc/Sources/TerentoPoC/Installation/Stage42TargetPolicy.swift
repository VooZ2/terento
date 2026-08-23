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
            return "The validated Stage 4.2 target policy is incomplete."
        case .unsupportedPackage:
            return "Only the validated Freizeitkarte Latvia package is enabled for this installation path."
        case .unsupportedVersion:
            return "The selected map version is not the validated Stage 4.2 release."
        case .unsupportedFilename:
            return "The selected map filename is not the validated Terento target."
        case .unsupportedDeviceProfile:
            return "This device does not match the validated Stage 4.2 installation profile."
        }
    }
}

/// Swift-side allowlist for the first real write path. The C bridge has a
/// matching fail-safe check, but invalid input must be rejected before any
/// transport call is reached.
struct Stage42TargetPolicy: Sendable {
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
        guard let expectedVersion = Self.expectedVersion else {
            throw Stage42TargetPolicyError.policyConfigurationInvalid
        }

        guard package.id == Self.expectedPackageID,
              MapIdentity.normalizeProvider(package.providerId) == Self.expectedProvider,
              MapIdentity.normalizeRegion(package.regionId) == Self.expectedRegion,
              artifact.catalogPackageID == Self.expectedPackageID,
              MapIdentity.normalizeProvider(artifact.provider) == Self.expectedProvider,
              MapIdentity.normalizeRegion(artifact.region) == Self.expectedRegion else {
            throw Stage42TargetPolicyError.unsupportedPackage
        }

        guard package.version == expectedVersion, artifact.version == expectedVersion else {
            throw Stage42TargetPolicyError.unsupportedVersion
        }

        guard artifact.targetFilename == Self.expectedFilename else {
            throw Stage42TargetPolicyError.unsupportedFilename
        }

        guard profile?.id == Self.expectedProfileID,
              profile?.targetDirectory == "/GARMIN",
              profile?.supportsMapWrite == true else {
            throw Stage42TargetPolicyError.unsupportedDeviceProfile
        }
    }
}
