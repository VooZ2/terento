import Foundation
#if canImport(FoundationXML)
import FoundationXML
#endif

struct GarminDeviceDocumentIdentity: Equatable, Sendable {
    let unitID: String
    let description: String?
}

struct GarminDeviceModelMetadata: Equatable, Sendable {
    let description: String?
    let partNumber: String?
}

enum GarminDeviceDocumentParser {
    static func modelMetadata(_ data: Data) -> GarminDeviceModelMetadata? {
        guard !data.isEmpty, data.count <= 2 * 1024 * 1024,
              let source = String(data: data, encoding: .utf8),
              source.range(of: "<!DOCTYPE", options: .caseInsensitive) == nil,
              source.range(of: "<!ENTITY", options: .caseInsensitive) == nil else { return nil }
        let delegate = GarminDeviceMetadataParserDelegate()
        let parser = XMLParser(data: data)
        parser.delegate = delegate
        parser.shouldProcessNamespaces = true
        parser.shouldResolveExternalEntities = false
        guard parser.parse(), ["Device", "GarminDevice"].contains(delegate.rootElement ?? ""),
              delegate.rootNamespace == nil || delegate.rootNamespace == ""
                || delegate.rootNamespace == "http://www.garmin.com/xmlschemas/GarminDevice/v2" else { return nil }
        let description = delegate.descriptions.count == 1
            ? sanitizedDescription(delegate.descriptions[0]) : nil
        let part = delegate.partNumbers.count == 1
            ? delegate.partNumbers[0].trimmingCharacters(in: .whitespacesAndNewlines) : ""
        let validPart = (1...64).contains(part.count) && part.allSatisfy {
            $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "-")
        }
        return GarminDeviceModelMetadata(description: description, partNumber: validPart ? part : nil)
    }

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

/// Only direct, scalar Model children are diagnostic metadata. A nested
/// element cannot turn a malformed field into an apparently valid suffix.
private final class GarminDeviceMetadataParserDelegate: NSObject, XMLParserDelegate {
    var rootElement: String?
    var rootNamespace: String?
    var descriptions: [String] = []
    var partNumbers: [String] = []
    private var elements: [String] = []
    private var text = ""
    private var nested = false

    func parser(_ parser: XMLParser, didStartElement elementName: String,
                namespaceURI: String?, qualifiedName qName: String?,
                attributes attributeDict: [String: String] = [:]) {
        if elements.isEmpty {
            rootElement = elementName
            rootNamespace = namespaceURI
        }
        elements.append((namespaceURI ?? "") == (rootNamespace ?? "") ? elementName : "")
        if elements.count == 3 {
            text = ""
            nested = false
        } else if elements.count > 3 { nested = true }
    }

    func parser(_ parser: XMLParser, foundCharacters string: String) {
        if elements.count == 3 { text += string }
    }

    func parser(_ parser: XMLParser, foundCDATA CDATABlock: Data) {
        if let value = String(data: CDATABlock, encoding: .utf8) {
            self.parser(parser, foundCharacters: value)
        } else { nested = true }
    }

    func parser(_ parser: XMLParser, didEndElement elementName: String,
                namespaceURI: String?, qualifiedName qName: String?) {
        if elements == [rootElement ?? "", "Model", "Description"] { descriptions.append(nested ? "" : text) }
        if elements == [rootElement ?? "", "Model", "PartNumber"] { partNumbers.append(nested ? "" : text) }
        elements.removeLast()
    }
}

struct GarminDeviceIdentityAdapter: Sendable {
    func makeIdentity(from snapshot: DeviceSnapshot) -> DeviceIdentity {
        let document = snapshot.garminDeviceXML.flatMap(GarminDeviceDocumentParser.parse)
        let metadata = snapshot.garminDeviceXML.flatMap(GarminDeviceDocumentParser.modelMetadata)
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
            garminDeviceXMLStatus: snapshot.garminDeviceXMLStatus,
            garminModelDescription: metadata?.description,
            garminModelPartNumber: metadata?.partNumber
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
        var parts: [String] = []
        if let size = GarminDeviceModelNormalizer.caseSizeMm(from: model) { parts.append("\(size) mm") }
        if let screen = GarminDeviceModelNormalizer.screenTechnology(from: model) { parts.append(screen) }
        if GarminDeviceModelNormalizer.hasExplicitFeature("solar", in: model) { parts.append("Solar") }
        if GarminDeviceModelNormalizer.hasExplicitFeature("inreach", in: model) { parts.append("inReach") }
        return parts.isEmpty ? nil : parts.joined(separator: ", ")
    }

    private func nonEmpty(_ value: String) -> String? {
        value.isEmpty ? nil : value
    }

}
