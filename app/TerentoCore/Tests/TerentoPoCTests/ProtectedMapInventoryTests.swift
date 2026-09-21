import Foundation

@main
struct ProtectedMapInventoryTests {
    static func main() throws {
        var checks = 0
        func check(_ condition: Bool, _ label: String) {
            precondition(condition, label)
            checks += 1
        }
        func file(_ id: UInt32, _ path: String, size: UInt64 = 10,
                  folder: Bool = false, storage: UInt32 = 1, parent: UInt32 = 1) -> DeviceFile {
            DeviceFile(itemID: id, parentID: parent, storageID: storage, path: path,
                       filename: String(path.split(separator: "/").last!), sizeBytes: size, isFolder: folder)
        }
        let root = file(1, "/GARMIN", size: 0, folder: true)
        let map = file(2, "/GARMIN/D123.img")
        let base = [root, map]
        let baseline = try ProtectedMapInventory(files: base)
        func unchanged(_ rows: [DeviceFile], from before: ProtectedMapInventory = baseline) -> Bool {
            guard let after = try? ProtectedMapInventory(files: rows, forcedLocations: before.protectedLocations) else { return false }
            return after.difference(from: before).isEmpty
        }
        check(unchanged([file(101, "/GARMIN", size: 0, folder: true, parent: 99),
                         file(102, "/GARMIN/D123.img", parent: 101)]), "session handles ignored")
        check(!unchanged([root]), "map removal fails")
        check(!unchanged([root, file(2, "/GARMIN/renamed.img")]), "map rename fails")
        check(!unchanged([root, file(2, "/GARMIN/D123.img", size: 11)]), "map size fails")
        check(!unchanged([root, file(2, "/GARMIN/D123.img", folder: true)]), "map kind fails")
        check(!unchanged([root, map, file(3, "/GARMIN/new.img")]), "unexpected map addition fails")
        check(!unchanged([root, map, file(3, "/GARMIN/new.db")]), "unknown object protected")
        let movedStorage = [file(1, "/GARMIN", size: 0, folder: true, storage: 2),
                            file(2, "/GARMIN/D123.img", storage: 2)]
        check(!unchanged(movedStorage), "storage move fails")
        let xml = file(3, "/GARMIN/GarminDevice.xml")
        let withXML = try ProtectedMapInventory(files: base + [xml])
        check(unchanged(base + [file(3, xml.path, size: 42)], from: withXML), "exact XML size diagnostic")
        check(!unchanged(base + [file(3, xml.path, folder: true)], from: withXML), "XML folder protected")
        check(!unchanged(base + [file(3, "/GARMIN/other.xml")]), "no XML wildcard")
        let monitor = file(4, "/GARMIN/Monitor", size: 0, folder: true)
        let monitorBase = try ProtectedMapInventory(files: base + [monitor])
        let fit = file(5, "/GARMIN/Monitor/private.FIT")
        check(unchanged(base + [monitor, fit], from: monitorBase), "observed Monitor FIT addition diagnostic")
        let withFIT = try ProtectedMapInventory(files: base + [monitor, fit])
        check(unchanged(base + [monitor], from: withFIT), "observed Monitor FIT removal diagnostic")
        check(!unchanged(base + [file(6, "/GARMIN/elsewhere.FIT")]), "no FIT wildcard")
        check(!unchanged(base + [monitor, file(5, "/GARMIN/Monitor/state.db")], from: monitorBase), "unknown runtime file protected")
        let tlg = file(6, "/GARMIN/TLG", size: 0, folder: true)
        let per = file(7, "/GARMIN/TLG/PER", size: 0, folder: true)
        let runtimeBase = try ProtectedMapInventory(files: base + [tlg, per])
        let ephemeral = file(8, "/GARMIN/TLG/PER/session", size: 0, folder: true)
        check(unchanged(base + [tlg, per, ephemeral], from: runtimeBase), "observed runtime directory diagnostic")
        let runtimeWithFolder = try ProtectedMapInventory(files: base + [tlg, per, ephemeral])
        check(unchanged(base + [tlg, per], from: runtimeWithFolder), "runtime directory removal diagnostic")
        let nestedMap = file(9, "/GARMIN/TLG/PER/session/unknown.img")
        let nested = try ProtectedMapInventory(files: base + [tlg, per, ephemeral, nestedMap])
        check(nested.protectedLocations.contains(.init(storageID: 1, path: ephemeral.path)), "map ancestor overrides runtime directory")
        check(!unchanged(base + [tlg, per], from: nested), "map ancestor removal fails")
        for suffix in ["img", "GMA", "unl", "SID"] {
            let strange = file(10, "/unexpected.\(suffix)", storage: 9)
            let inventory = try ProtectedMapInventory(files: [strange])
            check(inventory.protected.count == 1, "map suffix all-storage protected \(suffix)")
        }
        let mapFolder = file(11, "/GARMIN/Map", size: 0, folder: true)
        let sidFolder = file(12, "/GARMIN/SID", size: 0, folder: true)
        for folder in [mapFolder, sidFolder] {
            let leaf = file(13, folder.path + "/state.FIT")
            let inventory = try ProtectedMapInventory(files: base + [folder, leaf])
            check(inventory.protectedLocations.contains(.init(storageID: 1, path: leaf.path)), "map container FIT protected")
        }
        let forced = try ProtectedMapInventory(files: base + [xml], forcedLocations: [.init(storageID: 1, path: xml.path)])
        check(!unchanged(base + [file(3, xml.path, size: 11)], from: forced), "explicit target overrides XML diagnostic")
        let invalidRows: [[DeviceFile]] = [
            base + [map],
            [file(1, "/GARMIN", folder: true, storage: 0)],
            base + [file(4, "/GARMIN/Monitor/orphan.FIT")],
            base + [file(4, "/GARMIN/TLG/PER/orphan", folder: true)],
            base + [tlg, file(7, "/GARMIN/TLG/PER"), ephemeral],
            base + [file(3, "/GARMIN/d123.IMG")],
            base + [file(2, "/GARMIN/other.img")],
            base + [file(0, "/GARMIN/zero.img")],
            [root, file(3, "/GARMIN/missing/map.img")],
            [root, file(3, "/GARMIN/child"), file(4, "/GARMIN/child/map.img")],
            [root, file(3, "/GARMIN/../map.img")],
            [root, file(3, "/GARMIN//map.img")],
            [DeviceFile(itemID: 1, parentID: 0, storageID: 1, path: "/GARMIN", filename: "wrong", sizeBytes: 0, isFolder: true)]
        ]
        for rows in invalidRows {
            check((try? ProtectedMapInventory(files: rows)) == nil, "ambiguous/malformed inventory fails closed")
        }
        print("PASS: \(checks) protected inventory checks")
    }
}
