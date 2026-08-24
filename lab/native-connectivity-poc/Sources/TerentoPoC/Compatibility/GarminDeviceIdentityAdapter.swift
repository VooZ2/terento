import Foundation

struct GarminDeviceIdentityAdapter: Sendable {
    func makeIdentity(from snapshot: DeviceSnapshot) -> DeviceIdentity {
        DeviceIdentity(
            manufacturer: snapshot.manufacturer,
            model: snapshot.model,
            family: family(for: snapshot.model),
            variant: variant(for: snapshot.model),
            usbVendorId: snapshot.vendorID,
            usbProductId: snapshot.productID,
            firmware: nonEmpty(snapshot.deviceVersion),
            storageCapacity: snapshot.totalCapacity,
            freeSpace: snapshot.freeSpace
        )
    }

    private func family(for model: String) -> String? {
        let normalized = GarminDeviceModelNormalizer.normalize(model)

        if normalized.contains("fenix") {
            return "fēnix"
        }

        if normalized.contains("epix") {
            return "epix"
        }

        if normalized.contains("forerunner") {
            return "Forerunner"
        }

        if normalized.contains("enduro") {
            return "Enduro"
        }

        if normalized.contains("tactix") {
            return "tactix"
        }

        if normalized.contains("quatix") {
            return "quatix"
        }

        if normalized.contains("d2 mach") {
            return "D2 Mach"
        }

        if normalized.contains("descent") {
            return "Descent"
        }

        if normalized.contains("lily") {
            return "Lily"
        }

        if normalized.contains("venu") {
            return "Venu"
        }

        if normalized.contains("marq") {
            return "MARQ"
        }

        if normalized.contains("instinct") {
            return "Instinct"
        }

        if normalized.contains("approach") {
            return "Approach"
        }

        if normalized.contains("vivoactive") {
            return "vívoactive"
        }

        if normalized.contains("vivomove") {
            return "vívomove"
        }

        return nil
    }

    private func variant(for model: String) -> String? {
        let normalized = GarminDeviceModelNormalizer.normalize(model)

        if normalized.contains("amoled") && normalized.contains("47mm") {
            return "AMOLED 47mm"
        }

        if normalized.contains("amoled") {
            return "AMOLED"
        }

        if normalized.contains("47mm") {
            return "47mm"
        }

        if let match = normalized.range(of: #"\b\d{2}\s*mm\b"#, options: .regularExpression) {
            return normalized[match].replacingOccurrences(of: " ", with: "")
        }

        if normalized.contains("solar") {
            return "Solar"
        }

        return nil
    }

    private func nonEmpty(_ value: String) -> String? {
        value.isEmpty ? nil : value
    }

}
