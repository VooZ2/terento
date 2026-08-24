import Foundation

@main
struct DeviceAssetMatchingTests {
    static func main() async {
        testCompatibilityIsIndependent()
        testControlledURLsResolveRelativeAPIPaths()
        testCatalogJSONDecoding()
        await testMissingAssetUsesFallback()
        await testUnknownDeviceUsesFallback()
        await testCacheAndVersionRefresh()
        await testRealMTPIdentityResolvesModelSizeAsset()
        await testOfficialGarminSourceImageFallback()

        let exactURL = URL(string: "https://api.terento.app/assets/devices/garmin/fenix8-exact.webp")!
        let modelSizeURL = URL(string: "https://api.terento.app/assets/devices/garmin/fenix8-size.webp")!
        let modelURL = URL(string: "https://api.terento.app/assets/devices/garmin/fenix8-model.webp")!
        let familyURL = URL(string: "https://api.terento.app/assets/devices/garmin/fenix-family.webp")!
        let genericURL = URL(string: "https://api.terento.app/assets/devices/garmin/generic.webp")!
        let officialSource = DeviceAssetSource(
            type: "OFFICIAL_PRODUCT_MEDIA",
            brand: "Garmin",
            attributionRequired: true
        )

        let complete = identity(variant: "AMOLED 47mm")
        let partial = identity(variant: "47mm")

        let exactRecord = record(
            id: "garmin-fenix-8-47-amoled",
            canonicalModel: "fenix 8",
            caseSizeMm: 47,
            displayType: "AMOLED",
            asset: DeviceCatalogAsset(url: exactURL, scope: "EXACT_VARIANT", source: officialSource)
        )
        let sizeRecord = record(
            id: "garmin-fenix-8-47",
            canonicalModel: "fenix 8",
            caseSizeMm: 47,
            displayType: "AMOLED",
            asset: DeviceCatalogAsset(url: modelSizeURL, scope: "MODEL_SIZE", source: officialSource)
        )
        let modelRecord = record(
            id: "garmin-fenix-8",
            canonicalModel: "fenix 8",
            caseSizeMm: nil,
            displayType: nil,
            asset: DeviceCatalogAsset(url: modelURL, scope: "MODEL", source: officialSource)
        )
        let familyRecord = record(
            id: "garmin-fenix-9",
            canonicalModel: "fenix 9",
            caseSizeMm: 51,
            displayType: "AMOLED",
            asset: DeviceCatalogAsset(url: familyURL, scope: "FAMILY", source: officialSource)
        )
        let genericRecord = record(
            id: "garmin-forerunner-1",
            family: "Forerunner",
            canonicalModel: "forerunner 1",
            caseSizeMm: nil,
            displayType: nil,
            asset: DeviceCatalogAsset(url: genericURL, scope: "GENERIC", source: officialSource)
        )

        expect(
            DeviceCatalogAssetResolver.matchingAsset(
                identity: complete,
                canonicalModel: "fēnix 8",
                records: [sizeRecord, exactRecord]
            )?.scope == "EXACT_VARIANT",
            "exact variant wins when all identity evidence is known"
        )
        expect(
            DeviceCatalogAssetResolver.matchingAsset(
                identity: partial,
                canonicalModel: "fēnix 8",
                records: [exactRecord, sizeRecord]
            )?.scope == "MODEL_SIZE",
            "model-size fallback is used when display type is unknown"
        )
        expect(
            DeviceCatalogAssetResolver.matchingAsset(
                identity: partial,
                canonicalModel: "fēnix 8",
                records: [familyRecord, modelRecord]
            )?.scope == "MODEL",
            "model fallback is used when no size-specific asset exists"
        )
        expect(
            DeviceCatalogAssetResolver.matchingAsset(
                identity: partial,
                canonicalModel: "fēnix 8",
                records: [familyRecord]
            )?.scope == "FAMILY",
            "family fallback does not claim another model"
        )
        expect(
            DeviceCatalogAssetResolver.matchingAsset(
                identity: partial,
                canonicalModel: "fēnix 8",
                records: [genericRecord]
            )?.scope == "GENERIC",
            "generic fallback is deterministic for an unrelated device"
        )
        expect(officialSource.isValid, "official product media source requires Garmin attribution")
        expect(
            !DeviceAssetSource(
                type: "OFFICIAL_PRODUCT_MEDIA",
                brand: "Garmin",
                attributionRequired: false
            ).isValid,
            "official product media without attribution is rejected"
        )
        print("PASS: 19 device asset matching, cache, and compatibility tests")
    }

