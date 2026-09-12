import Foundation

/// The manifest fields needed to classify a scanned map for presentation.
///
/// This small value type keeps the map scanner independent from the
/// installation/manifest module. It is not an authorization grant: the
/// destructive delete path performs its own exact object, size, hash, and
/// backup verification.
struct MapOwnershipRecord: Sendable, Equatable {
    let devicePath: String
    let filename: String
    let providerId: String
    let regionId: String
    let version: MapVersion
    let sizeBytes: UInt64
    let packageID: String?
    let artifactID: String?
    let artifactKind: MapArtifactKind?
    let bbbikeMetadata: BBBikeMapMetadata?

    init(
        devicePath: String,
        filename: String,
        providerId: String,
        regionId: String,
        version: MapVersion,
        sizeBytes: UInt64,
        packageID: String? = nil,
        artifactID: String? = nil,
        artifactKind: MapArtifactKind? = nil,
        bbbikeMetadata: BBBikeMapMetadata? = nil
    ) {
        self.devicePath = devicePath
        self.filename = filename
        self.providerId = providerId
        self.regionId = regionId
        self.version = version
        self.sizeBytes = sizeBytes
        self.packageID = packageID
        self.artifactID = artifactID
        self.artifactKind = artifactKind
        self.bbbikeMetadata = bbbikeMetadata
    }
}

/// Matches a scanned map to the local ownership manifest for presentation.
///
/// This is deliberately not the destructive-operation authorization check.
/// SafeDeleteAdapter still re-reads the exact object identity before deleting
/// anything. A manual Remove of a Terento-owned object does not need to copy
/// the complete map again: the exact live path, filename, size, object ID,
/// and local manifest record are the ownership proof. Safe Update and Backup
/// retain their full-content verification paths.
struct MapOwnershipMatcher: Sendable {
    /// A missing release is accepted only for a recorded managed OTM contour.
    /// Callers must still match the exact path, size and provider/region identity.
    static func lifecycleVersionMatches(
        scanned: MapVersion?, recorded: MapVersion,
        provider: String, filename: String, artifactKind: MapArtifactKind?
    ) -> Bool {
        if let scanned { return scanned == recorded }
        return MapIdentity.normalizeProvider(provider) == "opentopomap"
            && artifactKind == .contours
            && TerentoManagedFilenameGenerator().artifactKind(for: filename) == .contours
    }

    func isExactCustomRecord(
        for file: InstalledMapFile,
        records: [MapOwnershipRecord]
    ) -> Bool {
        records.contains { entry in
            MapIdentity.normalizeProvider(entry.providerId) == "custom"
                && entry.devicePath == file.path
                && entry.filename == file.filename
                && entry.sizeBytes == file.sizeBytes
        }
    }

    func managementState(
        for file: InstalledMapFile,
        metadata: GarminIMGMetadata,
        records: [MapOwnershipRecord]
    ) -> MapManagementState {
        // Custom IMG files intentionally have no provider/region/version
        // identity. Exact manifest coordinates still allow their owner state
        // to be shown and managed without turning a heuristic match into a
        // destructive authorization grant.
        if isExactCustomRecord(for: file, records: records) {
            return .managedByTerento
        }

        guard let provider = metadata.provider,
              let region = metadata.region else {
            return .detectedNotManaged
        }

        let actualIdentity = MapIdentity(provider: provider, region: region)

        let isRecorded = records.contains { entry in
            guard let expectedIdentity = MapIdentity(
                provider: entry.providerId,
                region: entry.regionId
            ) else {
                return false
            }

            return entry.devicePath == file.path
                && entry.filename == file.filename
                && entry.sizeBytes == file.sizeBytes
                && MapIdentityMatcher.matches(
                    actual: actualIdentity,
                    expected: expectedIdentity,
                    providerRegionId: entry.regionId
                )
                // Some OpenTopoMap contour IMG headers do not carry a
                // release token. Exact local ownership still proves the
                // object because path, filename and size are also required.
                && (metadata.version == nil || entry.version == metadata.version)
        }

        return isRecorded ? .managedByTerento : .detectedNotManaged
    }

    func managedComponent(
        for file: InstalledMapFile,
        metadata: GarminIMGMetadata,
        records: [MapOwnershipRecord]
    ) -> (packageID: String?, artifactID: String?, artifactKind: MapArtifactKind?)? {
        guard let provider = metadata.provider,
              let region = metadata.region,
              let actualIdentity = MapIdentity(provider: provider, region: region) else {
            return nil
        }

        guard let record = records.first(where: { entry in
            guard let expectedIdentity = MapIdentity(
                provider: entry.providerId,
                region: entry.regionId
            ) else {
                return false
            }

            return entry.devicePath == file.path
                && entry.filename == file.filename
                && entry.sizeBytes == file.sizeBytes
                && MapIdentityMatcher.matches(
                    actual: actualIdentity,
                    expected: expectedIdentity,
                    providerRegionId: entry.regionId
                )
                && (metadata.version == nil || entry.version == metadata.version)
        }) else {
            return nil
        }

        return (record.packageID, record.artifactID, record.artifactKind)
    }
}
