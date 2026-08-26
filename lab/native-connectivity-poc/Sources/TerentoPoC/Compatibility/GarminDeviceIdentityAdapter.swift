import Foundation
#if canImport(FoundationXML)
import FoundationXML
#endif

struct GarminDeviceDocumentIdentity: Equatable, Sendable {
    let unitID: String
    let description: String?
}

enum GarminDeviceDocumentParser {
    static func parse(_ data: Data) -> GarminDeviceDocumentIdentity? {
        guard !data.isEmpty, data.count <= 2 * 1024 * 1024 else { return nil }
        if let source = String(data: data, encoding: .utf8),
           source.range(of: "<!DOCTYPE", options: .caseInsensitive) != nil
            || source.range(of: "<!ENTITY", options: .caseInsensitive) != nil {
            return nil
        }
        let delegate = GarminDeviceDocumentParserDelegate()
        let parser = XMLParser(data: data)
        parser.delegate = delegate
        parser.shouldResolveExternalEntities = false
        guard parser.parse(),
              delegate.rootElement == "GarminDevice",
              delegate.ids.count == 1,
              let unitID = sanitizedUnitID(delegate.ids[0]) else {
            return nil
        }
        guard delegate.descriptions.count <= 1 else { return nil }
        let description: String?
        if let rawDescription = delegate.descriptions.first {
            guard let sanitized = sanitizedDescription(rawDescription) else { return nil }
            description = sanitized
        } else {
            description = nil
        }
        return GarminDeviceDocumentIdentity(unitID: unitID, description: description)
    }

    private static func sanitizedUnitID(_ value: String) -> String? {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard (4...64).contains(trimmed.count),
              trimmed.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "-") }) else {
            return nil
        }
        return trimmed
    }

    private static func sanitizedDescription(_ value: String) -> String? {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed.count <= 160,
              !trimmed.contains(where: { $0.isNewline || $0.asciiValue.map { $0 < 32 } == true }) else {
            return nil
        }
        return trimmed
    }
}

private final class GarminDeviceDocumentParserDelegate: NSObject, XMLParserDelegate {
    var rootElement: String?
    var ids: [String] = []
    var descriptions: [String] = []
    private var elements: [String] = []
    private var capturesText = false
    private var text = ""

    func parser(_ parser: XMLParser, didStartElement elementName: String,
                namespaceURI: String?, qualifiedName qName: String?,
                attributes attributeDict: [String: String] = [:]) {
        if elements.isEmpty { rootElement = elementName }
        elements.append(elementName)
        capturesText = elements.suffix(2) == ["GarminDevice", "Id"]
            || elements.suffix(2) == ["Model", "Description"]
        if capturesText { text = "" }
    }

    func parser(_ parser: XMLParser, foundCharacters string: String) {
        if capturesText { text += string }
    }

    func parser(_ parser: XMLParser, didEndElement elementName: String,
                namespaceURI: String?, qualifiedName qName: String?) {
        if elements.suffix(2) == ["GarminDevice", "Id"] { ids.append(text) }
        if elements.suffix(2) == ["Model", "Description"] { descriptions.append(text) }
        if !elements.isEmpty { elements.removeLast() }
        capturesText = elements.suffix(2) == ["GarminDevice", "Id"]
            || elements.suffix(2) == ["Model", "Description"]
        text = ""
    }
}

struct GarminDeviceIdentityAdapter: Sendable {
    func makeIdentity(from snapshot: DeviceSnapshot) -> DeviceIdentity {
        let document = snapshot.garminDeviceXML.flatMap(GarminDeviceDocumentParser.parse)
        let serial = snapshot.serialNumber.flatMap(nonEmpty)
        let localIdentifier = serial ?? document?.unitID
        let resolution: DeviceIdentity.LocalIdentityResolution = serial != nil
            ? .mtpSerial
            : (document != nil ? .garminUnitID : .unavailable)
        return DeviceIdentity(
            manufacturer: snapshot.manufacturer,
            model: snapshot.model,
            family: family(for: snapshot.model),
            variant: variant(for: snapshot, description: document?.description),
            usbVendorId: snapshot.vendorID,
            usbProductId: snapshot.productID,
            firmware: nonEmpty(snapshot.deviceVersion),
            storageCapacity: snapshot.totalCapacity,
            freeSpace: snapshot.freeSpace,
            localHardwareIdentifier: localIdentifier,
            localIdentityResolution: resolution,
            deviceDescription: document?.description,
            garminDeviceXMLStatus: snapshot.garminDeviceXMLStatus
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

    private func variant(for snapshot: DeviceSnapshot, description: String?) -> String? {
        let model = [description, snapshot.model].compactMap { $0 }.joined(separator: " ")
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