    private static func testCompatibilityIsIndependent() {
        let snapshot = DeviceSnapshot(
            manufacturer: "Garmin",
            model: "fenix 8 - 47mm",
            deviceVersion: "20.00",
            vendorID: 0x091e,
            productID: 0x51b8,
            storages: [
                StorageInfo(
                    id: 1,
                    description: "Garmin",
                    volumeIdentifier: "test",
                    maximumCapacity: 1_000,
                    freeSpace: 500
                )
            ]
        )
        let engine = CompatibilityEngine()
        let before = engine.evaluate(snapshot: snapshot).status
        _ = DeviceAssetResolver.matchingAsset(
            identity: identity(variant: "AMOLED 47mm"),
            canonicalModel: "fēnix 8",
            records: []
        )
        let after = engine.evaluate(snapshot: snapshot).status

        expect(before == .tested && after == before, "asset resolution cannot change compatibility status")
    }

    private static func testControlledURLsResolveRelativeAPIPaths() {
        let relative = URL(string: "/assets/devices/garmin/fenix-8.webp")!
        let external = URL(string: "https://www.garmin.com/assets/devices/fenix-8.webp")!

        expect(
            DeviceAssetResolver.controlledURL(for: relative)?.absoluteString
                == "https://api.terento.app/assets/devices/garmin/fenix-8.webp",
            "relative API asset URL resolves against the API origin"
        )
        expect(
            DeviceAssetResolver.controlledURL(for: external) == nil,
            "asset URL from an uncontrolled origin is rejected"
        )
    }

    private static func testCatalogJSONDecoding() {
        let payload = Data(
            "{\"catalogVersion\":2,\"legal\":{\"manufacturerNotice\":true,\"text\":\"Terento notice\"},\"devices\":[{\"id\":\"garmin-fenix-8-47-amoled\",\"manufacturer\":\"Garmin\",\"family\":\"fenix\",\"model\":\"fēnix 8\",\"canonicalModel\":\"fenix 8\",\"variant\":\"47 mm, AMOLED\",\"caseSizeMm\":47,\"displayType\":\"AMOLED\",\"asset\":{\"status\":\"AVAILABLE\",\"url\":\"/assets/devices/garmin/fenix-8-47-amoled.webp\",\"version\":1,\"scope\":\"EXACT_VARIANT\",\"attribution\":\"Garmin media\",\"source\":{\"type\":\"OFFICIAL_PRODUCT_MEDIA\",\"brand\":\"Garmin\",\"attributionRequired\":true}}}]}".utf8
        )
        let decoded = try? JSONDecoder().decode(DeviceCatalogResponse.self, from: payload)

        expect(
            decoded?.catalogVersion == 2
                && decoded?.devices.first?.asset?.url?.absoluteString == "/assets/devices/garmin/fenix-8-47-amoled.webp"
                && decoded?.devices.first?.asset?.source?.type == "OFFICIAL_PRODUCT_MEDIA"
                && decoded?.devices.first?.asset?.attribution == "Garmin media",
            "version-2 catalog JSON preserves asset and attribution metadata"
        )
    }

    private static func testMissingAssetUsesFallback() async {
        let client = MockDeviceCatalogClient(
            catalog: catalog(
                asset: DeviceCatalogAsset(status: "MISSING", url: nil, scope: nil)
            ),
            assetData: Data("unused".utf8)
        )
        let result = await DeviceAssetResolver(client: client).resolve(identity: identity(variant: "AMOLED 47mm"))

        expect(result.isFallback && client.assetDownloadCount == 0, "MISSING asset uses the Terento fallback")
    }

    private static func testUnknownDeviceUsesFallback() async {
        let client = MockDeviceCatalogClient(
            catalog: catalog(
                asset: DeviceCatalogAsset(
                    url: URL(string: "/assets/devices/garmin/generic.webp"),
                    scope: "GENERIC",
                    source: officialSource
                )
            ),
            assetData: Data("unused".utf8)
        )
        let unknown = DeviceIdentity(
            manufacturer: "Garmin",
            model: "unknown smartwatch",
            family: nil,
            variant: nil,
            usbVendorId: 0x091e,
            usbProductId: 0xffff,
            firmware: nil,
            storageCapacity: 0,
            freeSpace: 0
        )
        let result = await DeviceAssetResolver(client: client).resolve(identity: unknown)

        expect(result.isFallback && client.assetDownloadCount == 0, "unknown identity uses the generic Terento fallback")
    }

