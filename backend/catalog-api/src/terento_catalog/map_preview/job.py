"""Map style preview rendering inside a UTC window.

Inside the configured UTC window the worker picks preview layers that are
missing, failed earlier, use an outdated package version or are older than
the refresh period. Layers that share a provider package are rendered from
one temporary download; the download is deleted as soon as its tiles exist.
Finished layers are published as a new release at most every
``publish_interval`` during a window and once more when the window ends.
"""
from __future__ import annotations

import itertools
import logging
import os
import socket
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, time as day_time, timedelta, timezone
from pathlib import Path
from threading import Event, Thread
from typing import Any, Callable

from .acquire import AcquisitionError, Limits, download, extract_img, remove_tree
from .areas import PreviewArea, load_areas, tile_count
from .publish import PreviewStore, directory_bytes, release_id
from .render import RenderError, Renderer
from .store import PreviewDatabase
from .styles import STYLE_BY_ID, STYLES, Candidate, PreviewStyle, candidates_for, packages_from_snapshot

LOGGER = logging.getLogger(__name__)
JOB_NAME = "map-preview-renderer"
ESTIMATED_TILE_BYTES = 24 * 1024
FAILURE_BACKOFF = timedelta(days=3)
# The lease is short and renewed while a window runs, so a renderer killed by
# a deploy or crash blocks the next one for at most LEASE_SECONDS.
LEASE_SECONDS = 15 * 60
LEASE_RENEW_SECONDS = 2 * 60


@dataclass(frozen=True)
class PreviewSettings:
    enabled: bool
    asset_root: Path
    work_dir: Path
    window_utc: tuple[day_time, day_time]
    refresh_days: int
    max_total_bytes: int
    max_source_bytes: int
    min_free_bytes: int
    renderer: Path
    public_base_url: str
    publish_interval: timedelta = timedelta(minutes=30)
    render_jobs: int = 1

    def limits(self) -> Limits:
        return Limits(max_source_bytes=self.max_source_bytes, min_free_bytes=self.min_free_bytes)


@dataclass
class WorkItem:
    area: PreviewArea
    style: PreviewStyle
    candidates: list[Candidate]
    existing: dict[str, Any] | None = None
    attempts: list[str] = field(default_factory=list)


@dataclass
class WindowResult:
    rendered: int = 0
    not_covered: int = 0
    failed: int = 0
    skipped_budget: bool = False
    release: str | None = None
    lease_busy: bool = False


def parse_window(value: str) -> tuple[day_time, day_time]:
    try:
        start_text, end_text = value.strip().split("-", 1)
        start = day_time.fromisoformat(start_text.strip())
        end = day_time.fromisoformat(end_text.strip())
    except ValueError as exc:
        raise RuntimeError("MAP_PREVIEW_WINDOW_UTC must use HH:MM-HH:MM") from exc
    # Equal start and end (for example 00:00-00:00) is a window around the clock.
    return start, end


def next_window(now: datetime, window: tuple[day_time, day_time]) -> tuple[datetime, datetime]:
    """Return the current or next (start, end) window in UTC."""
    now = now.astimezone(timezone.utc)
    start_time, end_time = window
    for offset in (-1, 0, 1):
        day = (now + timedelta(days=offset)).date()
        start = datetime.combine(day, start_time, tzinfo=timezone.utc)
        end = datetime.combine(day, end_time, tzinfo=timezone.utc)
        if end <= start:
            end += timedelta(days=1)
        if now < end:
            return start, end
    raise AssertionError("unreachable")  # pragma: no cover


