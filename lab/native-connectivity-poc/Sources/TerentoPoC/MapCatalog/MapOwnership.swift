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
}

/// Matches a scanned map to the local ownership manifest for presentation.
///
/// This is deliberately not the destructive-operation authorization check.
/// SafeDeleteAdapter still re-reads the exact object and verifies its full
/// SHA-256 against the manifest-backed backup before deleting anything.
struct MapOwnershipMatcher: Sendable {
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
              let region = metadata.region,
              let version = metadata.version else {
            return .detectedNotManaged
        }

        let normalizedProvider = MapIdentity.normalizeProvider(provider)
        let normalizedRegion = MapIdentity.normalizeRegion(region)

        let isRecorded = records.contains { entry in
            entry.devicePath == file.path
                && entry.filename == file.filename
                && entry.sizeBytes == file.sizeBytes
                && MapIdentity.normalizeProvider(entry.providerId) == normalizedProvider
                && MapIdentity.normalizeRegion(entry.regionId) == normalizedRegion
                && entry.version == version
        }

        return isRecorded ? .managedByTerento : .detectedNotManaged
    }
}