    private static func testCacheAndVersionRefresh() async {
        let cacheDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-device-assets-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: cacheDirectory) }

        let firstAsset = DeviceCatalogAsset(
            url: URL(string: "/assets/devices/garmin/fenix-8.webp"),
            scope: "MODEL",
            version: 1,
            attribution: "Garmin approved product media",
            source: officialSource
        )
        let client = MockDeviceCatalogClient(
            catalog: catalog(asset: firstAsset),
            assetData: Data("asset-v1".utf8)
        )
        let resolver = DeviceAssetResolver(
            client: client,
            cache: DeviceAssetCache(directory: cacheDirectory)
        )

        let first = await resolver.resolve(identity: identity(variant: "AMOLED 47mm"))
        let second = await resolver.resolve(identity: identity(variant: "AMOLED 47mm"))

        expect(!first.isFallback, "first asset load downloads and resolves the asset")
        expect(client.assetDownloadCount == 1 && second.cachedFileURL == first.cachedFileURL, "second asset load uses the local cache")
        expect(
            first.assetSource?.type == "OFFICIAL_PRODUCT_MEDIA"
                && first.attributionRequired
                && first.assetAttribution == "Garmin approved product media"
                && first.legalManufacturerNotice == true
                && first.legalNotice?.contains("not affiliated with Garmin") == true,
            "asset source and legal metadata are preserved in the resolved model"
        )

        client.catalog = catalog(
            asset: DeviceCatalogAsset(
                url: firstAsset.url,
                scope: "MODEL",
                version: 2,
                attribution: "Garmin approved product media",
                source: officialSource
            )
        )
        client.assetData = Data("asset-v2".utf8)
        let refreshed = await resolver.resolve(identity: identity(variant: "AMOLED 47mm"))

        expect(
            client.assetDownloadCount == 2
                && refreshed.cachedFileURL != first.cachedFileURL
                && (try? Data(contentsOf: refreshed.cachedFileURL!)) == Data("asset-v2".utf8),
            "asset version changes refresh the local cache"
        )
    }

    private static func testRealMTPIdentityResolvesModelSizeAsset() async {
        let snapshot = DeviceSnapshot(
            manufacturer: "Garmin",
            model: "fenix 8 - 47mm",
            deviceVersion: "2243",
            vendorID: 0x091e,
            productID: 0x51b8,
            storages: []
        )
        let identity = GarminDeviceIdentityAdapter().makeIdentity(from: snapshot)
        expect(identity.variant == "47mm", "real MTP model derives the 47mm variant")
        expect(identity.canonicalModel == "fēnix 8", "real MTP model derives the canonical fēnix 8 model")
        let asset = DeviceCatalogAsset(
            url: URL(string: "/assets/devices/garmin/fenix-8-47.webp"),
            scope: "MODEL_SIZE",
            version: 1,
            source: officialSource
        )
        let client = MockDeviceCatalogClient(
            catalog: DeviceCatalogResponse(
                catalogVersion: 2,
                legal: nil,
                devices: [
                    record(
                        id: "garmin-fenix-8-47",
                        canonicalModel: "fenix 8",
                        caseSizeMm: 47,
                        displayType: "AMOLED",
                        asset: asset
                    )
                ]
            ),
            assetData: Data("real-mtp-identity-asset".utf8)
        )
        let cacheDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-real-mtp-asset-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: cacheDirectory) }

        let result = await DeviceAssetResolver(
            client: client,
            cache: DeviceAssetCache(directory: cacheDirectory)
        ).resolve(identity: identity)
        let directMatch = DeviceAssetResolver.matchingAsset(
            identity: identity,
            canonicalModel: identity.canonicalModel ?? "",
            records: client.catalog.devices
        )
        expect(directMatch?.scope == "MODEL_SIZE", "real MTP identity matches the model-size catalog record")

        expect(
            identity.variant == "47mm"
                && result.scope == .modelSize
                && !result.isFallback
                && client.assetDownloadCount == 1,
            "real MTP model fenix 8 - 47mm resolves the model-size asset"
        )
    }

    private static func testOfficialGarminSourceImageFallback() async {
        let sourceURL = URL(string: "https://res.garmin.com/en/products/010-02891-00/g/cf-lg.jpg")!
        let sourceAsset = DeviceCatalogSourceAsset(
            url: sourceURL,
            scope: "MODEL",
            version: 1,
            attribution: "Garmin official product media",
            source: officialSource
        )
        let client = MockDeviceCatalogClient(
            catalog: DeviceCatalogResponse(
                catalogVersion: 2,
                legal: nil,
                devices: [
                    record(
                        id: "garmin-lily-2-active",
                        family: "Lily",
                        canonicalModel: "lily 2 active",
                        caseSizeMm: nil,
                        displayType: nil,
                        asset: DeviceCatalogAsset(status: "MISSING", url: nil, scope: nil),
                        sourceAsset: sourceAsset
                    )
                ]
            ),
            assetData: Data("garmin-source-image".utf8)
        )
        let cacheDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-garmin-source-(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: cacheDirectory) }

        let lily = DeviceIdentity(
            manufacturer: "Garmin",
            model: "Lily 2 Active",
            family: "Lily",
            variant: nil,
            usbVendorId: 0x091e,
            usbProductId: 0x0001,
            firmware: nil,
            storageCapacity: 0,
            freeSpace: 0
        )
        let result = await DeviceAssetResolver(
            client: client,
            cache: DeviceAssetCache(directory: cacheDirectory)
        ).resolve(identity: lily)

        expect(
            !result.isFallback
                && result.assetURL == sourceURL
                && result.assetSource?.type == "OFFICIAL_PRODUCT_MEDIA"
                && client.assetDownloadCount == 1,
            "approved catalog absence falls back to the official Garmin source image"
        )
        expect(
            DeviceAssetResolver.officialSourceURL(for: sourceURL) == sourceURL
                && DeviceAssetResolver.officialSourceURL(
                    for: URL(string: "https://example.com/watch.jpg")
                ) == nil,
            "official source image URLs are restricted to Garmin media hosting"
        )
    }

    private static func identity(variant: String?) -> DeviceIdentity {
        DeviceIdentity(
            manufacturer: "Garmin",
            model: "fenix 8 - 47mm",
            family: "fēnix",
            variant: variant,
            usbVendorId: 0x091e,
            usbProductId: 0x51b8,
            firmware: nil,
            storageCapacity: 0,
            freeSpace: 0
        )
    }

    private static func record(
        id: String,
        family: String = "fēnix",
        canonicalModel: String,
        caseSizeMm: Int?,
        displayType: String?,
        asset: DeviceCatalogAsset,
        sourceAsset: DeviceCatalogSourceAsset? = nil
    ) -> DeviceCatalogRecord {
        DeviceCatalogRecord(
            id: id,
            manufacturer: "Garmin",
            family: family,
            model: canonicalModel,
            canonicalModel: canonicalModel,
            variant: "",
            caseSizeMm: caseSizeMm,
            displayType: displayType,
            asset: asset,
            sourceAsset: sourceAsset
        )
    }

    private static let officialSource = DeviceAssetSource(
        type: "OFFICIAL_PRODUCT_MEDIA",
        brand: "Garmin",
        attributionRequired: true
    )

    private static func catalog(asset: DeviceCatalogAsset) -> DeviceCatalogResponse {
        DeviceCatalogResponse(
            catalogVersion: 2,
            legal: DeviceCatalogLegalMetadata(
                manufacturerNotice: true,
                text: "Garmin and fēnix are trademarks of Garmin Ltd. Terento is an independent open-source project and is not affiliated with Garmin."
            ),
            devices: [
                record(
                    id: "garmin-fenix-8-47-amoled",
                    canonicalModel: "fenix 8",
                    caseSizeMm: 47,
                    displayType: "AMOLED",
                    asset: asset
                )
            ]
        )
    }

    private static func expect(_ condition: Bool, _ message: String) {
        guard condition else { fatalError("FAIL: \(message)") }
        print("PASS: \(message)")
    }
}

private final class MockDeviceCatalogClient: DeviceCatalogAPIClient {
    var catalog: DeviceCatalogResponse
    var assetData: Data
    private(set) var assetDownloadCount = 0

    init(catalog: DeviceCatalogResponse, assetData: Data) {
        self.catalog = catalog
        self.assetData = assetData
    }

    func fetchCatalog() async throws -> DeviceCatalogResponse {
        catalog
    }

    func fetchAsset(from url: URL) async throws -> Data {
        assetDownloadCount += 1
        return assetData
    }
}
