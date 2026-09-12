import Foundation

/// Pure list rules keep UI partitioning and search deterministic and testable.
enum MapSelectionPresentationModel: Sendable {
    /// The current product permits one provider per installation batch. The first selected
    /// provider therefore locks rows from other providers until the current
    /// selection is cleared. Custom files are provider-neutral and remain
    /// selectable alongside one provider.
    static func selectionProviderID(
        selectedIDs: Set<String>,
        items: [MapSelectionItem]
    ) -> String? {
        let providerIDs = Set(
            items
                .filter { selectedIDs.contains($0.id) && $0.package.sourceKind == .provider }
                .map { MapIdentity.normalizeProvider($0.package.providerId) }
        )
        guard providerIDs.count == 1 else { return nil }
        return providerIDs.first
    }

    static func isSelectionEnabled(
        _ item: MapSelectionItem,
        selectedIDs: Set<String>,
        items: [MapSelectionItem]
    ) -> Bool {
        guard item.isSelectable else { return false }
        guard item.package.sourceKind == .provider else { return true }

        if !selectedIDs.contains(item.id), MapIdentity.normalizeProvider(item.package.providerId) == "bbbike",
           items.contains(where: { other in
               other.id != item.id && MapIdentity.normalizeProvider(other.package.providerId) == "bbbike"
                   && other.package.providerRegionId == item.package.providerRegionId
                   && other.package.mapType != item.package.mapType
                   && (selectedIDs.contains(other.id) || other.comparison.installedMap != nil)
           }) { return false }

        let selectedProviderIDs = Set(
            items
                .filter { selectedIDs.contains($0.id) && $0.package.sourceKind == .provider }
                .map { MapIdentity.normalizeProvider($0.package.providerId) }
        )

        if selectedProviderIDs.count > 1 {
            // Recoverable defensive state: allow deselection of the already
            // selected rows, but prevent adding another provider.
            return selectedIDs.contains(item.id)
        }

        guard let selectedProviderID = selectedProviderIDs.first else {
            return true
        }

        return selectedIDs.contains(item.id)
            || MapIdentity.normalizeProvider(item.package.providerId) == selectedProviderID
    }

    static func validSelectionIDs(
        _ selectedIDs: Set<String>,
        items: [MapSelectionItem]
    ) -> Set<String> {
        selectedIDs.intersection(Set(items.filter(\.isSelectable).map(\.id)))
    }

    static func installed(_ items: [MapSelectionItem]) -> [MapSelectionItem] {
        items
            .filter { $0.comparison.installedMap != nil }
            .sorted { lhs, rhs in
                if lhs.comparison.status != rhs.comparison.status {
                    return lhs.comparison.status == .updateAvailable
                }
                return lhs.title.localizedCaseInsensitiveCompare(rhs.title) == .orderedAscending
            }
    }

    /// Returns only supported provider maps that are present in the current
    /// device inventory. Ownership controls lifecycle actions, not whether a
    /// recognized map is visible in the Installed section.
    static func supportedInstalled(
        _ items: [MapSelectionItem],
        inventory: UnifiedMapInventory?
    ) -> [MapSelectionItem] {
        guard let inventory else {
            return []
        }

        let recognizedCatalogIDs = Set(
            inventory.providerGroups
                .flatMap(\.entries)
                .compactMap { entry -> String? in
                guard entry.isInstalled,
                      !entry.installedMaps.isEmpty,
                      entry.installedMaps.allSatisfy({ $0.metadataStatus == .parsed }),
                      entry.managementState == .managedByTerento
                        || entry.managementState == .detectedNotManaged else {
                    return nil
                }

                return entry.comparison?.id
                }
        )

        return installed(items).filter { recognizedCatalogIDs.contains($0.id) }
    }

    /// Returns the maps that belong in the Install catalogue.
    ///
    /// Normal browsing is intentionally limited to new-install candidates.
    /// A non-empty search may also reveal an installed catalog match so the
    /// user can understand why that region is not available to install here;
    /// the row remains non-selectable and lifecycle actions stay in Manage.
    static func available(
        _ items: [MapSelectionItem],
        query: String
    ) -> [MapSelectionItem] {
        MapCatalogPresentationIndex(items: items).filtered(query: query)
    }

}

