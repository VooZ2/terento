"""Canonical compatibility status contract.

The database view is the production aggregation boundary, while this module
keeps the same promotion rules executable in deterministic backend tests and
operator tooling. Counts are evidence metrics only; they never promote a
model on their own.
"""

from __future__ import annotations

from enum import Enum


class CompatibilityStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    TESTING = "TESTING"
    TESTED = "TESTED"
    SUPPORTED = "SUPPORTED"
    VERIFIED = "VERIFIED"


PUBLIC_COMPATIBILITY_STATUSES = frozenset(
    {CompatibilityStatus.TESTED, CompatibilityStatus.SUPPORTED, CompatibilityStatus.VERIFIED}
)


def calculate_compatibility_status(
    *,
    evidence_count: int,
    successful_install_count: int,
    firmware_version_count: int,
    physical_device_count: int,
    reconnect_verified_install_count: int = 0,
) -> CompatibilityStatus:
    """Return the canonical status for one exact device identity.

    ``physical_device_count`` is an operator-reviewed, privacy-preserving
    count. No Garmin Unit ID, serial number, or account identifier is needed
    or accepted. Reconnect fields are optional diagnostic evidence and never
    gate a status. A successful install is the support gate; the verified gate
    additionally needs reviewed device plurality and firmware variation.
    """

    if evidence_count <= 0:
        return CompatibilityStatus.UNKNOWN
    if successful_install_count <= 0:
        return CompatibilityStatus.TESTING
    if physical_device_count >= 2 and firmware_version_count >= 2:
        return CompatibilityStatus.VERIFIED
    return CompatibilityStatus.SUPPORTED


STATUS_PUBLIC_COPY: dict[CompatibilityStatus, str] = {
    CompatibilityStatus.UNKNOWN: "This exact device is known, but Terento does not have enough real hardware evidence yet.",
    CompatibilityStatus.TESTING: "This exact device is currently under validation or has only partial evidence.",
    CompatibilityStatus.TESTED: "Real hardware evidence exists for this model, but it is not yet a full support claim.",
    CompatibilityStatus.SUPPORTED: "A real map installation completed successfully for this exact model.",
    CompatibilityStatus.VERIFIED: "Confirmed across multiple physical devices and firmware versions.",
}
