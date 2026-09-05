#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-map-statistics-tests.XXXXXX")"
map_engine="$project_root/Sources/TerentoPoC/MapCatalog/MapEngine.swift"

grep -Fq 'guard package.sourceKind == .provider else { return }' "$map_engine" || {
  print -u2 'FAIL: custom IMG installations must stay out of map-statistics uploads'
  exit 1
}

swiftc -parse-as-library -module-name TerentoMapStatisticsEventTests \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapArtifactPlanning.swift" \
  "$project_root/Sources/TerentoPoC/Statistics/MapStatisticsEvent.swift" \
  "$project_root/Tests/TerentoPoCTests/MapStatisticsEventTests.swift" \
  -o "$build_dir/tests"

"$build_dir/tests"
