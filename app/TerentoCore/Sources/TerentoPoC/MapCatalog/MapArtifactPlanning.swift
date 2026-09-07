import Foundation

enum MapPackageSelectionError: Error, Equatable, Sendable {
    case missingMainArtifact
    case duplicateArtifact(String)
    case unknownOptionalArtifact(String)
    case requiredArtifactSelected(String)
    case unavailableOptionalArtifact(String)
    case selectionForUnselectedPackage(String)
}

/// The optional-artifact selection for one catalog package.
///
/// The main artifact is implicit and always belongs to the resulting plan.
/// Optional IDs are accepted only when they are defined by this exact
/// package and have already passed the catalog's usability contract.
struct MapPackageSelection: Equatable, Sendable {
    let packageID: String
    let selectedOptionalArtifactIDs: Set<String>

    init(
        package: MapPackage,
        selectedOptionalArtifactIDs: Set<String> = []
    ) throws {
        let artifactsByID = Dictionary(grouping: package.artifacts, by: \.id)
        if let duplicateID = artifactsByID.first(where: { $0.value.count > 1 })?.key {
            throw MapPackageSelectionError.duplicateArtifact(duplicateID)
        }

        guard package.mainArtifact != nil else {
            throw MapPackageSelectionError.missingMainArtifact
        }

        for artifactID in selectedOptionalArtifactIDs {
            guard let artifact = artifactsByID[artifactID]?.first else {
                throw MapPackageSelectionError.unknownOptionalArtifact(artifactID)
            }
            guard artifact.kind != .main, !artifact.required else {
                throw MapPackageSelectionError.requiredArtifactSelected(artifactID)
            }
            guard artifact.isUsableOptionalSelection else {
                throw MapPackageSelectionError.unavailableOptionalArtifact(artifactID)
            }
        }

        self.packageID = package.id
        self.selectedOptionalArtifactIDs = selectedOptionalArtifactIDs
    }
}

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
    /// Only a fully validated, sized, locally acquirable artifact can be
    /// offered as an optional user selection. Archive size alone is not an
    /// install-size proof and therefore never makes this true.
    var isUsableOptionalSelection: Bool {
        !required
            && kind != .main
            && validationState == .validated
            && sizeBytes.map { $0 > 0 } == true
            && (sourceURL != nil || localURL != nil)
    }

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
            downloadSizeBytes: downloadSizeBytes,
            checksum: checksum,
            validationState: validationState
        )
    }

    func withValidationState(_ validationState: MapArtifactValidationState) -> MapArtifact {
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
            downloadSizeBytes: downloadSizeBytes,
            checksum: checksum,
            validationState: validationState
        )
    }
}
