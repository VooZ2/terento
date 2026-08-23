import Foundation

struct CompatibilityDecision: Sendable, Equatable {
    let identity: DeviceIdentity
    let status: CompatibilityStatus
    let evidence: CompatibilityEvidence
    let registryEntry: DeviceRegistryEntry?
    let reason: String

    var displayName: String {
        registryEntry?.displayName ?? (identity.manufacturer + " " + identity.model)
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
                status: .unknown,
                evidence: .nativeConnectivityTested,
                registryEntry: nil,
                reason: "No local evidence exists for this exact device identity."
            )
        }

        let status = evaluatedStatus(for: entry)
        let reason: String
        switch status {
        case .tested:
            reason = "Read-only connectivity evidence exists for this exact registry entry."
        case .testing:
            reason = "This exact registry entry is currently under validation."
        case .supported:
            reason = "Map installation, reconnect, and map visibility evidence is complete."
        case .verified:
            reason = "Multiple devices and firmware variations have completed the workflow."
        case .unknown:
            reason = "The local registry does not contain enough evidence for support."
        }

        return CompatibilityDecision(
            identity: identity,
            status: status,
            evidence: entry.evidence,
            registryEntry: entry,
            reason: reason
        )
    }

    private func evaluatedStatus(for entry: DeviceRegistryEntry) -> CompatibilityStatus {
        let evidence = entry.evidence

        if evidence.map == .pass,
           evidence.reconnect == .pass,
           evidence.mapVisible == .pass {
            if evidence.multiplePhysicalDevices == .pass,
               evidence.firmwareVariation == .pass {
                return .verified
            }
            return .supported
        }

        switch entry.status {
        case .unknown, .testing, .tested:
            return entry.status
        case .supported, .verified:
            // A registry cannot claim a higher status than its recorded evidence.
            return .tested
        }
    }
}
