import Foundation

/// Secondary metadata evidence, not mutation authorization or proof of byte equality.
/// Unknown objects remain protected. Only the observed, narrowly typed runtime
/// namespaces below are diagnostic; no extension grants a general exclusion.
struct ProtectedMapInventory: Sendable {
    struct Location: Hashable, Sendable {
        let storageID: UInt32
        let path: String
    }

    struct Key: Hashable, Sendable {
        let storageID: UInt32
        let path: String
        let filename: String
        let sizeBytes: UInt64
        let isFolder: Bool
        /// 0 for a unique location. Tolerated duplicate entries of one location
        /// are numbered in canonical order, so set equality is multiset equality.
        var occurrence: Int = 0

        var location: Location { Location(storageID: storageID, path: path) }
    }

    enum Invalid: Error, Equatable {
        case malformedLocation
        case ambiguousLocation
        case ambiguousHandle
        case missingAncestor
        case ancestorIsNotDirectory
    }

    struct Difference: Sendable {
        let removed: Set<Key>
        let added: Set<Key>
        var isEmpty: Bool { removed.isEmpty && added.isEmpty }
    }

    let protected: Set<Key>
    let diagnostic: Set<Key>
    /// Locations holding tolerated duplicate or alias entries (see below).
    let toleratedDuplicateLocationCount: Int
    var protectedLocations: Set<Location> { Set(protected.map(\.location)) }

    /// Duplicate or case-alias entries are tolerated only for plain files that
    /// are outside `/GARMIN` and not map-classified (for example two music
    /// tracks listed under one name). They stay protected and are compared as a
    /// multiset, so any change to them still fails. Folders, map files on any
    /// storage, and everything under `/GARMIN` (the write target, map
    /// containers and runtime namespaces) keep failing closed.
    static func toleratesDuplicateLocation(_ file: DeviceFile) -> Bool {
        guard !file.isFolder else { return false }
        let lower = file.path.lowercased()
        guard lower != "/garmin", !lower.hasPrefix("/garmin/") else { return false }
        let suffix = (file.filename as NSString).pathExtension.lowercased()
        return !mapSuffixes.contains(suffix)
    }

    /// Number of locations whose duplicate or alias entries are tolerated, or
    /// nil when the inventory has an untolerated duplicate or alias.
    static func toleratedDuplicateLocations(in files: [DeviceFile]) -> Int? {
        // An exact duplicate is also a case alias, so alias groups cover both.
        var aliases: [Location: [DeviceFile]] = [:]
        for file in files {
            aliases[Location(storageID: file.storageID, path: file.path.lowercased()), default: []].append(file)
        }
        var tolerated = 0
        for group in aliases.values where group.count > 1 {
            guard group.allSatisfy(toleratesDuplicateLocation) else { return nil }
            tolerated += 1
        }
        return tolerated
    }

    private static let mapSuffixes: Set<String> = ["img", "gma", "unl", "sid"]

