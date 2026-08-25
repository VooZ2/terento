import Foundation

private func require(_ condition: @autoclosure () -> Bool, _ message: String) {
    guard condition() else {
        print("FAIL: \(message)")
        exit(1)
    }
}

@main
struct CompatibilityStatusClientTests {
    static func main() async {
        let cacheURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("terento-compatibility-status-\(UUID().uuidString).json")
        let cache = CompatibilityStatusCache(fileURL: cacheURL)

        let initialResponse = response([
            record(identity: "fēnix 8 · 47 mm", size: 47, status: "SUPPORTED"),
            record(identity: "fēnix 8 · 51 mm", size: 51, status: "TESTED"),
        ])
        let client = CompatibilityStatusClient(
            cache: cache,
            dataLoader: { _ in (initialResponse, httpResponse()) }
        )

        let fenix47 = identity(size: 47)
        let fenix51 = identity(size: 51)
        let supported = await client.resolve(identity: fenix47)
        let secondVariant = await client.resolve(identity: fenix51)
        require(supported.status == .supported, "47 mm uses the canonical SUPPORTED result")
        require(supported.source == .remote, "47 mm status comes from the public API")
        require(supported.record?.canonicalDeviceId == "garmin-fenix-8-47-amoled", "canonical device ID survives API decoding")
        require(supported.record?.caseSizeMm == 47, "case size survives API decoding")
        require(supported.record?.displayType == "AMOLED", "display type survives API decoding")
        require(supported.record?.successfulInstallations == 3, "successful install count survives API decoding")
        require(supported.record?.lastEvidence == "2026-08-25T11:47:43Z", "last evidence survives API decoding")
        require(supported.record?.mapCapable == true, "map capability survives API decoding")
        require(secondVariant.status == .tested, "51 mm uses its independent TESTED result")
        require(secondVariant.source == .remote, "51 mm status comes from the public API")

        let no51Client = CompatibilityStatusClient(
            cache: CompatibilityStatusCache(
                fileURL: FileManager.default.temporaryDirectory
                    .appendingPathComponent("terento-compatibility-status-no-51-\(UUID().uuidString).json")
            ),
            dataLoader: { _ in
                (response([record(identity: "fēnix 8 · 47 mm", size: 47, status: "SUPPORTED")]), httpResponse())
            }
        )
        let noInheritedStatus = await no51Client.resolve(identity: fenix51)
        require(noInheritedStatus.status == nil, "51 mm does not inherit 47 mm status")
        require(noInheritedStatus.source == .unavailable, "missing exact variant is neutral")

        let ambiguousDisplayClient = CompatibilityStatusClient(
            cache: CompatibilityStatusCache(
                fileURL: FileManager.default.temporaryDirectory
                    .appendingPathComponent("terento-compatibility-status-ambiguous-\(UUID().uuidString).json")
            ),
            dataLoader: { _ in
                (response([
                    record(identity: "fēnix 8 · 47 mm, AMOLED", size: 47, status: "SUPPORTED", variant: "47 mm, AMOLED"),
                    record(identity: "fēnix 8 · 47 mm, Solar", size: 47, status: "TESTED", variant: "47 mm, Solar"),
                ]), httpResponse())
            }
        )
        let ambiguousDisplay = await ambiguousDisplayClient.resolve(identity: fenix47)
        require(ambiguousDisplay.status == .supported, "reviewed VID/PID selects only its exact AMOLED catalog identity")

        let unreviewedSizeOnly = identity(size: 47, productID: 0x9999)
        let noDisplayGuess = await ambiguousDisplayClient.resolve(identity: unreviewedSizeOnly)
        require(noDisplayGuess.status == nil, "size-only identity does not choose AMOLED or Solar")

        let solar = identity(size: 47, variant: "47 mm, Solar", productID: 0x9999)
        let solarResult = await ambiguousDisplayClient.resolve(identity: solar)
        require(solarResult.status == .tested, "explicit Solar identity remains separate from AMOLED")

        let statusChangedClient = CompatibilityStatusClient(
            cache: cache,
            dataLoader: { _ in
                (response([record(identity: "fēnix 8 · 47 mm", size: 47, status: "VERIFIED")]), httpResponse())
            }
        )
        let updated = await statusChangedClient.resolve(identity: fenix47)
        require(updated.status == .verified, "a canonical status update replaces the cached status")
        require(updated.source == .remote, "updated status is not supplied by hardcoded UI logic")

        let offlineClient = CompatibilityStatusClient(
            cache: cache,
            dataLoader: { _ in throw URLError(.notConnectedToInternet) }
        )
        let cached = await offlineClient.resolve(identity: fenix47)
        require(cached.status == .verified, "offline mode uses the recent canonical cache")
        require(cached.source == .cache, "offline mode identifies cached provenance")

        let noCacheOfflineClient = CompatibilityStatusClient(
            cache: CompatibilityStatusCache(
                fileURL: FileManager.default.temporaryDirectory
                    .appendingPathComponent("terento-compatibility-status-empty-\(UUID().uuidString).json")
            ),
            dataLoader: { _ in throw URLError(.notConnectedToInternet) }
        )
        let unavailable = await noCacheOfflineClient.resolve(identity: fenix47)
        require(unavailable.status == nil, "offline mode without cache is neutral")
        require(unavailable.source == .unavailable, "offline mode does not fabricate a downgrade")

        let adapter = GarminDeviceIdentityAdapter()
        let reviewedIdentity = adapter.makeIdentity(from: snapshot(model: "fenix 8 - 47mm", productID: 0x51b8))
        require(reviewedIdentity.variant == "47 mm, AMOLED", "reviewed VID/PID enriches the exact AMOLED variant")
        require(
            ConnectedDeviceSubtitleFormatter.format(
                identity: reviewedIdentity,
                fallbackModel: "fenix 8 - 47mm",
                manufacturer: "Garmin"
            ) == "47 mm · AMOLED · Firmware 22.44",
            "connected subtitle renders exact case, variant, and firmware"
        )
        let unknownVariant = identity(size: 47, productID: 0x9999)
        require(unknownVariant.displayType == nil, "unknown variant remains nil")
        require(
            ConnectedDeviceSubtitleFormatter.format(
                identity: unknownVariant,
                fallbackModel: "fenix 8 - 47mm",
                manufacturer: "Garmin"
            ) == "47 mm · Firmware 22.44",
            "unknown variant subtitle does not invent AMOLED or Solar"
        )

        let reviewed51Identity = adapter.makeIdentity(from: snapshot(model: "fenix 8 - 51mm", productID: 0x51b8))
        require(reviewed51Identity.variant == "51 mm, AMOLED", "reviewed 51 mm MTP identity resolves its exact AMOLED variant")
        require(
            reviewed51Identity.reviewedCanonicalDeviceID == "garmin-fenix-8-51-amoled",
            "reviewed 51 mm identity binds to the live API canonical device ID"
        )

        try? FileManager.default.removeItem(at: cacheURL)
        print("PASS: canonical compatibility status client, exact variants, cache, and offline behavior")
    }

