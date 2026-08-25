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
        installedMaps: [InstalledMap],
        inspectedFiles: [InstalledMapFile]
    ) -> MapConflictResolution {
        if let matchingMap = installedMaps.first(where: { installedMap in
            guard let installedIdentity = installedMap.identity,
                  let selectedIdentity = selectedPackage.identity else {
                return false
            }

            return installedIdentity == selectedIdentity
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
        selectedPackage: MapPackage
    ) throws -> String {
        let filename = try filenameGenerator.filename(
            providerId: selectedPackage.providerId,
            regionId: selectedPackage.canonicalRegionId
        )
        return "\(profile.targetDirectory)/\(filename)"
    }
}

struct OwnershipVerifier: Sendable {
    private let filenameGenerator = TerentoManagedFilenameGenerator()

    func classify(
        map: InstalledMap,
        deviceKey: String,
        actualSHA256: String?,
        manifest: TerentoManifest
    ) -> InstallMapOwnership {
        guard map.metadataStatus == .parsed,
              let identity = map.identity else {
            return .unknown
        }

        guard filenameGenerator.isValid(map.sourceFile.filename),
              let actualSHA256 else {
            return .externalRecognized
        }

        let isManaged = manifest.entries.contains { entry in
            entry.deviceKey == deviceKey
                && entry.devicePath == map.sourceFile.path
                && entry.filename == map.sourceFile.filename
                && MapIdentity.normalizeProvider(entry.providerId) == identity.provider
                && MapIdentity.normalizeRegion(entry.regionId) == identity.region
                && entry.sizeBytes == map.sizeBytes
                && entry.sha256.caseInsensitiveCompare(actualSHA256) == .orderedSame
        }

        return isManaged ? .terentoManaged : .externalRecognized
    }
}
