import Foundation

/// The neutral artifact bundle used by selection and storage planning. The
/// main map is always part of the default plan; optional companions such as
/// contours are opt-in and never make the main map unavailable by themselves.
struct MapArtifactPlan: Equatable, Sendable {
    let packageID: String
    let selectedArtifacts: [MapArtifact]

    init(
        packageID: String,
        artifacts: [MapArtifact],
        includingOptionalArtifactIDs: Set<String> = []
    ) {
        let selected = artifacts.filter { artifact in
            artifact.kind == .main
                || artifact.required
                || includingOptionalArtifactIDs.contains(artifact.id)
        }

        self.packageID = packageID
        self.selectedArtifacts = selected.sorted { lhs, rhs in
            if lhs.kind != rhs.kind {
                return lhs.kind == .main
            }
            return lhs.id < rhs.id
        }
    }

    var selectedArtifactIDs: Set<String> {
        Set(selectedArtifacts.map(\.id))
    }

    var mainArtifact: MapArtifact? {
        selectedArtifacts.first { $0.kind == .main }
    }

    var optionalArtifacts: [MapArtifact] {
        selectedArtifacts.filter { !$0.required && $0.kind != .main }
    }

    var hasMainArtifact: Bool {
        mainArtifact != nil
    }

    /// A missing artifact size stays unknown. It must not be replaced by an
    /// archive/download size because the storage gate protects a device write.
    var installSizeBytes: UInt64? {
        guard !selectedArtifacts.isEmpty else { return nil }

        var total: UInt64 = 0
        for artifact in selectedArtifacts {
            guard let size = artifact.sizeBytes else {
                return nil
            }
            let addition = total.addingReportingOverflow(size)
            guard !addition.overflow else {
                return nil
            }
            total = addition.partialValue
        }
        return total > 0 ? total : nil
    }

    var hasUnresolvedInstallSize: Bool {
        installSizeBytes == nil
    }
}

extension MapArtifact {
    func withSize(_ sizeBytes: UInt64?) -> MapArtifact {
        MapArtifact(
            id: id,
            source: source,
            kind: kind,
            required: required,
            providerId: providerId,
            providerRegionId: providerRegionId,
            canonicalRegionId: canonicalRegionId,
            version: version,
            releaseMetadata: releaseMetadata,
            sourceURL: sourceURL,
            localURL: localURL,
            sizeBytes: sizeBytes,
            checksum: checksum,
            validationState: validationState
        )
    }
}
