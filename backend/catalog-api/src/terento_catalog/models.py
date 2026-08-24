from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, order=True)
class NormalizedVersion:
    year: int
    month: int

    def __post_init__(self) -> None:
        if self.year < 2000 or not 1 <= self.month <= 12:
            raise ValueError("normalized map version is outside the supported range")


@dataclass(frozen=True)
class ProviderMetadata:
    id: str
    name: str
    website: str
    license_information: str
    attribution: str
    license_url: str


@dataclass(frozen=True)
class MapMetadata:
    id: str
    provider_id: str
    name: str
    region: str
    country: str
    identifier: str
    managed_by_terento: bool = True


@dataclass(frozen=True)
class CollectedMap:
    provider: ProviderMetadata
    map: MapMetadata
    version: NormalizedVersion
    raw_version: str
    file_size_bytes: int | None
    source_url: str
    release_date: date | None
    checksum_sha256: str | None = None
    download_size_bytes: int | None = None
    install_size_bytes: int | None = None
    install_payload_path: str | None = None
    size_measurement_method: str | None = None
    size_measured_at: datetime | None = None
    size_measurement_warning: str | None = None


@dataclass(frozen=True)
class DeviceAsset:
    """Metadata for a lifecycle-managed, Terento-controlled device asset."""

    asset_type: str
    url: str | None
    sha256: str | None = None
    width: int | None = None
    height: int | None = None
    mime_type: str | None = None
    version: int | None = None
    attribution: str | None = None
    source_type: str | None = None
    source_brand: str | None = None
    attribution_required: bool | None = None
    scope: str = "MODEL"
    status: str = "AVAILABLE"
    storage_key: str | None = None


@dataclass(frozen=True)
class CollectedDevice:
    """A canonical Garmin device record discovered from an official source."""

    id: str
    family_id: str
    family_name: str
    manufacturer: str
    model: str
    canonical_model: str
    variant: str
    case_size_mm: int | None
    display_type: str | None
    part_number: str | None
    product_url: str
    source_url: str
    asset: DeviceAsset | None = None
    source_image_url: str | None = None
