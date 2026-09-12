#!/usr/bin/env python3
"""Compare live release identity with the tested deployment input; no network."""
import json
import sys

FIELDS = ("schemaVersion", "product", "platform", "publishedAt", "summary", "architecture", "version", "build", "releaseLabel", "releaseTag", "channel",
          "minimumMacOS", "downloadURL", "releaseURL", "releaseNotesURL", "sha256")

def validate(expected, actual):
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        raise ValueError("release manifests must be JSON objects")
    if expected.get("architecture") != "arm64":
        raise ValueError("unsupported release architecture")
    for field in FIELDS:
        if field not in expected or field not in actual or type(actual[field]) is not type(expected[field]) or actual[field] != expected[field]:
            raise ValueError(f"live release identity differs: {field}")

if __name__ == "__main__":
    validate(json.load(open(sys.argv[1])), json.load(open(sys.argv[2])))
    print("PASS: live manifest matches the tested release identity, URLs and checksum")
