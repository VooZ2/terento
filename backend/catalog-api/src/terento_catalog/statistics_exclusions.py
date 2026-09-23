from __future__ import annotations

from typing import Any


OUT_OF_SCOPE_PREWRITE = "OUT_OF_SCOPE_PREWRITE"
SECURITY_OUT_OF_SCOPE_WRITE = "OUT_OF_SCOPE_WRITE"


def classify_compatibility_event(
    event: dict[str, Any],
    devices: list[dict[str, Any]],
    assessment: dict[str, Any],
) -> dict[str, str] | None:
    canonical_id = assessment.get("canonicalDeviceId")
    device = next((row for row in devices if row.get("id") == canonical_id), None)
    # A historical device label alone cannot classify an event as out-of-scope.
    # Only an exact catalog row whose stored policy inputs deny writes can do
    # that; operator support metadata is irrelevant.
    out_of_scope = device is not None and (
        device.get("active") is False or device.get("map_capable") is False
    )
    if not out_of_scope:
        return None

    write_started = event.get("writeStarted")
    remote_created = event.get("remoteObjectCreated")
    if write_started is True or remote_created is True:
        return {
            "securityIssueCode": SECURITY_OUT_OF_SCOPE_WRITE,
            "reason": "An out-of-scope device reported a write boundary or remote object.",
        }
    # Both negative facts must be explicit. A missing write or remote-object
    # observation is not proof that the mutation boundary was never reached.
    # Historical incident cleanup verifies old rows independently.
    if write_started is not False or remote_created is not False:
        return None
    return {
        "statisticsExclusionCode": OUT_OF_SCOPE_PREWRITE,
        "reason": "The device was outside Terento scope and was blocked before the write boundary.",
    }