/// A visual-only projection of the conservative storage plan. It keeps the
/// segmented bar aligned with the same plan used by the Continue/Install CTA.
struct StorageBarProjection: Equatable, Sendable {
    let existingUsedBytes: UInt64
    let selectedMapBytes: UInt64
    let freeAfterInstallationBytes: UInt64

    init(plan: StoragePlan, totalCapacity: UInt64) {
        guard totalCapacity > 0 else {
            existingUsedBytes = 0
            selectedMapBytes = 0
            freeAfterInstallationBytes = 0
            return
        }

        let currentFreeSpace = min(plan.currentFreeSpace, totalCapacity)
        let existingUsed = totalCapacity - currentFreeSpace
        let availableBeforeSelection = totalCapacity - existingUsed
        let selected = plan.hasUnresolvedInstallSize
            ? 0
            : min(plan.selectedMapBytes, availableBeforeSelection)
        let availableAfterSelection = availableBeforeSelection - selected
        let freeAfter = plan.hasUnresolvedInstallSize
            ? currentFreeSpace
            : min(plan.projectedFreeSpace, availableAfterSelection)

        existingUsedBytes = existingUsed
        selectedMapBytes = selected
        freeAfterInstallationBytes = freeAfter
    }

    func fraction(for bytes: UInt64) -> Double {
        let total = existingUsedBytes
            .addingReportingOverflow(selectedMapBytes)
        guard !total.overflow else {
            return 0
        }

        let resolvedTotal = total.partialValue
            .addingReportingOverflow(freeAfterInstallationBytes)
        guard !resolvedTotal.overflow, resolvedTotal.partialValue > 0 else {
            return 0
        }

        let fraction = Double(bytes) / Double(resolvedTotal.partialValue)
        return fraction.isFinite ? min(1, max(0, fraction)) : 0
    }
}

enum InstallReviewAction: String, Equatable, Sendable {
    case prepare
    case install
}

enum InstallReviewAvailability: Equatable, Sendable {
    case ready(InstallReviewAction)
    case blocked(String)

    var isEnabled: Bool {
        if case .ready = self {
            return true
        }
        return false
    }

    var userReason: String? {
        if case let .blocked(reason) = self {
            return reason
        }
        return nil
    }
}

/// Resolves the review CTA from the same plan and lifecycle state rendered by
/// the screen. A positive storage message never enables an action that the
/// underlying installation path cannot safely execute.
struct InstallReviewAvailabilityResolver: Sendable {
    func resolve(
        plan: InstallationPlan?,
        deviceConnected: Bool,
        supportedInstallFlow: Bool,
        installationPhase: InstallationProcessPhase,
        hasValidatedArtifact: Bool,
        operationBusy: Bool
    ) -> InstallReviewAvailability {
        guard let plan else {
            return .blocked("Select a map to continue.")
        }
        guard plan.canContinue else {
            return .blocked(plan.reason)
        }
        guard deviceConnected else {
            return .blocked("Reconnect your Garmin to continue.")
        }
        guard supportedInstallFlow else {
            return .blocked("This map cannot be installed safely on this Garmin yet.")
        }
        if let conflictMessage = InstallationFlowPresentation.conflictMessage(
            flowOwnsOperation: false,
            independentOperationBusy: operationBusy
        ) {
            return .blocked(conflictMessage)
        }

        switch installationPhase {
        case .idle:
            return .ready(.prepare)
        case .awaitingConfirmation where hasValidatedArtifact:
            return .ready(.install)
        case .awaitingConfirmation:
            return .blocked("Installation checks are still in progress.")
        case .downloading, .preparing, .installing, .finishing:
            return .blocked("Installation is already in progress.")
        case .completed:
            return .blocked("This installation has already completed.")
        case .failed:
            return .blocked("The installation check needs to be run again.")
        }
    }
}

enum MapRowDividerPolicy: Sendable {
    static func showsDivider(at index: Int, in count: Int) -> Bool {
        index >= 0 && index < count - 1
    }
}

