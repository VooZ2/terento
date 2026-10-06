"""Run the bundled ``terento-preview-render`` tool with bounded resources."""
from __future__ import annotations

import json
import os
import resource
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .areas import PreviewArea

DEFAULT_RENDERER = Path("/usr/local/bin/terento-preview-render")


class RenderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class MapInfo:
    bounds: tuple[float, float, float, float]
    has_dem: bool
    has_typ: bool

    def covers(self, lon: float, lat: float) -> bool:
        west, south, east, north = self.bounds
        return west <= lon <= east and south <= lat <= north


@dataclass(frozen=True)
class RenderResult:
    tiles: int
    bytes: int
    seconds: float


class Renderer:
    def __init__(
        self,
        executable: Path = DEFAULT_RENDERER,
        *,
        timeout_seconds: int = 3600,
        memory_limit_bytes: int = 1536 * 1024 * 1024,
        quality: int = 78,
    ) -> None:
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.memory_limit_bytes = memory_limit_bytes
        self.quality = quality

    def available(self) -> bool:
        return self.executable.is_file() and os.access(self.executable, os.X_OK)

    def info(self, img: Path) -> MapInfo:
        document = self._run(["--img", str(img), "--info"], timeout=120)
        west, south, east, north = (float(part) for part in str(document["bounds"]).split(","))
        return MapInfo((west, south, east, north), bool(document.get("hasDEM")), bool(document.get("hasTYP")))

    def render(self, area: PreviewArea, imgs: list[Path], output: Path) -> RenderResult:
        west, south, east, north = area.bbox
        args: list[str] = []
        for img in imgs:
            args += ["--img", str(img)]
        args += [
            "--bbox", f"{west:.6f},{south:.6f},{east:.6f},{north:.6f}",
            "--zoom", f"{area.min_zoom}-{area.max_zoom}",
            "--out", str(output),
            "--quality", str(self.quality),
        ]
        document = self._run(args, timeout=self.timeout_seconds)
        return RenderResult(int(document["tiles"]), int(document["bytes"]), float(document["seconds"]))

    def compare(self, first: Path, second: Path, zoom: int) -> float | None:
        document = self._run(["--compare", str(first), str(second), "--zoom", f"{zoom}-{zoom}"], timeout=600)
        score = document.get("score")
        return None if score is None else float(score)

    def _run(self, args: list[str], *, timeout: int) -> dict:
        if not self.available():
            raise RenderError("renderer_missing", f"{self.executable} is not installed")
        environment = dict(os.environ)
        environment.setdefault("QT_QPA_PLATFORM", "offscreen")
        environment.setdefault("XDG_RUNTIME_DIR", "/tmp")
        limit = self.memory_limit_bytes

        def lower_priority() -> None:  # pragma: no cover - runs in the child
            os.nice(19)
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

        try:
            completed = subprocess.run(
                [str(self.executable), *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=environment,
                preexec_fn=lower_priority,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RenderError("render_timeout", f"Renderer exceeded {timeout} seconds") from error
        if completed.returncode != 0:
            detail = (completed.stderr or "").strip().splitlines()[-1:] or [""]
            raise RenderError("render_failed", f"Renderer exited with {completed.returncode}: {detail[0][:300]}")
        try:
            return json.loads(completed.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError) as error:
            raise RenderError("render_output", "Renderer returned no result") from error
