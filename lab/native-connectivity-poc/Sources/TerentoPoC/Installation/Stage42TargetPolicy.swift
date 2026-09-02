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
            return "Only validated map sources are enabled for this installation path."
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
    private let providerRegistry: MapProviderRegistry

    init(providerRegistry: MapProviderRegistry = .bundled) {
        self.providerRegistry = providerRegistry
    }

    func validate(
        package: MapPackage,
        artifact: ValidatedMapArtifact,
        profile: DeviceInstallProfile?,
        identity: DeviceIdentity,
        deviceFiles: [DeviceFile]
    ) throws {
        if package.sourceKind == .custom {
            try validateCustom(package: package, artifact: artifact)
        } else {
            try validateProvider(package: package, artifact: artifact)
        }
        try validateDeviceProfile(profile: profile, identity: identity, deviceFiles: deviceFiles)
    }

    private func validateProvider(
        package: MapPackage,
        artifact: ValidatedMapArtifact
    ) throws {
        let packageProvider = MapIdentity.normalizeProvider(package.providerId)
        let artifactProvider = MapIdentity.normalizeProvider(artifact.provider)

        guard !package.id.isEmpty,
              package.sourceKind == .provider,
              !packageProvider.isEmpty,
              providerRegistry.adapter(for: packageProvider) != nil,
              !package.regionId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              artifact.sourceKind == .provider,
              artifact.catalogPackageID == package.id,
              artifactProvider == packageProvider,
              let expectedIdentity = package.identity,
              MapIdentityMatcher.matches(
                  actual: MapIdentity(provider: artifact.provider, region: artifact.region),
                  expected: expectedIdentity,
                  providerRegionId: package.providerRegionId,
                  identifier: package.identifier
              ) else {
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
    }

    private func validateCustom(
        package: MapPackage,
        artifact: ValidatedMapArtifact
    ) throws {
        guard !package.id.isEmpty,
              MapIdentity.normalizeProvider(package.providerId) == "custom",
              !package.regionId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              artifact.sourceKind == .custom,
              artifact.catalogPackageID == package.id,
              MapIdentity.normalizeProvider(artifact.provider) == "custom",
              let expectedIdentity = package.identity,
              MapIdentity.normalizeRegion(artifact.region) == expectedIdentity.region,
              package.version == artifact.version else {
            throw Stage42TargetPolicyError.unsupportedPackage
        }

        let expectedFilename = try TerentoManagedFilenameGenerator().filename(
            providerId: package.providerId,
            regionId: package.canonicalRegionId
        )
        guard artifact.targetFilename == expectedFilename,
              TerentoManagedFilenameGenerator().isValid(artifact.targetFilename) else {
            throw Stage42TargetPolicyError.unsupportedFilename
        }
    }

    private func validateDeviceProfile(
        profile: DeviceInstallProfile?,
        identity: DeviceIdentity,
        deviceFiles: [DeviceFile]
    ) throws {
        guard identity.usbVendorId == 0x091e,
              GarminMapCapabilityRegistry.local.evaluate(identity: identity).canAttemptTerentoMapInstall,
              DeviceInstallProfileRegistry.hasSingleGarminRootFolder(in: deviceFiles),
              let profile,
              profile.matches(identity),
              profile.targetDirectory == "/GARMIN",
              profile.supportsMapWrite else {
            throw Stage42TargetPolicyError.unsupportedDeviceProfile
        }
    }
}
