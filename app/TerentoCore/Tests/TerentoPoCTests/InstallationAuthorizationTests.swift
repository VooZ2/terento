import Foundation

private enum AuthorizationTestError: Error {
    case failed(String)
}

private func require(_ condition: @autoclosure () -> Bool, _ message: String) throws {
    guard condition() else { throw AuthorizationTestError.failed(message) }
}

private func identity(
    model: String = "fenix 8 - 47mm AMOLED",
    family: String = "fēnix",
    displayType: String? = "AMOLED",
    catalogDeviceID: String? = nil,
    catalogSolar: Bool? = nil,
    deviceDescription: String? = nil,
    garminModelDescription: String? = nil,
    variant: String? = nil
) -> DeviceIdentity {
    DeviceIdentity(
        manufacturer: "Garmin",
        model: model,
        family: family,
        variant: variant,
        usbVendorId: 0x091e,
        usbProductId: 0x51b8,
        firmware: "test",
        storageCapacity: 31_000_000_000,
        freeSpace: 15_000_000_000,
        deviceDescription: deviceDescription ?? model,
        garminModelDescription: garminModelDescription,
        catalogMetadata: CatalogDeviceMetadata(
            candidateDeviceID: catalogDeviceID,
            model: GarminDeviceModelNormalizer.canonicalModel(from: model) ?? model,
            screenTechnology: displayType,
            solar: catalogSolar,
            inReach: nil
        )
    )
}

private func record(
    id: String,
    canonicalModel: String,
    model: String? = nil,
    variant: String? = nil,
    caseSizeMm: Int? = nil,
    displayType: String? = nil,
    solar: Bool? = nil,
    inReach: Bool? = nil,
    active: Bool = true,
    mapCapable: Bool?,
    scope: String,
    installationAuthorization: String
) -> InstallationAuthorizationRecord {
    InstallationAuthorizationRecord(
        id: id,
        manufacturer: "Garmin",
        model: model ?? canonicalModel,
        baseModel: GarminDeviceModelNormalizer.catalogCanonicalModel(from: model ?? canonicalModel) ?? canonicalModel,
        canonicalModel: canonicalModel,
        variant: variant ?? "",
        caseSizeMm: caseSizeMm,
        displayType: displayType,
        screenTechnology: displayType,
        solar: solar,
        inReach: inReach,
        active: active,
        mapCapable: mapCapable,
        scope: scope,
        installationAuthorization: installationAuthorization
    )
}

private func policyData(_ records: [InstallationAuthorizationRecord]) throws -> Data {
    let document = InstallationAuthorizationDocument(
        schemaVersion: 3,
        policyVersion: 3,
        updatedAt: "2026-09-22T00:00:00Z",
        manufacturer: "Garmin",
        devices: records
    )
    let encoded = try JSONEncoder().encode(document)
    var raw = try JSONSerialization.jsonObject(with: encoded) as! [String: Any]
    var devices = raw["devices"] as! [[String: Any]]
    for index in devices.indices {
        for key in ["caseSizeMm", "displayType", "screenTechnology", "solar", "inReach", "mapCapable"]
        where devices[index][key] == nil {
            devices[index][key] = NSNull()
        }
    }
    raw["devices"] = devices
    return try JSONSerialization.data(withJSONObject: raw)
}

private func response(
    _ data: Data,
    status: Int = 200,
    contentType: String = "application/json; charset=utf-8"
) -> (Data, URLResponse) {
    let url = URL(string: "https://api.terento.app/devices/installation-policy.json")!
    return (
        data,
        HTTPURLResponse(url: url, statusCode: status, httpVersion: nil,
                        headerFields: ["Content-Type": contentType])!
    )
}

private func client(for data: Data) -> InstallationAuthorizationClient {
    InstallationAuthorizationClient(dataLoader: { _ in response(data) })
}

private func modifiedPolicy(
    _ data: Data,
    change: (inout [String: Any]) -> Void
) throws -> Data {
    var document = try JSONSerialization.jsonObject(with: data) as! [String: Any]
    change(&document)
    return try JSONSerialization.data(withJSONObject: document)
}

