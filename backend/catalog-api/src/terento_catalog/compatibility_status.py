"""Canonical compatibility status contract.

Only privacy-minimised, opt-in installation reports reach this classifier.
The exact model/variant identity is selected by the caller; this function
only classifies its qualifying successful-install count.
"""

from __future__ import annotations

from enum import Enum


class CompatibilityStatus(str, Enum):
    TESTING = "TESTING"
    TESTED = "TESTED"
    SUPPORTED = "SUPPORTED"
    VERIFIED = "VERIFIED"


CANONICAL_STATUS_ORDER = (
    CompatibilityStatus.TESTING,
    CompatibilityStatus.TESTED,
    CompatibilityStatus.SUPPORTED,
    CompatibilityStatus.VERIFIED,
)
CANONICAL_STATUS_VALUES = tuple(status.value for status in CANONICAL_STATUS_ORDER)


PUBLIC_COMPATIBILITY_STATUSES = frozenset(
    CANONICAL_STATUS_ORDER
)


def calculate_compatibility_status(
    *,
    successful_install_count: int,
    recognized_map_capable_evidence: bool = False,
) -> CompatibilityStatus | None:
    """Return the canonical status for one exact model and variant.

    ``None`` is used for a non-map device or an identity with no qualifying
    map-capable evidence. It is deliberately not a compatibility status.
    Successful reports are already consent-gated by the evidence endpoint;
    failed reports and recognition-only evidence contribute zero successes.
    """

    if successful_install_count < 0:
        raise ValueError("successful_install_count must not be negative")
    if not recognized_map_capable_evidence:
        return None
    # Keep the threshold order explicit: this is the shared classifier used
    # by the public projection, admin projection, and tests.  The database
    # view mirrors these boundaries for query-side filtering.
    if successful_install_count == 0:
        return CompatibilityStatus.TESTING
    if successful_install_count < 3:
        return CompatibilityStatus.TESTED
    if successful_install_count < 5:
        return CompatibilityStatus.SUPPORTED
    return CompatibilityStatus.VERIFIED


STATUS_PUBLIC_COPY: dict[CompatibilityStatus, str] = {
    CompatibilityStatus.TESTING: "Terento has recognized this model as map-capable, but no successful shared installation has been received yet.",
    CompatibilityStatus.TESTED: "1–2 successful installations have been shared by Terento users.",
    CompatibilityStatus.SUPPORTED: "3–4 successful installations have been shared by Terento users.",
    CompatibilityStatus.VERIFIED: "5 or more successful installations have been shared by Terento users.",
}