    private static func identity(
        size: Int,
        variant: String? = nil,
        productID: UInt16 = 0x51b8
    ) -> DeviceIdentity {
        DeviceIdentity(
            manufacturer: "Garmin",
            model: "fenix 8 - \(size)mm",
            family: "fēnix",
            variant: variant,
            usbVendorId: 0x091e,
            usbProductId: productID,
            firmware: "2244",
            storageCapacity: 1_000,
            freeSpace: 500
        )
    }

    private static func record(
        identity: String,
        size: Int,
        status: String,
        variant: String? = nil
    ) -> [String: Any] {
        var result: [String: Any] = [
            "model": "fēnix 8",
            "canonicalModel": "fēnix 8",
            "compatibilityIdentity": identity,
            "variant": variant ?? "\(size) mm",
            "caseSizeMm": size,
            "canonicalDeviceId": size == 47 && variant?.contains("Solar") != true
                ? "garmin-fenix-8-47-amoled"
                : (variant?.contains("Solar") == true ? "garmin-fenix-8-47-solar" : "garmin-fenix-8-51-amoled"),
            "attemptedInstallations": size == 47 ? 3 : 1,
            "successfulInstallations": size == 47 ? 3 : 1,
            "failedInstallations": 0,
            "lastSuccessfulInstallation": "2026-08-25T11:47:43Z",
            "lastEvidence": "2026-08-25T11:47:43Z",
            "mapCapable": true,
            "evidenceStatus": status,
        ]
        if variant?.contains("Solar") == true {
            result["displayType"] = "Solar"
        } else {
            result["displayType"] = "AMOLED"
        }
        return result
    }

    private static func snapshot(model: String, productID: UInt16) -> DeviceSnapshot {
        DeviceSnapshot(
            manufacturer: "Garmin",
            model: model,
            deviceVersion: "2244",
            vendorID: 0x091e,
            productID: productID,
            storages: []
        )
    }

    private static func response(_ records: [[String: Any]]) -> Data {
        try! JSONSerialization.data(withJSONObject: [
            "schemaVersion": 2,
            "generatedAt": "2026-08-25T12:00:00Z",
            "models": records,
        ])
    }

    private static func httpResponse() -> URLResponse {
        HTTPURLResponse(
            url: URL(string: "https://api.terento.app/compatibility/public/top-models.json")!,
            statusCode: 200,
            httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
    }
}
