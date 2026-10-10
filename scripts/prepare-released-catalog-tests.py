#!/usr/bin/env python3
"""Adapt historical test fixtures without modifying pinned runtime or live catalogs."""
from pathlib import Path
import sys

TEST_PATH = Path("app/TerentoCore/Tests/TerentoPoCTests/Stage1ProviderNeutralTests.swift")
REPLACEMENTS = (
    ("makeFreizeitkarteIMG(token: package.providerRegionId)",
     "makeFreizeitkarteIMG(token: package.providerRegionId, version: package.version)", 1),
    ("makeFreizeitkarteIMG(token: String) -> [UInt8]",
     "makeFreizeitkarteIMG(token: String, version: MapVersion) -> [UInt8]", 1),
    ('Release 26.05', 'Release \\(String(format: "%02d.%02d", version.year % 100, version.month))', 2),
)


MATRICES = (
    ("testEveryBundledFreizeitkarteRowMatchesProviderIdentity", "freizeitkarte", 63),
    ("testEveryBundledOpenTopoMapRowAcceptsBothDateHeaderForms", "opentopomap", 177),
)


def prepare_source(source: str) -> str:
    # New clients preserve unavailable rows; their tests must stay unchanged.
    modern = "private static func testBlockedCatalogStaysVisible()" in source
    date_fixed = all(source.count(old) == 0 and source.count(new) >= count
                     for old, new, count in REPLACEMENTS)
    if not date_fixed:
        if not all(source.count(old) == count and source.count(new) == 0
                   for old, new, count in REPLACEMENTS):
            raise ValueError("Unrecognized released-client date fixture; review the pinned test source")
        for old, new, _ in REPLACEMENTS:
            source = source.replace(old, new)
    if modern:
        return source
    for name, provider_id, count in MATRICES:
        signature = f"    private static func {name}() {{"
        if source.count(signature) != 1:
            raise ValueError("Unrecognized released-client identity matrix")
        start = source.index(signature)
        end = source.index("\n    private static func ", start + len(signature))
        block = source[start:end]
        marker = f"// Released {provider_id} matrix: bundled coverage plus unchanged live policy."
        if marker in block:
            continue
        read = "            let data = try Data(contentsOf: identityContractCatalogURL)"
        guard = f"            let allRowsPass = packages.count == {count} && packages.allSatisfy {{ package in"
        if block.count(read) != 1 or block.count(guard) != 1 or block.count("        } catch {") != 1:
            raise ValueError("Unrecognized released-client identity matrix layout")
        block = block.replace(read, f'''            {marker}
            let bundledCatalogURL = packageRoot.appendingPathComponent(
                "Sources/TerentoPoC/Resources/Maps/catalog.json"
            )
            let matrixURLs = identityContractCatalogURL == bundledCatalogURL
                ? [bundledCatalogURL] : [bundledCatalogURL, identityContractCatalogURL]
            for catalogURL in matrixURLs {{
            let data = try Data(contentsOf: catalogURL)''')
        block = block.replace(guard, f'''            let provider = catalog.providers.first {{ $0.id == "{provider_id}" }}
            let expectedRowCount = catalogURL == bundledCatalogURL || provider?.allowsNewInstallCatalog == true ? {count} : 0
            let catalogKind = catalogURL == bundledCatalogURL ? "bundled" : "live"
            let installationEligibility = provider.map {{ $0.allowsNewInstallCatalog ? "allowed" : "blocked" }} ?? "missing-provider"
            print("Released {provider_id} matrix [catalog=\\(catalogKind), installation=\\(installationEligibility), actualRows=\\(packages.count), expectedRows=\\(expectedRowCount)]")
            // Live catalogs list only installable maps (owner rule 2026-10-10), so their size may shrink.
            let rowCountMatches = catalogURL == bundledCatalogURL || expectedRowCount == 0
                ? packages.count == expectedRowCount : !packages.isEmpty
            let allRowsPass = provider != nil && rowCountMatches && packages.allSatisfy {{ package in''')
        block = block.replace("        } catch {", "            }\n        } catch {")
        if provider_id == "opentopomap":
            old = '''            let requiresBundledContourFixture = ProcessInfo.processInfo.environment[
                "TERENTO_CATALOG_CONTRACT_PATH"
            ] == nil'''
            if block.count(old) != 1:
                raise ValueError("Unrecognized released-client contour fixture")
            block = block.replace(old, "            let requiresBundledContourFixture = catalogURL == bundledCatalogURL")
        source = source[:start] + block + source[end:]
    return source


def prepare(root: Path) -> None:
    path = root / TEST_PATH
    source = path.read_text()
    patched = prepare_source(source)
    if patched != source:
        path.write_text(patched)


if __name__ == "__main__":
    prepare(Path(sys.argv[1]))