/// Presentation-only state rules for the native installation flow. The map
/// engine remains the source of truth for the transaction itself; this keeps
/// navigation, sidebar status, and the active screen in sync with that state.
enum InstallationFlowPresentation: Sendable {
    static func hasStarted(_ phase: InstallationProcessPhase) -> Bool {
        phase != .idle
    }

    static func isActive(_ phase: InstallationProcessPhase) -> Bool {
        switch phase {
        case .downloading, .preparing, .awaitingConfirmation, .installing, .finishing:
            return true
        case .idle, .completed, .failed:
            return false
        }
    }

    static func conflictMessage(
        flowOwnsOperation: Bool,
        independentOperationBusy: Bool
    ) -> String? {
        guard independentOperationBusy, !flowOwnsOperation else {
            return nil
        }

        return "Another device operation is in progress."
    }

    static func shouldContinueAfterPreflight(
        userAuthorized: Bool,
        preflightSucceeded: Bool
    ) -> Bool {
        userAuthorized && preflightSucceeded
    }
}

/// Geographic browsing is a local presentation projection, never acquisition identity.
enum MapGeographyGroup: String, CaseIterable, Identifiable, Sendable {
    case all, europe, asia, africa, northAmerica, centralAmericaCaribbean
    case southAmerica, oceania, antarctica, other
    var id: String { rawValue }
    var title: String {
        switch self {
        case .all: return "All regions"
        case .europe: return "Europe"
        case .asia: return "Asia"
        case .africa: return "Africa"
        case .northAmerica: return "North America"
        case .centralAmericaCaribbean: return "Central America & Caribbean"
        case .southAmerica: return "South America"
        case .oceania: return "Oceania"
        case .antarctica: return "Antarctica"
        case .other: return "Other regions"
        }
    }
}

/// Build once per authoritative selection snapshot. Filtering never calls preflight.
struct MapCatalogPresentationIndex: Sendable {
    private struct Row: Sendable {
        let item: MapSelectionItem
        let provider: String
        let text: String
        let groups: Set<MapGeographyGroup>
    }
    private let rows: [Row]
    var geographyOptions: [MapGeographyGroup] {
        MapGeographyGroup.allCases.filter { $0 != .other || rows.contains { $0.groups.contains(.other) } }
    }
    init(items: [MapSelectionItem]) {
        rows = items.filter { $0.package.sourceKind == .provider }.map { item in
            let geography = CatalogGeography.resolve(item)
            return Row(item: item, provider: MapProviderDisplay.filterID(providerID: item.package.providerId, regionID: item.package.canonicalRegionId),
                       text: CatalogGeography.fold(geography.terms.joined(separator: " ")),
                       groups: geography.groups)
        }.sorted { lhs, rhs in
            if lhs.item.isRecommended != rhs.item.isRecommended { return lhs.item.isRecommended }
            let titleOrder = lhs.item.title.localizedCaseInsensitiveCompare(rhs.item.title)
            if titleOrder != .orderedSame { return titleOrder == .orderedAscending }
            if lhs.provider != rhs.provider { return lhs.provider < rhs.provider }
            return lhs.item.id < rhs.item.id
        }
    }
    func filtered(query: String, providerID: String = "", geography: MapGeographyGroup = .all) -> [MapSelectionItem] {
        let terms = CatalogGeography.fold(query).split(whereSeparator: { $0.isWhitespace }).map(String.init)
        let provider = MapIdentity.normalizeProvider(providerID)
        return rows.compactMap { row in
            guard (providerID.isEmpty || row.provider == provider),
                  (geography == .all || row.groups.contains(geography)),
                  (!terms.isEmpty || row.item.comparison.installedMap == nil),
                  terms.allSatisfy({ row.text.contains($0) }) else { return nil }
            return row.item
        }
    }
}