private let allMapsYesPolicy = try! policyData([
    record(id: "fenix-8-43", canonicalModel: "fenix 8", variant: "43 mm, AMOLED", caseSizeMm: 43, displayType: "AMOLED", mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
    record(id: "fenix-8-47", canonicalModel: "fenix 8", variant: "47 mm, AMOLED", caseSizeMm: 47, displayType: "AMOLED", mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
    record(id: "fenix-8-51", canonicalModel: "fenix 8", variant: "51 mm, AMOLED", caseSizeMm: 51, displayType: "AMOLED", mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
])

@main
struct InstallationAuthorizationTests {
    static func main() async throws {
        let exact = await client(for: allMapsYesPolicy).resolve(identity: identity())
        try require(exact.canInstall, "exact fenix 8 47 AMOLED Maps=Yes is installable")
        try require(exact.matches(identity: identity()), "exact authorization remains bound to the model and known variant facts")

        let base = await client(for: allMapsYesPolicy)
            .resolve(identity: identity(model: "fenix 8", displayType: nil))
        try require(base.canInstall, "fenix 8 without size is approved when every active variant has Maps=Yes")

        let partialWithOtherDisplay = try policyData([
            record(id: "fenix-8-43-amoled", canonicalModel: "fenix 8", variant: "43 mm, AMOLED", caseSizeMm: 43, displayType: "AMOLED", mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
            record(id: "fenix-8-47-amoled", canonicalModel: "fenix 8", variant: "47 mm, AMOLED", caseSizeMm: 47, displayType: "AMOLED", mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
            record(id: "fenix-8-51-mip", canonicalModel: "fenix 8", variant: "51 mm, MIP", caseSizeMm: 51, displayType: "MIP", mapCapable: false, scope: "OUT_OF_SCOPE", installationAuthorization: "BLOCKED"),
        ])
        let partial = await client(for: partialWithOtherDisplay)
            .resolve(identity: identity(model: "fenix 8 AMOLED", displayType: "AMOLED"))
        try require(partial.canInstall, "fenix 8 AMOLED without size is approved when all AMOLED candidates have Maps=Yes")

        let normalized = await client(for: allMapsYesPolicy)
            .resolve(identity: identity(model: "Garmin FĒNIX 8", displayType: nil))
        try require(normalized.canInstall, "model normalization produces the same base-model result")

        let substringCollisionPolicy = try policyData([
            record(id: "fenix-8", canonicalModel: "fenix 8", mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
            record(id: "fenix-80", canonicalModel: "fenix 80", mapCapable: false, scope: "OUT_OF_SCOPE", installationAuthorization: "BLOCKED"),
        ])
        let substringCollision = await client(for: substringCollisionPolicy)
            .resolve(identity: identity(model: "fenix 8", displayType: nil))
        try require(substringCollision.canInstall,
                    "fenix 8 does not accidentally match the different fenix 80 base model")

        let solarPolicy = try policyData([
            record(id: "fenix-8-solar", canonicalModel: "fenix 8", variant: "47 mm Solar", caseSizeMm: 47, displayType: "MIP", solar: true, mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
            record(id: "fenix-8-non-solar", canonicalModel: "fenix 8", variant: "47 mm AMOLED", caseSizeMm: 47, displayType: "AMOLED", solar: false, mapCapable: false, scope: "OUT_OF_SCOPE", installationAuthorization: "BLOCKED"),
        ])
        let solarState = await client(for: solarPolicy)
            .resolve(identity: identity(model: "fenix 8 Solar", displayType: "MIP"))
        try require(solarState.canInstall,
                    "a known Solar variant narrows candidates without treating Solar as display technology")

        let fenix7EnduroPolicy = try policyData([
            record(id: "fenix-7-47", canonicalModel: "fenix 7", variant: "47 mm", caseSizeMm: 47, displayType: "MIP", mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
            record(id: "enduro-3-51", canonicalModel: "Enduro 3", variant: "51 mm", caseSizeMm: 51, displayType: "MIP", mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
        ])
        let fenix7State = await client(for: fenix7EnduroPolicy)
            .resolve(identity: identity(model: "fenix 7 - 47mm", displayType: "MIP"))
        try require(fenix7State.canInstall, "fenix 7 Maps=Yes is approved")
        let enduro3State = await client(for: fenix7EnduroPolicy)
            .resolve(identity: identity(model: "Enduro 3", family: "Enduro", displayType: "MIP"))
        try require(enduro3State.canInstall, "Enduro 3 Maps=Yes is approved even with zero installations")

        let mapsOnlyPolicy = try policyData([
            record(id: "fenix-8-maps-yes", canonicalModel: "fenix 8", mapCapable: true,
                scope: "OUT_OF_SCOPE", installationAuthorization: "BLOCKED"),
        ])
        let mapsOnlyState = await client(for: mapsOnlyPolicy)
            .resolve(identity: identity(model: "fenix 8", displayType: nil))
        try require(mapsOnlyState.canInstall,
                    "Maps=Yes and active=true authorize independently of redundant scope/authorization labels")

        let ambiguous = try policyData([
            record(id: "fenix-8-47-yes", canonicalModel: "fenix 8", variant: "47 mm", caseSizeMm: 47, displayType: "AMOLED", mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
            record(id: "fenix-8-51-no", canonicalModel: "fenix 8", variant: "51 mm", caseSizeMm: 51, displayType: "AMOLED", mapCapable: false, scope: "OUT_OF_SCOPE", installationAuthorization: "BLOCKED"),
        ])
        let ambiguousState = await client(for: ambiguous)
            .resolve(identity: identity(model: "fenix 8", displayType: nil))
        try require(ambiguousState.blockReason == .pending,
                    "mixed Maps capability candidates remain PENDING instead of guessing Maps=Yes")
        try require(!ambiguousState.canInstall, "ambiguous capability cannot install")

        let conflictingSizes = identity(model: "fenix 8 - 51mm AMOLED",
            deviceDescription: "fenix 8 - 47mm AMOLED")
        let conflictingSizesState = await client(for: ambiguous)
            .resolve(identity: conflictingSizes)
        try require(conflictingSizesState.blockReason == .pending,
                    "conflicting case sizes broaden to mixed Maps candidates and remain PENDING")
        try require(exact.matches(identity: conflictingSizes),
                    "conflicting case sizes are unknown, not an authorization mismatch")

        let internallyConflictingSizes = identity(
            model: "fenix 8 - 47mm 51mm AMOLED")
        let internallyConflictingSizesState = await client(for: ambiguous)
            .resolve(identity: internallyConflictingSizes)
        try require(internallyConflictingSizesState.blockReason == .pending,
                    "two sizes in one source are unknown and mixed Maps candidates remain PENDING")

        let conflictingDisplays = identity(model: "fenix 8 - 47mm AMOLED",
            deviceDescription: "fenix 8 - 47mm MIP")
        let sameSizeDisplayConflict = try policyData([
            record(id: "fenix-8-47-amoled-yes", canonicalModel: "fenix 8",
                variant: "47 mm AMOLED", caseSizeMm: 47, displayType: "AMOLED",
                mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
            record(id: "fenix-8-47-mip-no", canonicalModel: "fenix 8",
                variant: "47 mm MIP", caseSizeMm: 47, displayType: "MIP",
                mapCapable: false, scope: "OUT_OF_SCOPE", installationAuthorization: "BLOCKED"),
        ])
        let conflictingDisplaysState = await client(for: sameSizeDisplayConflict)
            .resolve(identity: conflictingDisplays)
        try require(conflictingDisplaysState.blockReason == .pending,
                    "conflicting MTP/XML displays broaden to mixed Maps candidates and remain PENDING")
        try require(exact.matches(identity: conflictingDisplays),
                    "conflicting display observations are unknown, not an authorization mismatch")

        let internallyConflictingDisplay = identity(
            model: "fenix 8 - 47mm AMOLED MIP")
        let internallyConflictingState = await client(for: allMapsYesPolicy)
            .resolve(identity: internallyConflictingDisplay)
        try require(internallyConflictingState.canInstall,
                    "conflicting display tokens are ignored when every candidate has Maps=Yes")

        // A/B: conflicting display observations become unknown independently of
        // Maps. All-Yes candidates approve; mixed capability candidates stay pending.
        let displayConflictAllYes = await client(for: allMapsYesPolicy).resolve(identity: identity(
            model: "fenix 8 AMOLED", deviceDescription: "fenix 8 MIP"))
        try require(displayConflictAllYes.canInstall,
                    "A: MTP AMOLED plus XML MIP approves when every base-model candidate has Maps=Yes")
        let displayConflictMixed = await client(for: partialWithOtherDisplay).resolve(identity: identity(
            model: "fenix 8 AMOLED", deviceDescription: "fenix 8 MIP"))
        try require(displayConflictMixed.blockReason == .pending,
                    "B: MTP AMOLED plus XML MIP remains PENDING for mixed Maps candidates")

        // C: conflicting case sizes do not narrow the candidate set.
        let sizeConflictAllYes = await client(for: allMapsYesPolicy).resolve(identity: identity(
            model: "fenix 8 - 51mm AMOLED", deviceDescription: "fenix 8 - 47mm AMOLED"))
        try require(sizeConflictAllYes.canInstall,
                    "C: conflicting case sizes approve when every base-model candidate has Maps=Yes")

        let solarVariantsAllYes = try policyData([
            record(id: "fenix-8-solar-yes", canonicalModel: "fenix 8", variant: "Solar",
                solar: true, mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
            record(id: "fenix-8-standard-yes", canonicalModel: "fenix 8", variant: "Standard",
                solar: false, mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
        ])
        let solarVariantsMixed = try policyData([
            record(id: "fenix-8-solar-yes", canonicalModel: "fenix 8", variant: "Solar",
                solar: true, mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
            record(id: "fenix-8-standard-no", canonicalModel: "fenix 8", variant: "Standard",
                solar: false, mapCapable: false, scope: "OUT_OF_SCOPE", installationAuthorization: "BLOCKED"),
        ])
        let conflictingSolarIdentity = identity(model: "fenix 8 Solar", variant: "no solar")
        let solarConflictAllYes = await client(for: solarVariantsAllYes)
            .resolve(identity: conflictingSolarIdentity)
        try require(solarConflictAllYes.canInstall,
                    "D: conflicting Solar observations are ignored when every candidate has Maps=Yes")
        let solarConflictMixed = await client(for: solarVariantsMixed)
            .resolve(identity: conflictingSolarIdentity)
        try require(solarConflictMixed.blockReason == .pending,
                    "E: conflicting Solar observations leave mixed Maps candidates PENDING")

        let inReachVariants = try policyData([
            record(id: "fenix-8-inreach-yes", canonicalModel: "fenix 8", variant: "inReach",
                inReach: true, mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
            record(id: "fenix-8-standard-yes", canonicalModel: "fenix 8", variant: "Standard",
                inReach: false, mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
        ])
        let inReachConflict = await client(for: inReachVariants).resolve(identity: identity(
            model: "fenix 8 inReach", deviceDescription: "fenix 8 no inReach"))
        try require(inReachConflict.canInstall,
                    "conflicting inReach observations are unknown when every candidate has Maps=Yes")

        let conflictingModels = identity(model: "Edge 840",
            deviceDescription: "fenix 8 - 47mm AMOLED")
        let conflictingModelsState = await client(for: ambiguous)
            .resolve(identity: conflictingModels)
        try require(conflictingModelsState.blockReason == .pending,
                    "contradictory MTP/XML base models cannot select fenix Maps=Yes")

        let conflictingXMLModel = identity(model: "fenix 8 - 47mm AMOLED",
            garminModelDescription: "fenix 7 - 47mm AMOLED")
        let conflictingXMLState = await client(for: ambiguous)
            .resolve(identity: conflictingXMLModel)
        try require(conflictingXMLState.blockReason == .pending,
                    "contradictory Garmin XML model cannot authorize a write")

        // G/H: a remembered ID cannot narrow away siblings when variant facts
        // conflict; only the complete candidate set's Maps values decide.
        let staleIDDisplayConflictAllYes = await client(for: allMapsYesPolicy).resolve(identity: identity(
            model: "fenix 8 AMOLED", catalogDeviceID: "retired-catalog-id",
            deviceDescription: "fenix 8 MIP"))
        try require(staleIDDisplayConflictAllYes.canInstall,
                    "G: stale catalogDeviceID and conflicting variants still approve all-Yes candidates")
        let staleIDDisplayConflictMixed = await client(for: partialWithOtherDisplay).resolve(identity: identity(
            model: "fenix 8 AMOLED", catalogDeviceID: "fenix-8-amoled-only",
            deviceDescription: "fenix 8 MIP"))
        try require(staleIDDisplayConflictMixed.blockReason == .pending,
                    "H: stale catalogDeviceID cannot hide mixed Maps candidates")

        // A/B: a remembered catalog ID and its enriched display cannot discard
        // a plausible current-policy sibling when the device reports only size.
        let hintedVariants = try policyData([
            record(id: "fenix-8-47-yes", canonicalModel: "fenix 8", variant: "47 mm AMOLED",
                caseSizeMm: 47, displayType: "AMOLED", mapCapable: true,
                scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
            record(id: "fenix-8-47-no", canonicalModel: "fenix 8", variant: "47 mm MIP",
                caseSizeMm: 47, displayType: "MIP", mapCapable: false,
                scope: "OUT_OF_SCOPE", installationAuthorization: "BLOCKED"),
        ])
        let hintedYes = await client(for: hintedVariants).resolve(identity: identity(
            model: "fenix 8 - 47mm", displayType: "AMOLED", catalogDeviceID: "fenix-8-47-yes"))
        try require(hintedYes.blockReason == .pending,
                    "A: Maps=Yes hint and catalog display leave current Yes/No variants PENDING")
        let hintedNo = await client(for: hintedVariants).resolve(identity: identity(
            model: "fenix 8 - 47mm", displayType: "MIP", catalogDeviceID: "fenix-8-47-no"))
        try require(hintedNo.blockReason == .pending,
                    "B: unconfirmed Maps=No hint cannot block a mixed current variant set")
        let unknownHint = await client(for: hintedVariants).resolve(identity: identity(
            model: "fenix 8 - 47mm", displayType: nil, catalogDeviceID: "retired-id"))
        try require(unknownHint.blockReason == .pending,
                    "a retired ID cannot bypass current-policy candidate evaluation")
        for otherCapability in [nil, false] as [Bool?] {
            let other = record(id: "fenix-8-47-other", canonicalModel: "fenix 8",
                variant: "47 mm MIP", caseSizeMm: 47, displayType: "MIP",
                mapCapable: otherCapability,
                scope: otherCapability == nil ? "UNKNOWN" : "OUT_OF_SCOPE",
                installationAuthorization: otherCapability == nil ? "PENDING" : "BLOCKED")
            let mixed = try policyData([
                record(id: "fenix-8-47-yes", canonicalModel: "fenix 8",
                    variant: "47 mm AMOLED", caseSizeMm: 47, displayType: "AMOLED",
                    mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
                other,
            ])
            let state = await client(for: mixed).resolve(identity: identity(
                model: "fenix 8 - 47mm", displayType: "AMOLED",
                catalogDeviceID: "fenix-8-47-yes"))
            try require(state.blockReason == .pending,
                        "a Yes hint cannot resolve mixed Yes/No or Yes/NULL capability")
        }
        let noAndUnknown = try policyData([
            record(id: "fenix-8-47-no", canonicalModel: "fenix 8", variant: "47 mm AMOLED",
                caseSizeMm: 47, displayType: "AMOLED", mapCapable: false,
                scope: "OUT_OF_SCOPE", installationAuthorization: "BLOCKED"),
            record(id: "fenix-8-47-unknown", canonicalModel: "fenix 8", variant: "47 mm MIP",
                caseSizeMm: 47, displayType: "MIP", mapCapable: nil,
                scope: "UNKNOWN", installationAuthorization: "PENDING"),
        ])
        let noAndUnknownState = await client(for: noAndUnknown).resolve(identity: identity(
            model: "fenix 8 - 47mm", displayType: "AMOLED",
            catalogDeviceID: "fenix-8-47-no"))
        try require(noAndUnknownState.blockReason == .pending,
                    "a No hint cannot resolve mixed No/NULL capability")

        // C: the raw connected model itself identifies the exact display and size.
        let confirmed = await client(for: hintedVariants).resolve(identity: identity(
            model: "fenix 8 - 47mm AMOLED", displayType: "MIP",
            catalogDeviceID: "fenix-8-47-yes"))
        guard case let .approved(confirmedRecord, _) = confirmed else {
            throw AuthorizationTestError.failed("C: independently confirmed exact variant is approved")
        }
        try require(confirmedRecord.id == "fenix-8-47-yes",
                    "C: confirmed current variant selects its exact policy row")
        let conflictingHint = await client(for: hintedVariants).resolve(identity: identity(
            model: "fenix 8 - 47mm AMOLED", displayType: "MIP",
            catalogDeviceID: "fenix-8-47-no"))
        guard case let .approved(currentRecord, _) = conflictingHint else {
            throw AuthorizationTestError.failed("current device facts must supersede a stale sibling ID")
        }
        try require(currentRecord.id == "fenix-8-47-yes",
                    "current device selects exact variant regardless of stale sibling hint")

        let fenix7ProVariants = try policyData([
            record(id: "fenix-7-pro", canonicalModel: "fenix 7 pro", model: "fēnix 7 Pro",
                solar: false, mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
            record(id: "fenix-7-pro-solar", canonicalModel: "fenix 7 pro solar no wifi",
                model: "fēnix 7 Pro", variant: "Solar (no Wi-Fi)", solar: true,
                mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
            record(id: "fenix-8-other", canonicalModel: "fenix 8", mapCapable: false,
                scope: "OUT_OF_SCOPE", installationAuthorization: "BLOCKED"),
            record(id: "edge-other", canonicalModel: "Edge 840", mapCapable: false,
                scope: "OUT_OF_SCOPE", installationAuthorization: "BLOCKED"),
        ])
        let proBase = await client(for: fenix7ProVariants)
            .resolve(identity: identity(model: "fēnix 7 Pro", displayType: nil))
        try require(proBase.canInstall, "variant-rich canonical_model remains in fenix 7 pro base group")

        let proMixed = try policyData([
            record(id: "fenix-7-pro", canonicalModel: "fenix 7 pro", model: "fēnix 7 Pro",
                solar: false, mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
            record(id: "fenix-7-pro-solar", canonicalModel: "fenix 7 pro solar no wifi",
                model: "fēnix 7 Pro", variant: "Solar (no Wi-Fi)", solar: true,
                mapCapable: false, scope: "OUT_OF_SCOPE", installationAuthorization: "BLOCKED"),
            record(id: "fenix-8", canonicalModel: "fenix 8", mapCapable: true,
                scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
            record(id: "edge-840", canonicalModel: "Edge 840", mapCapable: true,
                scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
        ])
        let proUnknownSolar = await client(for: proMixed)
            .resolve(identity: identity(model: "fenix 7 pro", displayType: nil))
        try require(proUnknownSolar.blockReason == .pending, "unknown Solar leaves both capability candidates")
        let proKnownSolar = await client(for: proMixed)
            .resolve(identity: identity(model: "fenix 7 pro Solar", displayType: nil))
        try require(proKnownSolar.blockReason == .outOfScope, "known Solar rejects non-Solar candidate")
        let proHintedNonSolar = await client(for: proMixed).resolve(identity: identity(
            model: "fenix 7 pro", displayType: nil, catalogDeviceID: "fenix-7-pro",
            catalogSolar: false))
        try require(proHintedNonSolar.blockReason == .pending,
                    "E: catalog-derived non-Solar cannot suppress plausible Solar Maps=No")
        let proHintedSolar = await client(for: proMixed).resolve(identity: identity(
            model: "fenix 7 pro", displayType: nil, catalogDeviceID: "fenix-7-pro-solar",
            catalogSolar: true))
        try require(proHintedSolar.blockReason == .pending,
                    "E: catalog-derived Solar cannot suppress plausible non-Solar Maps=Yes")
        let displayVariants = try policyData([
            record(id: "pro-amoled-47", canonicalModel: "fenix 7 pro sapphire",
                model: "fēnix 7 Pro", caseSizeMm: 47, displayType: "AMOLED",
                mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
            record(id: "pro-amoled-51", canonicalModel: "fenix 7 pro sapphire",
                model: "fēnix 7 Pro", caseSizeMm: 51, displayType: "AMOLED",
                mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
            record(id: "pro-mip-47", canonicalModel: "fenix 7 pro solar no wifi",
                model: "fēnix 7 Pro", caseSizeMm: 47, displayType: "MIP",
                mapCapable: false, scope: "OUT_OF_SCOPE", installationAuthorization: "BLOCKED"),
        ])
        let proAMOLED = await client(for: displayVariants)
            .resolve(identity: identity(model: "fenix 7 pro AMOLED", displayType: "AMOLED"))
        try require(proAMOLED.canInstall, "known display narrows candidate set while unknown size retains both sizes")
        let proEight = await client(for: proMixed)
            .resolve(identity: identity(model: "fenix 8", displayType: nil))
        try require(proEight.canInstall, "fenix 7 pro never absorbs fenix 8")

        let mapsNo = try policyData([
            record(id: "edge-840", canonicalModel: "Edge 840", variant: "", mapCapable: false, scope: "OUT_OF_SCOPE", installationAuthorization: "BLOCKED"),
        ])
        let edgeBlocked = await client(for: mapsNo)
            .resolve(identity: identity(model: "Edge 840", family: "Edge", displayType: nil))
        try require(edgeBlocked.blockReason == .outOfScope && !edgeBlocked.canInstall,
                    "Maps=No is BLOCKED")

        let mapsUnknown = try policyData([
            record(id: "future-model", canonicalModel: "future model", variant: "", mapCapable: nil, scope: "UNKNOWN", installationAuthorization: "PENDING"),
        ])
        let unknownCapability = await client(for: mapsUnknown)
            .resolve(identity: identity(model: "future model", family: "future", displayType: nil))
        try require(unknownCapability.blockReason == .pending && !unknownCapability.canInstall,
                    "Maps=NULL is PENDING and cannot install")

        let absentModel = await client(for: allMapsYesPolicy)
            .resolve(identity: identity(model: "Edge 840", family: "Edge", displayType: nil))
        try require(absentModel.blockReason == .pending && !absentModel.canInstall,
                    "a model absent from the catalog is PENDING, including Edge 840")
        try require(absentModel.userMessage?.contains("reliably determine") == true,
                    "PENDING uses an uncertainty message rather than a permanent unsupported claim")

        let edgeApprovedPolicy = try policyData([
            record(id: "edge-840", canonicalModel: "Edge 840", variant: "", mapCapable: true, scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
        ])
        let edgeApprovedState = await client(for: edgeApprovedPolicy)
            .resolve(identity: identity(model: "Edge 840", family: "Edge", displayType: nil))
        try require(edgeApprovedState.canInstall,
                    "a future catalog Edge Maps=Yes row is approved by the same rules")
        let swappedDevicePolicy = try policyData([
            record(id: "fenix-8-47-yes", canonicalModel: "fenix 8", mapCapable: true,
                scope: "IN_SCOPE", installationAuthorization: "APPROVED"),
            record(id: "edge-840", canonicalModel: "Edge 840", mapCapable: false,
                scope: "OUT_OF_SCOPE", installationAuthorization: "BLOCKED"),
        ])
        let swappedDevice = await client(for: swappedDevicePolicy).resolve(identity: identity(
            model: "Edge 840", family: "Edge", displayType: "AMOLED",
            catalogDeviceID: "fenix-8-47-yes"))
        try require(swappedDevice.blockReason == .outOfScope,
                    "D/F: stale Fenix ID after Edge device swap cannot authorize the Edge")
        let swappedAbsent = await client(for: allMapsYesPolicy).resolve(identity: identity(
            model: "Edge 840", family: "Edge", displayType: "AMOLED",
            catalogDeviceID: "fenix-8-47"))
        try require(swappedAbsent.blockReason == .pending,
                    "F: Edge cannot inherit Fenix authorization when Edge has no policy row")
        let edgeHintedSelf = await client(for: edgeApprovedPolicy).resolve(identity: identity(
            model: "Edge 840", family: "Edge", displayType: nil,
            catalogDeviceID: "fenix-8-47"))
        try require(edgeHintedSelf.canInstall,
                    "D: stale prior-device ID cannot hide current Edge policy row")

        let unavailable = InstallationAuthorizationClient(dataLoader: { _ in
            throw URLError(.notConnectedToInternet)
        })
        let unavailableState = await unavailable.resolve(identity: identity())
        try require(unavailableState.blockReason == .catalogUnavailable,
                    "policy endpoint unavailability is CATALOG_UNAVAILABLE")

        let cachedApproval = await client(for: allMapsYesPolicy).resolve(identity: identity())
        try require(cachedApproval.canInstall,
                    "fixture starts with a previously approved cached policy")
        var providerAcquisitionStarted = false
        var authorizationCallbackCount = 0
        do {
            try await InstallationAuthorizationAcquisitionGate.run(
                identity: identity(),
                client: unavailable,
                onAuthorized: { _ in authorizationCallbackCount += 1 }
            ) {
                providerAcquisitionStarted = true
            }
            throw AuthorizationTestError.failed("unavailable fresh policy must block acquisition")
        } catch let error as InstallationAuthorizationAcquisitionError {
            try require(error.authorization.blockReason == .catalogUnavailable,
                        "fresh policy unavailability is preserved as the acquisition gate reason")
        }
        try require(!providerAcquisitionStarted && authorizationCallbackCount == 0,
                    "a cached approval cannot start acquisition when fresh policy is unavailable")

        let invalidManufacturer = try modifiedPolicy(allMapsYesPolicy) {
            $0["manufacturer"] = "Other"
        }
        let invalidManufacturerState = await client(for: invalidManufacturer).resolve(identity: identity())
        try require(invalidManufacturerState.blockReason == .catalogUnavailable,
                    "schema-invalid document manufacturer fails closed")

        let missingCapability = try modifiedPolicy(allMapsYesPolicy) { document in
            var devices = document["devices"] as! [[String: Any]]
            devices[0].removeValue(forKey: "mapCapable")
            document["devices"] = devices
        }
        let missingCapabilityState = await client(for: missingCapability).resolve(identity: identity())
        try require(missingCapabilityState.blockReason == .catalogUnavailable,
                    "missing required nullable Maps field is invalid, not a valid pending row")

        let contradictoryProjection = try modifiedPolicy(allMapsYesPolicy) { document in
            var devices = document["devices"] as! [[String: Any]]
            devices[1]["mapCapable"] = false
            document["devices"] = devices
        }
        let contradictoryState = await client(for: contradictoryProjection).resolve(identity: identity())
        try require(contradictoryState.blockReason == .outOfScope,
                    "Maps=No blocks even when redundant scope/authorization labels still say approved")

        let wrongMediaType = InstallationAuthorizationClient(dataLoader: { _ in
            response(allMapsYesPolicy, contentType: "text/html")
        })
        let wrongMediaTypeState = await wrongMediaType.resolve(identity: identity())
        try require(wrongMediaTypeState.blockReason == .catalogUnavailable,
                    "a non-JSON policy response cannot grant installation")

        print("PASS: installation authorization capability-based hierarchical matching")
    }
}
