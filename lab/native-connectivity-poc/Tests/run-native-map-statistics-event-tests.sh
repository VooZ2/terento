#!/bin/zsh
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/terento-map-statistics-tests.XXXXXX")"

swiftc -parse-as-library -module-name TerentoMapStatisticsEventTests \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapIdentity.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapVersion.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapModels.swift" \
  "$project_root/Sources/TerentoPoC/MapCatalog/MapArtifactPlanning.swift" \
  "$project_root/Sources/TerentoPoC/Statistics/MapStatisticsEvent.swift" \
  "$project_root/Tests/TerentoPoCTests/MapStatisticsEventTests.swift" \
  -o "$build_dir/tests"

"$build_dir/tests"
