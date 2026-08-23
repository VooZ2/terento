import Foundation

enum ManagedFilenameError: Error, Equatable, Sendable {
    case emptyComponent
    case unsafeComponent
}

struct TerentoManagedFilenameGenerator: Sendable {
    func filename(providerId: String, regionId: String) throws -> String {
        let provider = try component(providerId)
        let region = try component(regionId)
        return "terento_\(provider)_\(region).img"
    }

    /// A versioned filename is used for safe updates because the old map must
    /// remain on the device until the new object has been written and fully
    /// verified. It is still deterministic and remains inside Terento's
    /// managed filename grammar.
    func versionedFilename(
        providerId: String,
        regionId: String,
        version: MapVersion
    ) throws -> String {
        let base = try filename(providerId: providerId, regionId: regionId)
        return base.replacingOccurrences(of: ".img", with: "_\(version.description).img")
    }

    func isVersioned(
        _ filename: String,
        providerId: String,
        regionId: String,
        version: MapVersion
    ) -> Bool {
        guard let expected = try? versionedFilename(
            providerId: providerId,
            regionId: regionId,
            version: version
        ) else {
            return false
        }

        return filename == expected && isValid(filename)
    }

    func isValid(_ filename: String) -> Bool {
        guard filename.utf8.count <= 255,
              !filename.isEmpty,
              !filename.contains("/"),
              !filename.contains("\\"),
              !filename.contains("\0"),
              !filename.contains(".."),
              let expression = try? NSRegularExpression(
                // Components are normalized to lowercase ASCII and may
                // contain internal separators after normalization.
                pattern: #"^terento_[a-z0-9]+(?:_[a-z0-9]+)*_[a-z0-9]+(?:_[a-z0-9]+)*(?:_[0-9]{4}-[0-9]{2})?\.img$"#
              ) else {
            return false
        }

        let range = NSRange(filename.startIndex..<filename.endIndex, in: filename)
        return expression.firstMatch(in: filename, range: range) != nil
    }

    private func component(_ value: String) throws -> String {
        let normalized = value
            .folding(
                options: [.caseInsensitive, .diacriticInsensitive],
                locale: Locale(identifier: "en_US_POSIX")
            )
            .lowercased()
            .replacingOccurrences(of: "[^a-z0-9]+", with: "_", options: .regularExpression)
            .trimmingCharacters(in: CharacterSet(charactersIn: "_"))

        guard !normalized.isEmpty else {
            throw ManagedFilenameError.emptyComponent
        }

        guard normalized.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "_") }) else {
            throw ManagedFilenameError.unsafeComponent
        }

        return normalized
    }
}