    init(files: [DeviceFile], forcedLocations: Set<Location> = []) throws {
        var locations: [Location: DeviceFile] = [:]
        var handles = Set<UInt32>()
        var duplicates: [Location: [Int]] = [:]
        for (index, file) in files.enumerated() {
            let components = file.path.split(separator: "/", omittingEmptySubsequences: false)
            guard file.storageID != 0, file.path.hasPrefix("/"), components.count >= 2,
                  !components.dropFirst().contains(where: { $0.isEmpty || $0 == "." || $0 == ".." }),
                  !file.filename.isEmpty, !file.filename.contains("/"),
                  !file.filename.contains("\0"), !file.path.contains("\0"),
                  file.hasMatchingPathFilename else {
                throw Invalid.malformedLocation
            }
            guard file.itemID != 0, handles.insert(file.itemID).inserted else {
                throw Invalid.ambiguousHandle
            }
            let location = Location(storageID: file.storageID, path: file.path)
            if locations[location] != nil {
                duplicates[location, default: []].append(index)
                continue
            }
            locations[location] = file
        }
        // Exact and case-alias duplicates fail closed unless every entry of the
        // group is a tolerated plain file outside the map scope.
        guard let toleratedCount = Self.toleratedDuplicateLocations(in: files) else {
            throw Invalid.ambiguousLocation
        }
        toleratedDuplicateLocationCount = toleratedCount

        var keys = files.map { Self.key($0) }
        for location in duplicates.keys {
            let members = files.indices.filter {
                files[$0].storageID == location.storageID && files[$0].path == location.path
            }.sorted { lhs, rhs in
                let a = files[lhs], b = files[rhs]
                return (a.filename, a.sizeBytes) < (b.filename, b.sizeBytes)
            }
            for (occurrence, index) in members.enumerated() {
                keys[index] = Self.key(files[index], occurrence: occurrence)
            }
        }

        // Coherence is a property of the complete inventory, including runtime
        // observations. Classification must never hide orphaned objects.
        for location in locations.keys {
            var path = location.path
            while let slash = path.lastIndex(of: "/"), slash != path.startIndex {
                path = String(path[..<slash])
                guard let ancestor = locations[Location(storageID: location.storageID, path: path)] else {
                    throw Invalid.missingAncestor
                }
                guard ancestor.isFolder else { throw Invalid.ancestorIsNotDirectory }
            }
        }

        var required = forcedLocations
        for file in files {
            let location = Location(storageID: file.storageID, path: file.path)
            if !Self.isObservedRuntimeObject(file) { required.insert(location) }
        }
        // Preserve ancestry even when a protected object appears beneath a runtime
        // namespace. Never infer ancestry from session-scoped parent handles.
        for location in Array(required) {
            var path = location.path
            while let slash = path.lastIndex(of: "/"), slash != path.startIndex {
                path = String(path[..<slash])
                let ancestor = Location(storageID: location.storageID, path: path)
                guard let file = locations[ancestor] else { throw Invalid.missingAncestor }
                guard file.isFolder else { throw Invalid.ancestorIsNotDirectory }
                required.insert(ancestor)
            }
        }
        protected = Set(keys.filter { required.contains($0.location) })
        diagnostic = Set(keys.filter { !required.contains($0.location) })
    }

    func difference(from baseline: ProtectedMapInventory) -> Difference {
        Difference(removed: baseline.protected.subtracting(protected),
                   added: protected.subtracting(baseline.protected))
    }

    /// Exact expected replacement in the same canonical protected scope.
    /// Session handles never participate; this grants no mutation authority.
    func isExactReplacement(of baseline: ProtectedMapInventory, removing old: Key, adding new: Key) -> Bool {
        guard old.storageID == new.storageID, old.location != new.location,
              !old.isFolder, !new.isFolder,
              baseline.protected.contains(old),
              !baseline.protectedLocations.contains(new.location) else { return false }
        return protected == baseline.protected.subtracting([old]).union([new])
    }

    private static func key(_ file: DeviceFile, occurrence: Int = 0) -> Key {
        Key(storageID: file.storageID, path: file.path, filename: file.filename,
            sizeBytes: file.sizeBytes, isFolder: file.isFolder, occurrence: occurrence)
    }

    private static func isObservedRuntimeObject(_ file: DeviceFile) -> Bool {
        let lower = file.path.lowercased()
        let suffix = (file.filename as NSString).pathExtension.lowercased()
        // Map evidence wins over runtime location, including malformed folder
        // objects bearing a map filename. This is a positive protection rule.
        if mapSuffixes.contains(suffix)
            || lower == "/garmin/map" || lower.hasPrefix("/garmin/map/")
            || lower == "/garmin/sid" || lower.hasPrefix("/garmin/sid/") { return false }
        if file.path == "/GARMIN/GarminDevice.xml", !file.isFolder { return true }
        if !file.isFolder, suffix == "fit",
           file.path.hasPrefix("/GARMIN/Monitor/"),
           file.path.split(separator: "/").count == 3 { return true }
        if file.isFolder, file.path.hasPrefix("/GARMIN/TLG/PER/") { return true }
        return false
    }
}
