"""Build read-only Admin pages with deterministic presentation evidence."""

from pathlib import Path
import shutil
import sys

from admin_plan_preview import build
from terento_catalog.admin import _map_statistics_summary, diagnostics_page, map_statistics_page


def create(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    build(root)
    providers = [
        {"id": provider, "name": name, "health": "HEALTHY"}
        for provider, name in (
            ("opentopomap", "OpenTopoMap"), ("maprando", "MapRando"),
            ("freizeitkarte", "Freizeitkarte"), ("bbbike", "BBBike"),
            ("custom", "custom"),
        )
    ]
    rows = []
    for provider, successful, failed in (
        ("opentopomap", 14, 6), ("maprando", 23, 2),
        ("freizeitkarte", 19, 6), ("bbbike", 8, 1), ("custom", 20, 3),
    ):
        for event_type, outcome, count in (
            ("INSTALL_SUCCEEDED", "SUCCEEDED", successful),
            ("INSTALL_FAILED", "FAILED", failed),
        ):
            rows.append({
                "provider_id": provider, "map_package_id": provider + "-fixture",
                "region": "LT", "region_identity": "LITHUANIA",
                "region_display_name": "Lithuania", "region_country": "LT",
                "component_kind": "main", "event_type": event_type,
                "outcome": outcome, "operation_count": count, "event_count": count,
                "last_occurred_at": "2026-09-18T09:39:00Z",
            })
    rows.extend([
        {"provider_id": "opentopomap", "event_type": "DOWNLOAD_SUCCEEDED", "outcome": "SUCCEEDED", "operation_count": 84, "event_count": 84},
        {"provider_id": "opentopomap", "event_type": "DOWNLOAD_FAILED", "outcome": "FAILED", "operation_count": 4, "event_count": 4},
        {"provider_id": "opentopomap", "event_type": "DOWNLOAD_INTERRUPTED", "outcome": "UNKNOWN", "operation_count": 7, "event_count": 7},
        {"provider_id": "opentopomap", "event_type": "DOWNLOAD_STARTED", "outcome": "STARTED", "operation_count": 3, "event_count": 3},
    ])
    statistics = {"rows": rows, "summary": _map_statistics_summary(rows)}
    (root / "statistics.html").write_bytes(map_statistics_page(
        statistics, providers, {"username": "Preview"}, "fixture",
    ))
    (root / "diagnostics.html").write_bytes(diagnostics_page(
        [], {"username": "Preview"}, "fixture", identity="Fixture watch",
        operations=[{
            "event_id": "fixture-diagnostic", "operation_key": "fixture-diagnostic",
            "compatibility_identity": "Fixture watch", "model": "Fixture watch",
            "provider": "opentopomap", "region": "Lithuania",
            "phase_outcome": "FAILED", "diagnostic_status": "ACTIVE",
            "error_category": "TRANSFER_FAILED", "write_started": True,
            "occurred_at": "2026-09-18T09:39:00Z",
        }],
    ))
    shutil.copyfile(Path(__file__).with_name("admin_presentation_browser.html"), root / "presentation-check.html")


if __name__ == "__main__":
    create(Path(sys.argv[1]))