def plan_work(
    areas: list[PreviewArea],
    packages: list[dict[str, Any]],
    layers: dict[tuple[str, str], dict[str, Any]],
    bounds: dict[tuple[str, str], tuple[float, float, float, float]],
    enabled_providers: set[str],
    *,
    now: datetime,
    refresh_days: int,
    published: set[tuple[str, str]] | None = None,
) -> tuple[list[WorkItem], list[tuple[PreviewArea, PreviewStyle]]]:
    """Return (layers to render, layers no enabled package covers).

    A layer counts as done only when its tiles are in the published release:
    a renderer stopped between drawing a layer and publishing it leaves an
    AVAILABLE row without tiles, and that layer is drawn again.
    """
    work: list[WorkItem] = []
    uncovered: list[tuple[PreviewArea, PreviewStyle]] = []
    ordered = sorted(areas, key=lambda area: (not area.featured, areas.index(area)))
    for area in ordered:
        for style in STYLES:
            if style.provider_id not in enabled_providers:
                continue
            candidates = candidates_for(area, style, packages, known_bounds=bounds)
            existing = layers.get((area.id, style.id))
            if not candidates:
                if existing is None or existing["status"] != "NOT_COVERED":
                    uncovered.append((area, style))
                continue
            if existing is not None:
                retry_at = existing.get("retry_not_before")
                if retry_at is not None and retry_at > now:
                    continue
                if existing["status"] == "AVAILABLE" and (published is None or (area.id, style.id) in published):
                    current = {(c.package_id, c.package_version) for c in candidates}
                    fresh = existing.get("rendered_at") and existing["rendered_at"] > now - timedelta(days=refresh_days)
                    if (existing.get("package_id"), existing.get("package_version")) in current and fresh:
                        continue
            work.append(WorkItem(area, style, candidates, existing))
    return work, uncovered


