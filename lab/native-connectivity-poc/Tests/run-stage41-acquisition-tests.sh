#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-stage41-acquisition-tests.XXXXXX")"
binary_path="$build_dir/stage41-acquisition-tests"

swiftc \
    -module-name TerentoStage41AcquisitionTests \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapCatalogLoader.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/InstalledMap.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapOwnership.swift" \
    "$project_root/Sources/TerentoPoC/Installation/ManagedFilename.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationSafetyModels.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapSourceValidator.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapPackageAcquisition.swift" \
    "$project_root/Tests/TerentoPoCTests/Stage41AcquisitionTests.swift" \
    -o "$binary_path"

"$binary_path"

bundled_catalog="$project_root/Sources/TerentoPoC/Resources/Maps/catalog.json"
if ! jq -e '
    .catalogVersion == 1
    and ([.providers[].maps[]] | length) == 63
    and ([.providers[].maps[].id] | unique | length) == 63
    and all(.providers[].maps[];
        (.installSizeBytes | type == "number")
        and .installSizeBytes > 0
        and (.sourceURL | startswith("https://download.freizeitkarte-osm.de/"))
    )
' "$bundled_catalog" >/dev/null; then
    print -u2 "FAIL: bundled catalog is not the complete validated API-schema snapshot"
    exit 1
fi

print "PASS: bundled fallback contains all 63 current packages with final IMG sizes"

if grep -Eq 'LibMTPBridge|MTPTransport|SendObject|DeleteObject|MoveObject|RenameObject|Backup' \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapPackageAcquisition.swift"; then
    print -u2 "FAIL: acquisition layer contains a device transport or write dependency"
    exit 1
fi

print "PASS: acquisition layer has no Garmin transport or write dependency"
