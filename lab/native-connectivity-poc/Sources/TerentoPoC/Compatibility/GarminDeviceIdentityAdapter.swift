import Foundation

struct GarminDeviceIdentityAdapter: Sendable {
    func makeIdentity(from snapshot: DeviceSnapshot) -> DeviceIdentity {
        DeviceIdentity(
            manufacturer: snapshot.manufacturer,
            model: snapshot.model,
            family: family(for: snapshot.model),
            variant: variant(for: snapshot),
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

    private func variant(for snapshot: DeviceSnapshot) -> String? {
        let model = snapshot.model
        let normalized = GarminDeviceModelNormalizer.normalize(model)

        if normalized.contains("amoled") && normalized.contains("47mm") {
            return "AMOLED 47mm"
        }

        if normalized.contains("amoled") {
            return "AMOLED"
        }

        if normalized.contains("solar") {
            if let size = GarminDeviceModelNormalizer.caseSizeMm(from: model) {
                return "\(size) mm, Solar"
            }
            return "Solar"
        }

        // VID/PID 091e:51b8 is separately reviewed hardware evidence for the
        // exact 47 mm AMOLED catalog record. This is not inferred from the
        // product image or from size alone. An explicit display token above
        // always wins, so a future Solar identity cannot leak AMOLED.
        if snapshot.vendorID == 0x091e,
           snapshot.productID == 0x51b8,
           GarminDeviceModelNormalizer.canonicalModel(from: model) == "fēnix 8",
           GarminDeviceModelNormalizer.caseSizeMm(from: model) == 47 {
            return "47 mm, AMOLED"
        }

        if normalized.contains("47mm") {
            return "47mm"
        }

        if let match = normalized.range(of: #"\b\d{2}\s*mm\b"#, options: .regularExpression) {
            return normalized[match].replacingOccurrences(of: " ", with: "")
        }

        return nil
    }

    private func nonEmpty(_ value: String) -> String? {
        value.isEmpty ? nil : value
    }

}
