#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-download-resume-tests.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
binary_path="$build_dir/download-resume-tests"

swiftc \
    -module-name TerentoDownloadResumeTests \
    -parse-as-library \
    "$project_root/Sources/TerentoPoC/Models/MTPModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapArtifactPlanning.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapCatalogLoader.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/InstalledMap.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapOwnership.swift" \
    "$project_root/Sources/TerentoPoC/Installation/ManagedFilename.swift" \
    "$project_root/Sources/TerentoPoC/Installation/InstallationSafetyModels.swift" \
    "$project_root/Sources/TerentoPoC/Installation/MapSourceValidator.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/BBBikeArchiveSafety.swift" \
    "$project_root/Sources/TerentoPoC/MapCatalog/MapPackageAcquisition.swift" \
    "$project_root/Tests/TerentoPoCTests/DownloadResumeTests.swift" \
    -o "$binary_path"

(
    cd "$project_root"
    "$binary_path"
)

acquisition="$project_root/Sources/TerentoPoC/MapCatalog/MapPackageAcquisition.swift"
map_engine="$project_root/Sources/TerentoPoC/MapCatalog/MapEngine.swift"
require() {
    local file="$1" text="$2" message="$3"
    if ! grep -Fq -- "$text" "$file"; then
        print -u2 "FAIL: $message"
        exit 1
    fi
}
require "$acquisition" 'let key = sourceProof == nil ? resumeKey : nil' 'BBBike source-proof downloads must not be resumed'
require "$map_engine" 'nonisolated static let retainedArtifactLifetime: TimeInterval = 30 * 60' 'retained-artifact lifetime changed without the partial-download lifetime'
require "$map_engine" 'MapDownloadResumeStore.shared.purgeAll()' 'quitting does not remove partial downloads'
# Final validation stays on the completed file: the acquirer path is unchanged.
require "$acquisition" 'validatedSource = try MapSourceValidator().validate(' 'final source validation is missing'
if [[ $(grep -c 'downloadClient.download' "$acquisition") -ne 1 ]]; then
    print -u2 "FAIL: resume must stay inside the single downloader boundary"
    exit 1
fi
print "PASS: resumable downloads stay inside the reviewed downloader and keep final validation"
