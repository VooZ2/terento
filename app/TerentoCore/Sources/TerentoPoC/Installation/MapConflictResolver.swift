import Foundation

enum MapConflictResolution: Equatable, Sendable {
    case noConflict
    case requiresExplicitReplacement(
        installedMap: InstalledMap,
        ownership: InstallMapOwnership
    )
    case blockedAmbiguous
}

struct MapConflictResolver: Sendable {
    private let filenameGenerator = TerentoManagedFilenameGenerator()

    func resolve(
        selectedPackage: MapPackage,
        targetPath: String,
        artifactKind: MapArtifactKind = .main,
        installedMaps: [InstalledMap],
        inspectedFiles: [InstalledMapFile]
    ) -> MapConflictResolution {
        if let matchingMap = installedMaps.first(where: { installedMap in
            guard artifactKind == .main || installedMap.sourceFile.path == targetPath else {
                return false
            }
            guard let installedIdentity = installedMap.identity,
                  let selectedIdentity = selectedPackage.identity else {
                return false
            }

            return MapIdentityMatcher.matches(
                actual: installedIdentity,
                expected: selectedIdentity,
                providerRegionId: selectedPackage.providerRegionId,
                identifier: selectedPackage.identifier
            )
        }) {
            return .requiresExplicitReplacement(
                installedMap: matchingMap,
                ownership: ownership(for: matchingMap)
            )
        }

        // A file already occupying Terento's target path is not safe to
        // overwrite unless its identity and ownership were proven above.
        if inspectedFiles.contains(where: { $0.path == targetPath }) {
            return .blockedAmbiguous
        }

        return .noConflict
    }

    private func ownership(for map: InstalledMap) -> InstallMapOwnership {
        guard map.metadataStatus == .parsed, map.identity != nil else {
            return .unknown
        }

        switch map.managementState {
        case .managedByTerento:
            return .terentoManaged
        case .detectedNotManaged:
            return .externalRecognized
        case .unknown:
            return .unknown
        }
    }

    func targetPath(
        profile: DeviceInstallProfile,
        selectedPackage: MapPackage,
        artifactKind: MapArtifactKind = .main
    ) throws -> String {
        let filename = try filenameGenerator.filename(
            providerId: selectedPackage.providerId,
            regionId: selectedPackage.canonicalRegionId,
            artifactKind: artifactKind
        )
        return "\(profile.targetDirectory)/\(filename)"
    }
}
