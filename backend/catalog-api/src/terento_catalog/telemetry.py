"""Shared validation and classification for privacy-minimised telemetry."""

from __future__ import annotations

import re
from typing import Any


# SemVer 2.0-compatible release identity.  Labels are deliberately bounded by
# the event validators as well, so this helper only answers format/classification.
SEMVER_RELEASE_LABEL = re.compile(
    r"^(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def validate_release_label(value: Any) -> str:
    """Return a safe release label or raise the public event error."""

    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > 80
        or "/Users/" in value
        or "file://" in value
        or SEMVER_RELEASE_LABEL.fullmatch(value) is None
    ):
        raise ValueError("invalid_releaseLabel")
    return value


def is_local_release_label(value: Any) -> bool:
    """Classify only a valid SemVer label with the exact ``-local`` suffix."""

    return (
        isinstance(value, str)
        and SEMVER_RELEASE_LABEL.fullmatch(value) is not None
        and value.endswith("-local")
    )

