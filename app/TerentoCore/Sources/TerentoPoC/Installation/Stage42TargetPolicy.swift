import Foundation

enum Stage42TargetPolicyError: LocalizedError, Equatable, Sendable {
    case policyConfigurationInvalid
    case unsupportedPackage
    case unsupportedVersion
    case unsupportedFilename
    case unsupportedDeviceProfile
    case installationAuthorizationRequired
    case installationAuthorizationUnavailable

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
        case .installationAuthorizationRequired:
            return "Map installation is not available for this device in Terento."
        case .installationAuthorizationUnavailable:
            return "Terento could not verify this device's installation authorization right now. Check your connection and try again."
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
        deviceFiles: [DeviceFile],
        installedMaps: [InstalledMap] = [],
        inspectedFiles: [InstalledMapFile] = [],
        installationAuthorization: InstallationAuthorizationState
    ) throws {
        guard installationAuthorization.canInstall,
              installationAuthorization.matches(identity: identity) else {
            if installationAuthorization.blockReason == .catalogUnavailable {
                throw Stage42TargetPolicyError.installationAuthorizationUnavailable
            }
            throw Stage42TargetPolicyError.installationAuthorizationRequired
        }
        if deviceFiles.contains(where: { BBBikeProviderAdapter.conflicts(package, filename: $0.filename)
            || OSMapaProviderAdapter.conflicts(package, filename: $0.filename) }) {
            throw Stage42TargetPolicyError.unsupportedPackage
        }
        if MapIdentity.normalizeProvider(package.providerId) == "osmapa" {
            try validateOSMapaContent(package: package, deviceFiles: deviceFiles,
                                      installedMaps: installedMaps, inspectedFiles: inspectedFiles)
        }
        if package.sourceKind == .custom {
            try validateCustom(package: package, artifact: artifact)
        } else {
            try validateProvider(package: package, artifact: artifact)
        }
        try validateDeviceProfile(profile: profile, identity: identity, deviceFiles: deviceFiles)
    }

    /// OSMapaPL conflicts depend on file content, not names. Every map image
    /// on the device must have scan evidence from this same inventory, and
    /// that evidence must show no conflict; otherwise nothing is written.
    private func validateOSMapaContent(
        package: MapPackage,
        deviceFiles: [DeviceFile],
        installedMaps: [InstalledMap],
        inspectedFiles: [InstalledMapFile]
    ) throws {
        var evidence: [InstalledMapFile] = []
        for file in GarminMapScanner.inspectionCandidates(deviceFiles) {
            let matches = inspectedFiles.filter {
                $0.path == file.path && $0.filename == file.filename && $0.sizeBytes == file.sizeBytes
            }
            guard matches.count == 1 else { throw Stage42TargetPolicyError.unsupportedPackage }
            evidence.append(matches[0])
        }
        guard OSMapaProviderAdapter.installedConflict(
            for: package, installedMaps: installedMaps, inspectedFiles: evidence
        ) == nil else {
            throw Stage42TargetPolicyError.unsupportedPackage
        }
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
              artifactIDMatches(artifact, package: package),
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
            regionId: package.canonicalRegionId,
            artifactKind: artifact.artifactKind
        )
        guard artifact.targetFilename == expectedFilename,
              TerentoManagedFilenameGenerator().isValid(artifact.targetFilename) else {
            throw Stage42TargetPolicyError.unsupportedFilename
        }
    }

    private func artifactIDMatches(
        _ artifact: ValidatedMapArtifact,
        package: MapPackage
    ) -> Bool {
        guard let expected = package.artifacts.first(where: {
            $0.kind == artifact.artifactKind
        })?.id else {
            return artifact.artifactKind == .main && artifact.artifactID == package.id
        }

        if artifact.artifactKind == .main {
            return artifact.artifactID == expected || artifact.artifactID == package.id
        }
        return artifact.artifactID == expected
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
            regionId: package.canonicalRegionId,
            artifactKind: artifact.artifactKind
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
              DeviceInstallProfileRegistry.hasSingleGarminRootFolder(in: deviceFiles),
              let profile,
              profile.matches(identity),
              profile.targetDirectory == "/GARMIN",
              profile.supportsMapWrite else {
            throw Stage42TargetPolicyError.unsupportedDeviceProfile
        }
    }
}
