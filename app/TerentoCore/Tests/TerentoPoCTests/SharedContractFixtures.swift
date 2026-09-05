import Foundation

/// Resolve from the source, independent of the runner's current directory.
/// Require both the fixture directory and the native package marker.
enum SharedContractFixtures {
    static func repositoryRoot(source: StaticString = #filePath) throws -> URL {
        var candidate = URL(fileURLWithPath: String(describing: source))
            .standardizedFileURL.resolvingSymlinksInPath().deletingLastPathComponent()
        while candidate.path != "/" {
            let package = candidate.appendingPathComponent("app/TerentoCore/Package.swift")
            let fixtures = candidate.appendingPathComponent("contracts/fixtures")
            if FileManager.default.fileExists(atPath: package.path),
               FileManager.default.fileExists(atPath: fixtures.path) {
                return candidate
            }
            candidate.deleteLastPathComponent()
        }
        throw CocoaError(.fileNoSuchFile)
    }

    static func data(_ name: String) throws -> Data {
        guard !name.contains("/"), !name.contains("..") else {
            throw CocoaError(.fileReadInvalidFileName)
        }
        return try Data(contentsOf: repositoryRoot()
            .appendingPathComponent("contracts/fixtures/\(name).json"))
    }
}
