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
    var protectedLocations: Set<Location> { Set(protected.map(\.location)) }

    init(files: [DeviceFile], forcedLocations: Set<Location> = []) throws {
        var locations: [Location: DeviceFile] = [:]
        var aliases = Set<Location>()
        var handles = Set<UInt32>()
        for file in files {
            let components = file.path.split(separator: "/", omittingEmptySubsequences: false)
            guard file.storageID != 0, file.path.hasPrefix("/"), components.count >= 2,
                  !components.dropFirst().contains(where: { $0.isEmpty || $0 == "." || $0 == ".." }),
                  !file.filename.isEmpty, !file.filename.contains("/"),
                  !file.filename.contains("\0"), !file.path.contains("\0"),
                  components.last.map(String.init) == file.filename else {
                throw Invalid.malformedLocation
            }
            let location = Location(storageID: file.storageID, path: file.path)
            let alias = Location(storageID: file.storageID, path: file.path.lowercased())
            guard locations[location] == nil, aliases.insert(alias).inserted else {
                throw Invalid.ambiguousLocation
            }
            guard file.itemID != 0, handles.insert(file.itemID).inserted else {
                throw Invalid.ambiguousHandle
            }
            locations[location] = file
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
        protected = Set(files.filter { required.contains(Location(storageID: $0.storageID, path: $0.path)) }.map(Self.key))
        diagnostic = Set(files.filter { !required.contains(Location(storageID: $0.storageID, path: $0.path)) }.map(Self.key))
    }

    func difference(from baseline: ProtectedMapInventory) -> Difference {
        Difference(removed: baseline.protected.subtracting(protected),
                   added: protected.subtracting(baseline.protected))
    }

    private static func key(_ file: DeviceFile) -> Key {
        Key(storageID: file.storageID, path: file.path, filename: file.filename,
            sizeBytes: file.sizeBytes, isFolder: file.isFolder)
    }

    private static func isObservedRuntimeObject(_ file: DeviceFile) -> Bool {
        let lower = file.path.lowercased()
        let suffix = (file.filename as NSString).pathExtension.lowercased()
        // Map evidence wins over runtime location, including malformed folder
        // objects bearing a map filename. This is a positive protection rule.
        if ["img", "gma", "unl", "sid"].contains(suffix)
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