private enum CatalogGeography {
    static func fold(_ text: String) -> String {
        text.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: Locale(identifier: "en_US_POSIX"))
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
    private static let countries: [MapGeographyGroup: String] = [
        .europe: "AL AD AT BY BE BA BG HR CY CZ DK EE FI FR DE GI GR GG VA HU IS IE IM IT JE XK LV LI LT LU MT MD MC ME NL MK NO PL PT RO RU SM RS SK SI ES SJ SE CH TR UA GB AX FO",
        .asia: "AF AM AZ BH BD BT BN KH CN CY GE HK IN ID IR IQ IL JP JO KZ KP KR KW KG LA LB MO MY MV MN MM NP OM PK PS PH QA RU SA SG LK SY TW TJ TH TL TR TM AE UZ VN YE",
        .africa: "DZ AO BJ BW BF BI CV CM CF TD KM CG CD CI DJ EG GQ ER SZ ET GA GM GH GN GW KE LS LR LY MG MW ML MR MU YT MA MZ NA NE NG RE RW SH ST SN SC SL SO ZA SS SD TZ TG TN UG EH ZM ZW",
        .northAmerica: "CA US MX GL PM BM",
        .centralAmericaCaribbean: "AI AG AW BS BB BZ BQ VG KY CR CU CW DM DO SV GD GP GT HT HN JM MQ MS NI PA PR BL KN LC MF VC SX TT TC VI",
        .southAmerica: "AR BO BR CL CO EC FK GF GY PY PE SR UY VE",
        .oceania: "AS AU CX CC CK FJ PF GU KI MH FM NR NC NZ NU NF MP PW PG PN WS SB TK TO TV UM VU WF",
        .antarctica: "AQ BV GS HM TF"
    ]
    private static let groupsByCode: [String: Set<MapGeographyGroup>] = {
        var result: [String: Set<MapGeographyGroup>] = [:]
        for (group, codes) in countries {
            for code in codes.split(separator: " ") { result[String(code), default: []].insert(group) }
        }
        return result
    }()
    private static let namesByCode: [String: [String]] = {
        Dictionary(uniqueKeysWithValues: groupsByCode.keys.map { code in
            (code, ["en", "lt", "fr", "de"].compactMap { Locale(identifier: $0).localizedString(forRegionCode: code) })
        })
    }()
    private static func geographicKey(_ value: String) -> String {
        fold(value).filter { $0.isLetter || $0.isNumber }
    }
    private static let codeByName: [String: String] = {
        var result: [String: String] = [:]
        for (code, names) in namesByCode { for name in names { result[geographicKey(name)] = code } }
        for (name, code) in ["china":"CN", "turkey":"TR", "czech republic":"CZ", "russia":"RU", "south korea":"KR", "north korea":"KP", "ivory coast":"CI", "swaziland":"SZ"] { result[geographicKey(name)] = code }
        return result
    }()
    private static func code(_ value: String) -> String? {
        let value = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if groupsByCode[value.uppercased()] != nil { return value.uppercased() }
        if let code = codeByName[geographicKey(MapDisplayNameNormalizer.normalize(value))] { return code }
        // Accept whole ISO3 tokens as geography, never arbitrary provider identifiers.
        if value.count == 3, value.allSatisfy({ $0.isASCII && $0.isLetter }),
           let name = Locale(identifier: "en").localizedString(forRegionCode: value.uppercased()) {
            return codeByName[geographicKey(name)]
        }
        return nil
    }
    // Reviewed names from the bundled FZK/OTM catalog. Metadata-only aliases;
    // they neither restrict catalog membership nor change policy identities.
    private static let regionalCountries: [String: [String]] = [
        "alps": ["AT", "CH", "DE", "FR", "IT", "LI", "SI"],
        "alpes": ["AT", "CH", "DE", "FR", "IT", "LI", "SI"],
        "dach": ["DE", "AT", "CH"], "regionbalkans": ["AL", "BA", "BG", "HR", "GR", "ME", "MK", "RS", "SI", "XK"],
        "regionbelgiumnetherlandsluxembourg": ["BE", "NL", "LU"],
        "britishisles": ["GB", "IE"], "greatbritain": ["GB"],
        "irelandandnorthernireland": ["IE", "GB"],
        "bosniaherzegovina": ["BA"], "macedonia": ["MK"],
        "canadaeast": ["CA"], "canadawest": ["CA"],
        "canaryislands": ["ES"], "canarias": ["ES"], "ilescanaries": ["ES"],
        "azores": ["PT"], "acores": ["PT"], "madeira": ["PT"], "balearics": ["ES"],
        "capeverde": ["CV"], "comores": ["KM"],
        "congobrazzaville": ["CG"], "congodemocraticrepublic": ["CD"],
        "faeroeislands": ["FO"], "faroeislands": ["FO"],
        "gccstates": ["AE", "BH", "KW", "OM", "QA", "SA"],
        "haitianddomrep": ["HT", "DO"], "israelandpalestine": ["IL", "PS"],
        "malaysiasingaporebrunei": ["MY", "SG", "BN"],
        "sainthelenaascensionandtristandacunha": ["SH"],
        "saotomeandprincipe": ["ST"], "senegalandgambia": ["SN", "GM"],
        "southafricaandlesotho": ["ZA", "LS"],
        "usmidwest": ["US"], "usnortheast": ["US"], "uspacific": ["US"], "ussouth": ["US"], "uswest": ["US"]
    ]
    private static let regionalGroups: [String: Set<MapGeographyGroup>] = [
        "azores": [.europe], "acores": [.europe], "balearics": [.europe],
        "canaryislands": [.africa], "canarias": [.africa], "ilescanaries": [.africa], "madeira": [.africa],
        "reunion": [.africa], "mayotte": [.africa],
        "guadeloupe": [.centralAmericaCaribbean], "martinique": [.centralAmericaCaribbean],
        "stbarthelemy": [.centralAmericaCaribbean], "saintbarthelemy": [.centralAmericaCaribbean],
        "stmartin": [.centralAmericaCaribbean], "saintmartin": [.centralAmericaCaribbean],
        "frenchguiana": [.southAmerica], "guyane": [.southAmerica],
        "newcaledonia": [.oceania], "nouvellecaledonie": [.oceania], "hawaii": [.oceania],
        "frenchpolynesia": [.oceania], "polynesiefrancaise": [.oceania],
        // Reviewed multi-territory geography; these filters do not invent country membership.
        "americanoceania": [.oceania],
        "frenchsouthernandantarcticlands": [.africa, .antarctica],
        "russiaasianpart": [.asia], "russiaeuropeanpart": [.europe],
        "russiacentral": [.europe], "russiakaliningrad": [.europe], "kaliningrad": [.europe],
        "russianorthwest": [.europe], "russiasouth": [.europe], "russiavolga": [.europe]
    ]
    static func resolve(_ item: MapSelectionItem) -> (terms: [String], groups: Set<MapGeographyGroup>) {
        let package = item.package
        // Style annotations are not geography. Preserve the region outside parentheses.
        let region = item.title.replacingOccurrences(
            of: #"(?i)\s*\([^)]*(?:contours?|IGN|latin1|UTF-?8|ASCII|style)[^)]*\)"#,
            with: "", options: .regularExpression)
            .replacingOccurrences(of: #"(?i)\b(?:IGN|contours?|courbes|latin1|UTF-?8|ASCII|style)\b"#, with: "", options: .regularExpression)
        var terms = [region]
        var codes = Set(package.countryCodes.compactMap(code))
        if let identity = item.canonicalRegionIdentity, let canonical = code(identity.countryCode) { codes.insert(canonical) }
        if let regionCode = code(region) { codes.insert(regionCode) }
        if let regionCode = code(package.regionId) { codes.insert(regionCode) }
        let key = geographicKey(region)
        codes.formUnion(regionalCountries[key] ?? [])
        // Region-level overrides take precedence over sovereign-country coverage.
        let overrideGroups = regionalGroups[key]
        if item.canonicalRegionIdentity == CanonicalMapRegionIdentity(countryCode: "UA", locality: "CRIMEA") {
            codes = ["UA"]; terms = ["Crimea", "Ukraine", "UA"]
        }
        for country in codes {
            terms.append(country)
            terms.append(contentsOf: namesByCode[country] ?? [])
        }
        // Retain geographic ISO3 search such as DEU without indexing raw package IDs.
        if package.regionId.count == 3, code(package.regionId) != nil { terms.append(package.regionId) }
        let groups = overrideGroups ?? codes.reduce(into: Set<MapGeographyGroup>()) { $0.formUnion(groupsByCode[$1] ?? []) }
        return (terms, groups.isEmpty ? [.other] : groups)
    }
}
