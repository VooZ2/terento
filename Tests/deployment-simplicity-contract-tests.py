"""Prevent the ordinary deployment path from regaining target-specific branches."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent
ACTIVE_FILES = (
    ROOT / "AGENTS.md",
    ROOT / "backend/catalog-api/AGENTS.md",
    ROOT / "backend/catalog-api/README.md",
    ROOT / "backend/catalog-api/docs/operations.md",
    ROOT / "backend/catalog-api/docs/production-operations-protocol.md",
    ROOT / "backend/catalog-api/docs/production-candidate-receipt.md",
    ROOT / "backend/catalog-api/docs/production-db-recovery.md",
    ROOT / "Tests/README.md",
    ROOT / "PROJECT_STRUCTURE.md",
    ROOT / ".github/workflows/deploy-catalog-api.yml",
    ROOT / ".github/workflows/publish-vps-images.yml",
    ROOT / "scripts/infra/terento-deploy.py",
    ROOT / "scripts/infra/terento-deploy-migration.py",
    ROOT / "scripts/infra/terento-deploy-ssh-entry.py.in",
    ROOT / "scripts/infra/deploy-vps-image.sh",
)
FORBIDDEN = (
    re.compile(r"target_\d{3}_separately_applied"),
    re.compile(r"migrate-vps-image\.sh"),
    re.compile(r"migrate\s+--target\s+\d{3}"),
    re.compile(r"terento/\d{3}-production-candidate"),
    re.compile(r"CANDIDATE_SOURCE_SHA"),
    re.compile(r"CANDIDATE_SOURCE_REF"),
    re.compile(r"candidate_source_sha"),
    re.compile(r"candidate_source_ref"),
    re.compile(r"candidate-\$GITHUB_SHA"),
)
MIGRATION_SAFETY_FILES = (
    ROOT / "AGENTS.md",
    ROOT / "backend/catalog-api/AGENTS.md",
    ROOT / "backend/catalog-api/docs/production-operations-protocol.md",
    ROOT / "backend/catalog-api/docs/operations.md",
)
MIGRATION_SAFETY_MARKERS = (
    "backward-compatible",
    "expand/contract",
    "rollback",
)


def main():
    errors = []
    for path in ACTIVE_FILES:
        source = path.read_text(encoding="utf-8") if path.exists() else ""
        for pattern in FORBIDDEN:
            if pattern.search(source):
                errors.append(f"{path.relative_to(ROOT)} reintroduced {pattern.pattern}")
    for path in MIGRATION_SAFETY_FILES:
        source = path.read_text(encoding="utf-8") if path.exists() else ""
        for marker in MIGRATION_SAFETY_MARKERS:
            if marker not in source:
                errors.append(f"{path.relative_to(ROOT)} is missing migration safety marker: {marker}")
    for path in (ROOT / "AGENTS.md", ROOT / "backend/catalog-api/AGENTS.md"):
        source = path.read_text(encoding="utf-8")
        if "one immutable-image" not in source or "deploy-only" not in source:
            errors.append(f"{path.relative_to(ROOT)} is missing the deployment simplicity rule")
    if errors:
        raise AssertionError("\n".join(errors))
    print(f"PASS: {len(ACTIVE_FILES)} active deployment files contain no target-specific path")


if __name__ == "__main__":
    main()
