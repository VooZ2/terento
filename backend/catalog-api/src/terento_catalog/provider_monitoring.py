"""Provider download policy and periodic checks; no map binaries are stored."""
from datetime import datetime, timedelta, timezone
import logging

LOGGER = logging.getLogger(__name__)


def _timestamp(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value and value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def monitoring_state(checked_at, interval_hours=1, now=None, retry_at=None):
    now = now or datetime.now(timezone.utc)
    checked_at = _timestamp(checked_at)
    retry_at = _timestamp(retry_at)
    due = checked_at + timedelta(hours=interval_hours) if checked_at else None
    next_check = max(due or now, retry_at) if retry_at else due
    return {'intervalHours': interval_hours,
            'nextCheckAt': next_check.isoformat() if next_check else None,
            'stale': due is None or now > due + timedelta(minutes=10)}


def provider_block_reason(status, download_status, checked_at, interval_hours=1, now=None, retry_at=None):
    now = now or datetime.now(timezone.utc)
    retry_at = _timestamp(retry_at)
    if retry_at and retry_at > now:
        return 'PROVIDER_RATE_LIMITED'
    if status != 'ACTIVE':
        return 'PROVIDER_PAUSED'
    # Keep a known outage blocked until a successful check supersedes it.
    if download_status == 'DOWN':
        return 'PROVIDER_DOWN'
    if download_status in (None, 'UNKNOWN') or monitoring_state(checked_at, interval_hours, now)['stale']:
        return 'STATUS_STALE'
    return None


def run_health_cycle(database, check=None):
    # Reuse the same lock, cooldown, source validation and audit path as Admin.
    if check is None:
        from .http_api import CatalogService
        check = CatalogService(database).check_provider
    database.prune_provider_health_history()
    for row in database.due_provider_health_checks():
        try:
            check(row['id'], scheduled=True)
        except ValueError:
            LOGGER.info('Provider check deferred: %s', row['id'])
        except Exception:
            LOGGER.exception('Provider check failed: %s; retry next cycle', row['id'])


def run_worker(database, stop):
    while not stop.is_set():
        try:
            run_health_cycle(database)
        except Exception:
            LOGGER.exception('Provider health schedule failed; retry next cycle')
        stop.wait(60)