class PreviewRun:
    def __init__(
        self,
        database: Any,
        settings: PreviewSettings,
        *,
        renderer: Renderer | None = None,
        store: PreviewStore | None = None,
        db: PreviewDatabase | None = None,
        areas: list[PreviewArea] | None = None,
        downloader: Callable[..., Path] = download,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.database = database
        self.settings = settings
        self.renderer = renderer or Renderer(settings.renderer, jobs=settings.render_jobs)
        self.store = store or PreviewStore(settings.asset_root)
        self.db = db or PreviewDatabase(database)
        self.areas = areas if areas is not None else load_areas()
        self.download = downloader
        self.clock = clock

    def run(self, deadline: datetime, stop: Event | None = None) -> WindowResult:
        result = WindowResult()
        owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        if not self.db.acquire_lease(owner, LEASE_SECONDS):
            LOGGER.info("map previews: another renderer holds the lease")
            result.lease_busy = True
            return result
        renewing = Event()
        renewer = Thread(target=self._renew_lease, args=(owner, renewing), name="map-preview-lease", daemon=True)
        renewer.start()
        job = uuid.uuid4().hex
        staged: dict[tuple[str, str], Path] = {}
        try:
            self._clear_leftovers()
            rows, _updated = self.database.catalog_snapshot()
            packages = packages_from_snapshot(rows)
            layers = self.db.layers()
            bounds = self.db.package_bounds()
            enabled = self.db.enabled_providers()
            current = self.store.current_release()
            published = self.store.layers(current) if current else set()
            # Layers an earlier renderer left with transparent land are redrawn.
            published = {key for key in published if not self.store.has_transparency(current, *key)}
            work, uncovered = plan_work(
                self.areas, packages, layers, bounds, enabled,
                now=self.clock(), refresh_days=self.settings.refresh_days,
                published=published,
            )
            for area, style in uncovered:
                self.db.save_layer(area.id, style.id, style.provider_id, "NOT_COVERED")
                result.not_covered += 1
            # A layer marked uncovered that now has a package (for example
            # after a catalog change) is pending again, not "no map here".
            for item in work:
                if item.existing is not None and item.existing.get("status") == "NOT_COVERED":
                    self.db.save_layer(item.area.id, item.style.id, item.style.provider_id, "PENDING")
            LOGGER.info("map previews: %d layers to render, %d not covered", len(work), len(uncovered))
            staging = self.store.staging_dir(job)
            queue = list(work)
            last_publish = self.clock()
            while queue:
                if (stop is not None and stop.is_set()) or self.clock() >= deadline:
                    break
                package = self._next_candidate(queue[0])
                if package is None:
                    item = queue.pop(0)
                    self._record_not_covered(item)
                    result.not_covered += 1
                    continue
                batch = [item for item in queue if self._next_candidate(item) is not None
                         and self._next_candidate(item).package_id == package.package_id]
                queue = [item for item in queue if item not in batch]
                if not self._within_budget(batch, staged):
                    result.skipped_budget = True
                    LOGGER.warning("map previews: disk budget reached; stopping this window")
                    break
                outcome = self._render_package(package, batch, staging, staged, deadline)
                result.rendered += outcome["rendered"]
                result.failed += outcome["failed"]
                queue.extend(outcome["retry"])
                # Publish finished layers during long windows so previews
                # appear progressively instead of only when the window ends.
                if staged and self.clock() - last_publish >= self.settings.publish_interval:
                    result.release = self._publish(staged)
                    staged.clear()
                    last_publish = self.clock()
            # Status-only changes need no new release: the manifest is built
            # from the database on request.
            if staged:
                result.release = self._publish(staged)
        finally:
            renewing.set()
            renewer.join(timeout=10)
            self.store.clear_staging()
            self.db.release_lease(owner)
        return result

    def _renew_lease(self, owner: str, stop: Event) -> None:
        while not stop.wait(LEASE_RENEW_SECONDS):
            try:
                self.db.acquire_lease(owner, LEASE_SECONDS)
            except Exception:  # noqa: BLE001 - the next renewal retries
                LOGGER.warning("map previews: lease renewal failed", exc_info=True)

    def _clear_leftovers(self) -> None:
        """Remove downloads and staged tiles a killed renderer left behind."""
        self.store.clear_staging()
        if self.settings.work_dir.is_dir():
            for child in self.settings.work_dir.iterdir():
                if child.is_dir() and not child.is_symlink():
                    remove_tree(child)
                else:
                    child.unlink(missing_ok=True)

    # Work -----------------------------------------------------------------------
    @staticmethod
    def _next_candidate(item: WorkItem) -> Candidate | None:
        for candidate in item.candidates:
            if candidate.package_id not in item.attempts:
                return candidate
        return None

    def _record_not_covered(self, item: WorkItem) -> None:
        self.db.save_layer(item.area.id, item.style.id, item.style.provider_id, "NOT_COVERED")

    def _within_budget(self, batch: list[WorkItem], staged: dict[tuple[str, str], Path]) -> bool:
        estimate = sum(tile_count(item.area) for item in batch) * ESTIMATED_TILE_BYTES
        pending = sum(directory_bytes(path) for path in staged.values())
        return self.store.disk_usage() + pending + estimate <= self.settings.max_total_bytes

    def _render_package(
        self,
        package: Candidate,
        batch: list[WorkItem],
        staging: Path,
        staged: dict[tuple[str, str], Path],
        deadline: datetime,
    ) -> dict[str, Any]:
        outcome: dict[str, Any] = {"rendered": 0, "failed": 0, "retry": []}
        work_dir = self.settings.work_dir / uuid.uuid4().hex
        work_dir.mkdir(parents=True, exist_ok=True)
        limits = self.settings.limits()
        try:
            try:
                imgs = [self._fetch(package.provider_id, package.main_url, work_dir / "main", package.size_bytes, limits)]
                for index, url in enumerate(package.overlay_urls):
                    imgs.append(self._fetch(package.provider_id, url, work_dir / f"overlay-{index}", package.size_bytes, limits))
                info = self.renderer.info(imgs[0])
            except (AcquisitionError, RenderError) as error:
                retry = getattr(error, "retry_not_before", None)
                for item in batch:
                    self._fail(item, error, retry)
                outcome["failed"] += len(batch)
                return outcome
            self.db.save_bounds(package.package_id, package.package_version, info.bounds)
            for item in batch:
                if self.clock() >= deadline:
                    break
                if not info.covers(*item.area.center):
                    item.attempts.append(package.package_id)
                    outcome["retry"].append(item)
                    continue
                target = staging / item.area.id / item.style.id
                remove_tree(target)
                try:
                    rendered = self.renderer.render(item.area, imgs, target)
                except RenderError as error:
                    remove_tree(target)
                    self._fail(item, error, None)
                    outcome["failed"] += 1
                    continue
                staged[(item.area.id, item.style.id)] = target
                self.db.save_layer(
                    item.area.id, item.style.id, item.style.provider_id, "AVAILABLE",
                    package_id=package.package_id, package_version=package.package_version,
                    tile_count=rendered.tiles, bytes_=rendered.bytes, rendered_at=self.clock(),
                )
                outcome["rendered"] += 1
        finally:
            remove_tree(work_dir)
        return outcome

    def _fetch(self, provider_id: str, url: str, directory: Path, expected: int, limits: Limits) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        name = url.rsplit("/", 1)[-1].split("?", 1)[0] or "source"
        source = self.download(provider_id, url, directory / name, expected_bytes=expected, limits=limits)
        return extract_img(source, directory, limits)

    def _fail(self, item: WorkItem, error: Exception, retry: datetime | None) -> None:
        code = getattr(error, "code", "failed")
        keep = item.existing is not None and item.existing.get("status") == "AVAILABLE"
        self.db.save_layer(
            item.area.id, item.style.id, item.style.provider_id,
            "AVAILABLE" if keep else "FAILED",
            retry_not_before=retry or (self.clock() + FAILURE_BACKOFF),
            error_code=code, error_message=str(error), keep_rendered=keep,
        )
        LOGGER.warning("map previews: %s/%s failed: %s", item.area.id, item.style.id, code)

    # Publishing -------------------------------------------------------------------
    def _publish(self, staged: dict[tuple[str, str], Path]) -> str | None:
        layers = self.db.layers()
        current = self.store.current_release()
        published = self.store.layers(current) if current else set()
        keep = [key for key in published if layers.get(key, {}).get("status") == "AVAILABLE"]
        self._score(staged, published, current)
        release = release_id(self.clock())
        if release == current:
            release = release_id(self.clock() + timedelta(seconds=1))
        self.store.publish(release=release, staged=dict(staged), keep=keep)
        final_layers = sorted(self.store.layers(release))
        self.db.mark_released(release, final_layers, len(final_layers), self.store.disk_usage())
        LOGGER.info("map previews: published %s with %d layers", release, len(final_layers))
        return release

    def _score(self, staged: dict[tuple[str, str], Path], published: set[tuple[str, str]], current: str | None) -> None:
        touched = {area_id for area_id, _style in staged}
        by_id = {area.id: area for area in self.areas}
        for area_id in touched:
            area = by_id.get(area_id)
            if area is None:
                continue
            directories: dict[str, Path] = {}
            for style in STYLES:
                key = (area_id, style.id)
                if key in staged:
                    directories[style.id] = staged[key]
                elif key in published and current:
                    directories[style.id] = self.store.releases / current / area_id / style.id
            zoom = min(area.min_zoom + 2, area.max_zoom)
            scores = []
            for first, second in itertools.combinations(sorted(directories), 2):
                try:
                    value = self.renderer.compare(directories[first], directories[second], zoom)
                except RenderError:
                    value = None
                if value is not None:
                    scores.append(value)
            self.db.save_score(area_id, sum(scores) / len(scores) if scores else None)


def run_worker(database: Any, stop: Event, settings: PreviewSettings, *, clock=lambda: datetime.now(timezone.utc)) -> None:
    """Scheduler thread: render inside each window until stopped."""
    if not settings.enabled:
        LOGGER.info("map previews are disabled (MAP_PREVIEW_ENABLED=false)")
        return
    renderer = Renderer(settings.renderer, jobs=settings.render_jobs)
    if not renderer.available():
        LOGGER.error("map previews enabled but %s is missing", settings.renderer)
        return
    while not stop.is_set():
        start, end = next_window(clock(), settings.window_utc)
        now = clock()
        if now < start:
            _heartbeat(database, status="WAITING", next_run_at=start)
            stop.wait(max(1.0, (start - now).total_seconds()))
            continue
        _heartbeat(database, status="RUNNING", started_at=now)
        try:
            result = PreviewRun(database, settings, renderer=renderer, clock=clock).run(end, stop)
            if result.lease_busy:
                # A renderer stopped by a deploy keeps its lease until it
                # expires; retry soon instead of waiting for the next window.
                stop.wait(LEASE_RENEW_SECONDS)
                continue
            status = "WARNING" if result.failed or result.skipped_budget else "HEALTHY"
            summary = None
            if result.failed or result.skipped_budget:
                summary = f"{result.failed} preview layers failed" + ("; disk budget reached" if result.skipped_budget else "")
            _heartbeat(database, status=status, completed_at=clock(), error_summary=summary)
            LOGGER.info("map previews window done: rendered=%d not_covered=%d failed=%d release=%s",
                        result.rendered, result.not_covered, result.failed, result.release)
        except Exception as error:  # noqa: BLE001 - keep the scheduler alive
            LOGGER.exception("map preview window failed; next window will retry")
            _heartbeat(database, status="FAILED", completed_at=clock(), error_summary=f"{type(error).__name__}: {str(error)[:300]}")
        _, end = next_window(clock(), settings.window_utc)
        remaining = (end - clock()).total_seconds()
        if remaining > 0:
            stop.wait(remaining)


def _heartbeat(database: Any, **values: Any) -> None:
    try:
        database.record_scheduler_heartbeat(job_name=JOB_NAME, **values)
    except Exception:  # noqa: BLE001 - observability must not stop rendering
        LOGGER.exception("map preview heartbeat update failed")
