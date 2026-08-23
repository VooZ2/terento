import Foundation

struct MapVersion: Codable, Comparable, Equatable, Hashable, Sendable, CustomStringConvertible {
    let year: Int
    let month: Int

    init?(year: Int, month: Int) {
        guard year >= 0, (1...12).contains(month) else {
            return nil
        }

        self.year = year
        self.month = month
    }

    init?(rawValue: String) {
        let value = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        let patterns = [
            #"^(\d{4})[-/.](0?[1-9]|1[0-2])$"#,
            #"^(\d{2})[-/.](0?[1-9]|1[0-2])$"#
        ]

        for (index, pattern) in patterns.enumerated() {
            guard let regex = try? NSRegularExpression(pattern: pattern),
                  let match = regex.firstMatch(
                      in: value,
                      range: NSRange(value.startIndex..<value.endIndex, in: value)
                  ),
                  let yearRange = Range(match.range(at: 1), in: value),
                  let monthRange = Range(match.range(at: 2), in: value),
                  let parsedYear = Int(value[yearRange]),
                  let parsedMonth = Int(value[monthRange]) else {
                continue
            }

            let year = index == 1 ? 2000 + parsedYear : parsedYear
            if let version = MapVersion(year: year, month: parsedMonth) {
                self = version
                return
            }
        }

        return nil
    }

    var description: String {
        String(format: "%04d-%02d", year, month)
    }

    static func < (lhs: MapVersion, rhs: MapVersion) -> Bool {
        if lhs.year != rhs.year {
            return lhs.year < rhs.year
        }
        return lhs.month < rhs.month
    }

}

protocol MapVersionParser: Sendable {
    func parse(_ value: String) -> MapVersion?
}

struct FreizeitkarteVersionParser: MapVersionParser, Sendable {
    func parse(_ value: String) -> MapVersion? {
        let pattern = #"(?i)\brelease\s+(\d{2})[./-](0?[1-9]|1[0-2])\b"#
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(
                  in: value,
                  range: NSRange(value.startIndex..<value.endIndex, in: value)
              ),
              let yearRange = Range(match.range(at: 1), in: value),
              let monthRange = Range(match.range(at: 2), in: value),
              let year = Int(value[yearRange]),
              let month = Int(value[monthRange]) else {
            return nil
        }

        return MapVersion(year: 2000 + year, month: month)
    }
}

struct MapVersionNormalizer: Sendable {
    private let freizeitkarteParser = FreizeitkarteVersionParser()

    func parse(rawValue: String?, provider: String?, fullText: String) -> MapVersion? {
        if let rawValue,
           MapIdentity.normalizeProvider(provider ?? "") == "freizeitkarte",
           let version = freizeitkarteParser.parse(rawValue) {
            return version
        }

        if let rawValue, let version = MapVersion(rawValue: rawValue) {
            return version
        }

        // A date-looking fragment elsewhere in an IMG header is not enough
        // evidence to identify the release. Returning nil prevents a build
        // date, serial number, or unrelated metadata from becoming a false
        // version comparison.
        _ = fullText
        return nil
    }
}
