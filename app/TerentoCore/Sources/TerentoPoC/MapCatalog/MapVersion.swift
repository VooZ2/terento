import Foundation

struct MapVersion: Codable, Comparable, Equatable, Hashable, Sendable, CustomStringConvertible {
    let year: Int
    let month: Int
    /// Absent for legacy/monthly providers; MapRando publishes daily releases.
    let day: Int?

    init?(year: Int, month: Int, day: Int? = nil) {
        guard year >= 0, (1...12).contains(month) else {
            return nil
        }

        if let day {
            let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
            let lengths = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
            guard (1...lengths[month - 1]).contains(day) else { return nil }
        }
        self.day = day
        self.year = year
        self.month = month
    }

    private enum CodingKeys: String, CodingKey { case year, month, day }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        let year = try values.decode(Int.self, forKey: .year)
        let month = try values.decode(Int.self, forKey: .month)
        let day = try values.decodeIfPresent(Int.self, forKey: .day)
        guard let version = MapVersion(year: year, month: month, day: day) else {
            throw DecodingError.dataCorruptedError(forKey: .day, in: values,
                debugDescription: "Invalid map release date")
        }
        self = version
    }

    init?(rawValue: String) {
        let value = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        if let daily = MapRandoVersionParser().parseISO(value) {
            self = daily
            return
        }
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
        if let day { return String(format: "%04d-%02d-%02d", year, month, day) }
        return String(format: "%04d-%02d", year, month)
    }

    static func < (lhs: MapVersion, rhs: MapVersion) -> Bool {
        if lhs.year != rhs.year {
            return lhs.year < rhs.year
        }
        if lhs.month != rhs.month { return lhs.month < rhs.month }
        return (lhs.day ?? 0) < (rhs.day ?? 0)
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

struct OpenTopoMapVersionParser: MapVersionParser, Sendable {
    func parse(_ value: String) -> MapVersion? {
        let fullPattern = #"\b(20\d{2})[-/.](0?[1-9]|1[0-2])(?:[-/.](?:0?[1-9]|[12]\d|3[01]))?\b"#
        if let version = parse(
            value,
            pattern: fullPattern,
            yearOffset: 0,
            yearCapture: 1,
            monthCapture: 2
        ) {
            return version
        }

        // Some OpenTopoMap Garmin images with a full 20-byte description
        // expose the generated date as `026-05-24` instead of
        // `2026-05-24`. The leading `2` is lost at the fixed-header field
        // boundary; the remaining `0YY` is still an unambiguous 20YY year.
        let compactPattern = #"\b0(\d{2})[-/.](0?[1-9]|1[0-2])(?:[-/.](?:0?[1-9]|[12]\d|3[01]))?\b"#
        return parse(
            value,
            pattern: compactPattern,
            yearOffset: 2000,
            yearCapture: 1,
            monthCapture: 2
        )
    }

    func generatedDateLabel(from value: String) -> String? {
        let fullPattern = #"\b(20\d{2})[-/.](0?[1-9]|1[0-2])[-/.](0?[1-9]|[12]\d|3[01])\b"#
        if let label = dateLabel(
            in: value,
            pattern: fullPattern,
            yearOffset: 0,
            yearCapture: 1,
            monthCapture: 2,
            dayCapture: 3
        ) {
            return label
        }

        let compactPattern = #"\b0(\d{2})[-/.](0?[1-9]|1[0-2])[-/.](0?[1-9]|[12]\d|3[01])\b"#
        return dateLabel(
            in: value,
            pattern: compactPattern,
            yearOffset: 2000,
            yearCapture: 1,
            monthCapture: 2,
            dayCapture: 3
        )
    }

    private func parse(
        _ value: String,
        pattern: String,
        yearOffset: Int,
        yearCapture: Int,
        monthCapture: Int
    ) -> MapVersion? {
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(
                  in: value,
                  range: NSRange(value.startIndex..<value.endIndex, in: value)
              ),
              let yearRange = Range(match.range(at: yearCapture), in: value),
              let monthRange = Range(match.range(at: monthCapture), in: value),
              let parsedYear = Int(value[yearRange]),
              let month = Int(value[monthRange]) else {
            return nil
        }

        return MapVersion(year: parsedYear + yearOffset, month: month)
    }

    private func dateLabel(
        in value: String,
        pattern: String,
        yearOffset: Int,
        yearCapture: Int,
        monthCapture: Int,
        dayCapture: Int
    ) -> String? {
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(
                  in: value,
                  range: NSRange(value.startIndex..<value.endIndex, in: value)
              ),
              let yearRange = Range(match.range(at: yearCapture), in: value),
              let monthRange = Range(match.range(at: monthCapture), in: value),
              let dayRange = Range(match.range(at: dayCapture), in: value),
              let parsedYear = Int(value[yearRange]),
              let month = Int(value[monthRange]),
              let day = Int(value[dayRange]),
              MapVersion(year: parsedYear + yearOffset, month: month) != nil else {
            return nil
        }

        return String(format: "Generated %04d-%02d-%02d", parsedYear + yearOffset, month, day)
    }
}

struct MapVersionNormalizer: Sendable {
    private let freizeitkarteParser = FreizeitkarteVersionParser()
    private let openTopoMapParser = OpenTopoMapVersionParser()

    func parse(rawValue: String?, provider: String?, fullText: String) -> MapVersion? {
        if let rawValue,
           MapIdentity.normalizeProvider(provider ?? "") == "freizeitkarte",
           let version = freizeitkarteParser.parse(rawValue) {
            return version
        }

        if let rawValue,
           MapIdentity.normalizeProvider(provider ?? "") == "opentopomap",
           let version = openTopoMapParser.parse(rawValue) {
            return version
        }

        if MapIdentity.normalizeProvider(provider ?? "") == "maprando" {
            return rawValue.flatMap { MapRandoVersionParser().parse($0) }
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

/// Provider releases are read from the complete fixed IMG description, never
/// from a renamed device filename or an unrelated embedded date fragment.
struct MapRandoVersionParser: Sendable {
    func parseISO(_ value: String) -> MapVersion? {
        parse(value, pattern: #"^(20\d{2})-(\d{2})-(\d{2})$"#, reversed: false)
    }

    func parse(_ value: String) -> MapVersion? {
        parse(value, pattern: #"^(\d{2})\.(\d{2})\.(20\d{2})$"#, reversed: true)
            ?? parseISO(value)
    }

    private func parse(_ value: String, pattern: String, reversed: Bool) -> MapVersion? {
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: value, range: NSRange(value.startIndex..., in: value)) else { return nil }
        let numbers = (1...3).compactMap { index -> Int? in
            guard let range = Range(match.range(at: index), in: value) else { return nil }
            return Int(value[range])
        }
        guard numbers.count == 3 else { return nil }
        return MapVersion(year: numbers[reversed ? 2 : 0], month: numbers[1], day: numbers[reversed ? 0 : 2])
    }
}
