import Foundation

// Isolate catalog decoding from the live USB transport, as in existing native runners.
protocol DeviceFileReader: Sendable {
    func readFileInventory() throws -> [DeviceFile]
    func readFilePrefix(for file: DeviceFile, maxLength: Int) throws -> [UInt8]
    func readFilePrefixes(for files: [DeviceFile], maxLength: Int) throws -> [UInt32: [UInt8]]
}

@main
struct SharedAPIContractTests {
    static func main() async throws {
        let mapData = try SharedContractFixtures.data("map-catalog.valid")
        let mapDecoder = MapCatalogDocumentDecoder()
        let catalog = try mapDecoder.decode(mapData)
        precondition(catalog.catalogVersion == 1 && !catalog.packages.isEmpty)
        let first = catalog.packages[0]
        precondition(first.downloadSizeBytes != first.installSizeBytes)

        var mapObject = try JSONSerialization.jsonObject(with: mapData) as! [String: Any]
        mapObject["futureField"] = ["nested": true]
        var providers = mapObject["providers"] as! [[String: Any]]
        providers[0]["futureProviderField"] = "ignored"
        var maps = providers[0]["maps"] as! [[String: Any]]
        maps[0]["futureMapField"] = ["ignored"]
        providers[0]["maps"] = maps
        mapObject["providers"] = providers
        let additive = try mapDecoder.decode(JSONSerialization.data(withJSONObject: mapObject))
        precondition(additive == catalog)
        // Public schema requires this field, but the existing native decoder ignores it.
        let legacy = try mapDecoder.decode(SharedContractFixtures.data("map-catalog.invalid-missing-schema-version"))
        precondition(legacy == catalog)
        try rejects {
            _ = try mapDecoder.decode(SharedContractFixtures.data("map-catalog.invalid-missing-providers"))
        }

        let deviceData = try SharedContractFixtures.data("device-catalog.valid")
        let devices = try JSONDecoder().decode(DeviceCatalogResponse.self, from: deviceData)
        precondition(devices.catalogVersion == 2 && devices.devices.count == 1)
        var deviceObject = try JSONSerialization.jsonObject(with: deviceData) as! [String: Any]
        deviceObject["futureField"] = true
        var records = deviceObject["devices"] as! [[String: Any]]
        records[0]["futureDeviceField"] = ["ignored": 1]
        deviceObject["devices"] = records
        let additiveDevices = try JSONDecoder().decode(DeviceCatalogResponse.self,
            from: JSONSerialization.data(withJSONObject: deviceObject))
        precondition(additiveDevices.devices[0].canonicalModel == devices.devices[0].canonicalModel)
        try rejects {
            _ = try JSONDecoder().decode(DeviceCatalogResponse.self,
                from: SharedContractFixtures.data("device-catalog.invalid-missing-canonical-model"))
        }

        // Runner places the unchanged bundled resource next to the executable.
        let bundled = try MapCatalogLoader(endpoint: nil).loadBundled()
        let fallback = try await MapCatalogLoader(endpoint: nil).loadRemoteThenFallback()
        precondition(fallback.source == .bundledFallback && fallback.catalog == bundled)
        precondition(!bundled.packages.isEmpty)
        print("PASS: shared catalogs decode, additive fields are ignored, invalid boundaries and bundled fallback are preserved")
    }

    static func rejects(_ work: () throws -> Void) throws {
        do { try work() } catch { return }
        throw NSError(domain: "SharedAPIContractTests.expectedRejection", code: 1)
    }
}
