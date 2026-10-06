"""Atomic preview tile releases on the public asset volume.

Layout under ``<asset root>/previews``::

    current.json                       {"release": "<id>"}
    releases/<id>/<area>/<style>/<z>/<x>/<y>.webp
    staging/<job>/<area>/<style>/...   rendered, not yet public

A new release hard-links every unchanged layer from the current one, so a
release only costs disk space for the layers that were redrawn. The newest
two releases are kept; older ones are removed after the switch.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

RELEASE_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")
SEGMENT = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TILE_PATH = re.compile(
    r"^/assets/previews/(?P<release>[0-9]{8}T[0-9]{6}Z)/(?P<area>[a-z0-9]+(?:-[a-z0-9]+)*)/"
    r"(?P<style>[a-z0-9]+(?:-[a-z0-9]+)*)/(?P<z>[0-9]{1,2})/(?P<x>[0-9]{1,7})/(?P<y>[0-9]{1,7})\.webp$"
)
KEEP_RELEASES = 2


def release_id(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class PreviewStore:
    def __init__(self, asset_root: Path) -> None:
        self.root = asset_root / "previews"
        self.releases = self.root / "releases"
        self.staging = self.root / "staging"

    # Reading -------------------------------------------------------------
    def current_release(self) -> str | None:
        try:
            value = json.loads((self.root / "current.json").read_text(encoding="utf-8")).get("release")
        except (OSError, ValueError):
            return None
        if isinstance(value, str) and RELEASE_PATTERN.fullmatch(value) and (self.releases / value).is_dir():
            return value
        return None

    def tile(self, request_path: str) -> tuple[bytes, str] | None:
        match = TILE_PATH.fullmatch(request_path)
        if match is None:
            return None
        parts = match.groupdict()
        path = (
            self.releases / parts["release"] / parts["area"] / parts["style"]
            / str(int(parts["z"])) / str(int(parts["x"])) / f"{int(parts['y'])}.webp"
        )
        try:
            path.resolve().relative_to(self.releases.resolve())
            data = path.read_bytes()
        except (OSError, ValueError):
            return None
        if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
            return None
        stat = path.stat()
        return data, f'"{parts["release"]}-{stat.st_ino:x}-{stat.st_size:x}"'

    def layers(self, release: str) -> set[tuple[str, str]]:
        base = self.releases / release
        found: set[tuple[str, str]] = set()
        if not base.is_dir():
            return found
        for area in base.iterdir():
            if area.is_dir() and SEGMENT.fullmatch(area.name):
                for style in area.iterdir():
                    if style.is_dir() and SEGMENT.fullmatch(style.name):
                        found.add((area.name, style.name))
        return found

    # Writing -------------------------------------------------------------
    def staging_dir(self, job: str) -> Path:
        path = self.staging / job
        path.mkdir(parents=True, exist_ok=True)
        return path

    def publish(
        self,
        *,
        release: str,
        staged: dict[tuple[str, str], Path],
        keep: Iterable[tuple[str, str]],
    ) -> Path:
        """Create ``release`` from ``staged`` layers plus kept current layers."""
        if not RELEASE_PATTERN.fullmatch(release):
            raise ValueError("invalid release id")
        self.releases.mkdir(parents=True, exist_ok=True)
        building = self.releases / f".building-{release}"
        shutil.rmtree(building, ignore_errors=True)
        building.mkdir(parents=True)
        current = self.current_release()
        try:
            if current is not None:
                for area_id, style_id in keep:
                    if (area_id, style_id) in staged:
                        continue
                    source = self.releases / current / area_id / style_id
                    if source.is_dir():
                        _link_tree(source, building / area_id / style_id)
            for (area_id, style_id), source in staged.items():
                if not (SEGMENT.fullmatch(area_id) and SEGMENT.fullmatch(style_id)):
                    raise ValueError("invalid layer id")
                target = building / area_id / style_id
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, target)
            final = self.releases / release
            os.replace(building, final)
            _write_atomic(self.root / "current.json", json.dumps({"release": release}).encode("utf-8"))
        except BaseException:
            shutil.rmtree(building, ignore_errors=True)
            raise
        self.prune()
        return final

    def prune(self) -> None:
        if not self.releases.is_dir():
            return
        current = self.current_release()
        releases = sorted(
            (path.name for path in self.releases.iterdir() if path.is_dir() and RELEASE_PATTERN.fullmatch(path.name)),
            reverse=True,
        )
        keep = set(releases[:KEEP_RELEASES])
        if current:
            keep.add(current)
        for name in releases:
            if name not in keep:
                shutil.rmtree(self.releases / name, ignore_errors=True)
        for path in self.releases.iterdir():
            if path.name.startswith(".building-"):
                shutil.rmtree(path, ignore_errors=True)

    def clear_staging(self) -> None:
        shutil.rmtree(self.staging, ignore_errors=True)

    def disk_usage(self) -> int:
        """Bytes used under the preview root, counting hard links once."""
        seen: set[tuple[int, int]] = set()
        total = 0
        for directory, _dirs, files in os.walk(self.root):
            for name in files:
                try:
                    stat = os.lstat(os.path.join(directory, name))
                except OSError:
                    continue
                key = (stat.st_dev, stat.st_ino)
                if key not in seen:
                    seen.add(key)
                    total += stat.st_size
        return total


def directory_bytes(path: Path) -> int:
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


def _link_tree(source: Path, target: Path) -> None:
    for directory, _dirs, files in os.walk(source):
        relative = Path(directory).relative_to(source)
        (target / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            os.link(Path(directory, name), target / relative / name)


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
