import Foundation

struct CompatibilityDecision: Sendable, Equatable {
    let identity: DeviceIdentity
    let status: CompatibilityStatus?
    let statusSource: CompatibilityStatusSource
    let publicRecord: CompatibilityStatusRecord?
    let evidence: CompatibilityEvidence
    let registryEntry: DeviceRegistryEntry?
    let reason: String

    var displayName: String {
        registryEntry?.displayName ?? (identity.manufacturer + " " + identity.presentationModel)
    }
}

struct CompatibilityEngine: Sendable {
    let registry: DeviceRegistry
    private let identityAdapter: GarminDeviceIdentityAdapter

    init(
        registry: DeviceRegistry = .local,
        identityAdapter: GarminDeviceIdentityAdapter = GarminDeviceIdentityAdapter()
    ) {
        self.registry = registry
        self.identityAdapter = identityAdapter
    }

    func evaluate(snapshot: DeviceSnapshot) -> CompatibilityDecision {
        let identity = identityAdapter.makeIdentity(from: snapshot)

        guard let entry = registry.entry(for: identity) else {
            return CompatibilityDecision(
                identity: identity,
                status: nil,
                statusSource: .unavailable,
                publicRecord: nil,
                evidence: .nativeConnectivityTested,
                registryEntry: nil,
                reason: "Current public compatibility evidence is not available for this exact device identity."
            )
        }

        return CompatibilityDecision(
            identity: identity,
            // The local registry only identifies the device and its safe
            // capability profile. It is not a public compatibility source.
            status: nil,
            statusSource: .unavailable,
            publicRecord: nil,
            evidence: entry.evidence,
            registryEntry: entry,
            reason: "Resolving current public compatibility evidence for this exact device identity."
        )
    }

}

extension CompatibilityDecision {
    func applying(
        _ resolution: CompatibilityStatusResolution
    ) -> CompatibilityDecision {
        CompatibilityDecision(
            identity: identity,
            status: resolution.status,
            statusSource: resolution.source,
            publicRecord: resolution.record,
            evidence: evidence,
            registryEntry: registryEntry,
            reason: Self.reason(for: resolution)
        )
    }

    private static func reason(for resolution: CompatibilityStatusResolution) -> String {
        switch resolution.source {
        case .remote:
            return "Public compatibility status refreshed from the canonical Terento service."
        case .cache:
            return "Public compatibility status is shown from a recent canonical Terento cache entry."
        case .unavailable:
            return "Current public compatibility evidence is unavailable; no local status was invented."
        }
    }
}
