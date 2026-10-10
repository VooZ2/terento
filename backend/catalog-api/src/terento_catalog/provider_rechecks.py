"""Bounded original-source checks, durable jobs and provider-scoped serialization."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import re
import json
import logging
from urllib.error import HTTPError
from urllib.parse import urlparse, unquote
from urllib.request import HTTPRedirectHandler, build_opener

@contextmanager
def provider_lock(database, provider_id):
    with database.connection() as connection:
        locked = connection.execute("SELECT pg_try_advisory_lock(hashtext(%s)) AS acquired", ('provider:'+provider_id,)).fetchone()['acquired']
        if not locked:
            raise ValueError('provider_busy')
        try:
            yield
        finally:
            connection.execute("SELECT pg_advisory_unlock(hashtext(%s))", ('provider:'+provider_id,))


def ensure_retry_allowed(database, provider_id):
    """Shared cooldown for collection, health checks and targeted recovery."""
    with database.connection() as c:
        health = c.execute("SELECT health_retry_not_before FROM map_provider WHERE id=%s", (provider_id,)).fetchone()
        if health and health['health_retry_not_before'] and health['health_retry_not_before'] > datetime.now(timezone.utc):
            raise ValueError(f"Provider rate limit: retry after {health['health_retry_not_before'].isoformat()}")
        row = c.execute(
            "SELECT max(retry_not_before) AS retry_at FROM provider_recheck "
            "WHERE provider_id=%s AND retry_not_before > now()", (provider_id,)
        ).fetchone()
        if row and row['retry_at']:
            raise ValueError(f"Provider rate limit: retry after {row['retry_at'].isoformat()}")


def enqueue(database, provider_id, package_id, admin_id):
    with database.connection() as c:
        provider = c.execute("SELECT status FROM map_provider WHERE id=%s FOR UPDATE", (provider_id,)).fetchone()
        if not provider:
            raise LookupError('provider_not_found')
        if provider['status'] == 'RETIRED':
            raise LookupError('provider_retired')
        if package_id and not c.execute("SELECT id FROM map_package WHERE id=%s AND provider_id=%s AND availability <> 'RETIRED'", (package_id,provider_id)).fetchone():
            raise LookupError('package_not_found')
        # Enforce a provider cooldown across page reloads and repeated jobs.
        recent = c.execute("SELECT id,state,package_id,GREATEST(retry_not_before,created_at+interval '5 minutes') AS retry_at FROM provider_recheck WHERE provider_id=%s AND (state IN ('QUEUED','RUNNING') OR retry_not_before > now() OR created_at > now()-interval '5 minutes') ORDER BY id DESC LIMIT 1", (provider_id,)).fetchone()
        if recent:
            if recent['state'] in {'QUEUED', 'RUNNING'}:
                if recent['package_id'] == package_id:
                    return {'jobId': recent['id']}
                raise ValueError('provider_busy: another package check is active')
            raise ValueError(f"Provider check cooldown: retry after {recent['retry_at'].isoformat()}")
        row = c.execute("INSERT INTO provider_recheck(provider_id,package_id,admin_user_id) VALUES(%s,%s,%s) RETURNING id", (provider_id,package_id,admin_id)).fetchone()
        return {'jobId': row['id']}


def jobs(database, provider_id):
    with database.connection() as c:
        return list(c.execute("SELECT * FROM provider_recheck WHERE provider_id=%s ORDER BY id DESC LIMIT 10", (provider_id,)).fetchall())


def inspect_artifact(row):
    """Use the provider's existing validator; no user-supplied URLs."""
    from .provider_catalog import ProviderCollectionError
    codes = row.get('country_codes') or []
    if row['provider_id'] == 'freizeitkarte':
        from .provider_catalog import freizeitkarte_policy_country_codes
        codes = freizeitkarte_policy_country_codes(row.get('provider_region_id', ''), codes)
    if row.get('availability') == 'WITHHELD' or 'RU' in codes or ('UA' in codes and row.get('region', '').upper() == 'CRIMEA'):
        raise ValueError('acquisition_withheld')
    url, provider = row['source_url'], row['provider_id']
    opener = build_opener(_NoRedirect())
    from .collectors.freizeitkarte.range_zip import HTTPRangeFetcher
    fetcher = HTTPRangeFetcher(timeout_seconds=15, opener=opener)
    if provider == 'bbbike':
        from .bbbike import inspect_bbbike
        m = inspect_bbbike(url,row['provider_region_id'],row['map_type'])
        return dict(size_bytes=m.download_size_bytes, install_size_bytes=m.install_size_bytes,
                    install_payload_path=m.payload_path,source_proof=m.source_proof,source_updated_at=m.generated_at)
    if provider == 'maprando':
        from .maprando import inspect_maprando_img
        m=inspect_maprando_img(url, fetcher=HTTPRangeFetcher(timeout_seconds=15, max_response_bytes=512, opener=opener))
        if not m.identity_validated:
            raise ProviderCollectionError('MapRando header identity is unavailable')
        return dict(size_bytes=m.size_bytes,install_size_bytes=m.size_bytes)
    if provider == 'opentopomap' and row['kind']=='contours':
        from .contour_source import inspect_contour
        m=inspect_contour(url, opener=opener, fetcher=fetcher)
        return dict(size_bytes=m.download_size_bytes,install_size_bytes=m.install_size_bytes,
                    install_payload_path=m.payload_path,source_proof=m.source_proof,source_updated_at=m.source_updated_at)
    from .collectors.freizeitkarte.range_zip import ZipRangeInspector, HTTPRangeFetcher
    allowed={'freizeitkarte': {'download.freizeitkarte-osm.de','freizeitkarte-osm.de'},'opentopomap': {'garmin.opentopomap.org'}}
    parsed=urlparse(url)
    if (parsed.scheme!='https' or parsed.hostname not in allowed.get(provider,set()) or parsed.username or parsed.port or parsed.query or parsed.fragment
            or any(part in {'.', '..'} for part in unquote(parsed.path).split('/'))):
        raise ValueError('unreviewed_source')
    if provider == 'freizeitkarte' and not re.fullmatch(r'/garmin/[^/]+/[^/]+_gmapsupp\.img\.zip', unquote(parsed.path)):
        raise ValueError('unreviewed_source')
    if provider == 'opentopomap' and not re.fullmatch(r'/[a-z-]+/[a-z0-9-]+/otm-[a-z0-9-]+\.zip', parsed.path):
        raise ValueError('unreviewed_source')
    m=ZipRangeInspector(fetcher).inspect(url,expected_payload_path=row.get('install_payload_path') or ('gmapsupp.img' if provider=='freizeitkarte' else None))
    return dict(size_bytes=m.download_size_bytes,install_size_bytes=m.install_size_bytes,install_payload_path=m.payload_path)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Source redirect requires review')


def check_failure(error):
    cause, seen = error, set()
    while not isinstance(cause, HTTPError) and id(cause) not in seen:
        seen.add(id(cause))
        next_cause = cause.__cause__ or cause.__context__
        if next_cause is None:
            break
        cause = next_cause
    status=cause.code if isinstance(cause,HTTPError) else None
    if status==429:
        code, message, action='rate_limited','Provider rate limit reached.','Wait before checking again.'
    elif status:
        code, message, action='http_error',f'Provider returned HTTP {status}.','Open the source or refresh the catalog.'
    elif isinstance(cause,(TimeoutError,OSError)):
        code,message,action='network_error','The source could not be reached.','Check again later.'
    elif str(error)=='acquisition_withheld':
        code,message,action='policy_withheld','Acquisition is withheld by policy.','No network check is permitted.'
    else:
        code,message,action='validation_failed',str(error)[:240],'Review source metadata and the provider validator.'
    result = {'stage':'source_validation','status':'UNAVAILABLE','code':code,'message':message,'nextAction':action,'httpStatus':status,'checkedAt':datetime.now(timezone.utc).isoformat()}
    if status == 429:
        now = datetime.now(timezone.utc)
        retry = cause.headers.get('Retry-After', '') if cause.headers else ''
        try:
            until = now + timedelta(seconds=int(retry)) if retry.isdigit() else parsedate_to_datetime(retry)
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError, OverflowError):
            until = now + timedelta(minutes=15)
        result['retryNotBefore'] = max(until, now + timedelta(minutes=5)).isoformat()
    return result


def process_one(database):
    with database.connection() as c:
        job=c.execute("SELECT * FROM provider_recheck WHERE state='QUEUED' ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED").fetchone()
        if not job: return
        c.execute("UPDATE provider_recheck SET state='RUNNING' WHERE id=%s",(job['id'],))
    try:
        with provider_lock(database,job['provider_id']):
            ensure_retry_allowed(database, job['provider_id'])
            with database.connection() as c:
                rows=list(c.execute("""SELECT a.*,p.provider_id,p.provider_region_id,p.map_type,p.country_codes,p.region,p.availability,p.updated_at AS package_updated_at
                    FROM map_artifact a JOIN map_package p ON p.id=a.package_id
                    JOIN map_provider provider ON provider.id=p.provider_id
                    WHERE p.provider_id=%s AND p.availability <> 'RETIRED' AND provider.status <> 'RETIRED'
                    AND ((%s::text IS NOT NULL AND p.id=%s) OR (%s::text IS NULL AND a.validation_status IN ('FAILED','UNAVAILABLE')))
                    ORDER BY a.id""",(job['provider_id'],job['package_id'],job['package_id'],job['package_id'])).fetchall())
            results=[]
            package_versions = {}
            for row in rows:
                values={}
                try:
                    values=inspect_artifact(row)
                    result={'stage':'source_validation','status':'VALIDATED','code':None,'message':'Source validation passed.','nextAction':None,'checkedAt':datetime.now(timezone.utc).isoformat()}
                except Exception as error:
                    result=check_failure(error)
                result['artifactId']=row['id']
                result['packageId']=row['package_id']
                with database.connection() as c:
                    # A source revision changed outside this worker: do not publish stale evidence.
                    current=c.execute('SELECT a.source_url,a.updated_at,p.updated_at AS package_updated_at FROM map_artifact a JOIN map_package p ON p.id=a.package_id WHERE a.id=%s FOR UPDATE OF a,p',(row['id'],)).fetchone()
                    if not current or current['source_url']!=row['source_url'] or current['updated_at']!=row['updated_at'] or current.get('package_updated_at') != package_versions.get(row['package_id'], row.get('package_updated_at')):
                        result.update(status='STALE',message='Source changed. Check again.',nextAction='Check again.')
                    else:
                        c.execute('UPDATE map_artifact SET validation_status=%s,last_check=%s::jsonb,updated_at=now() WHERE id=%s',(result['status'],json.dumps(result),row['id']))
                        for key,value in values.items():
                            if key not in {'size_bytes','install_size_bytes','install_payload_path','source_proof','source_updated_at'}: raise ValueError('invalid_measurement')
                            c.execute(f"UPDATE map_artifact SET {key}=%s{'::jsonb' if key=='source_proof' else ''} WHERE id=%s",(json.dumps(value) if key=='source_proof' else value,row['id']))
                        c.execute("""UPDATE map_package p SET availability=CASE WHEN p.availability='WITHHELD' THEN 'WITHHELD' WHEN EXISTS(SELECT 1 FROM map_artifact a WHERE a.package_id=p.id AND a.required AND a.validation_status <> 'VALIDATED') THEN 'UNAVAILABLE' ELSE 'AVAILABLE' END,updated_at=now() WHERE id=%s""",(row['package_id'],))
                        c.execute("UPDATE provider_source SET last_checked_at=now(),updated_at=now() WHERE provider_id=%s AND source_type='DOWNLOAD' AND source_url=%s", (row['provider_id'], row['source_url']))
                        if row['provider_id'] == 'bbbike' and result['status'] == 'VALIDATED':
                            generated = values['source_updated_at']
                            c.execute('UPDATE map_package SET release=%s,version_label=%s,release_id=%s,generated_at=%s,source_updated_at=%s,updated_at=now() WHERE id=%s', (generated.date().isoformat(),generated.date().isoformat(),values['source_proof']['revision'],generated,generated,row['package_id']))
                        new_package = c.execute('SELECT updated_at FROM map_package WHERE id=%s', (row['package_id'],)).fetchone()
                        if new_package:
                            package_versions[row['package_id']] = new_package['updated_at']
                    c.execute('INSERT INTO provider_artifact_check(artifact_id,result) VALUES(%s,%s::jsonb)',(row['id'],json.dumps(result)))
                    results.append(result)
                    c.execute('UPDATE provider_recheck SET results=%s::jsonb WHERE id=%s',(json.dumps(results),job['id']))
                    if result.get('httpStatus') == 429:
                        # Persist the restriction in the same transaction as its
                        # evidence: a restart cannot lose the Retry-After window.
                        c.execute('UPDATE provider_recheck SET retry_not_before=%s WHERE id=%s', (result['retryNotBefore'],job['id']))
                if result.get('httpStatus') == 429:
                    break
            state='SUCCEEDED' if all(r['status']=='VALIDATED' for r in results) else 'FAILED'
            with database.connection() as c:
                c.execute('UPDATE provider_recheck SET state=%s,finished_at=now() WHERE id=%s',(state,job['id']))
    except ValueError as error:
        if str(error) == 'provider_busy':
            with database.connection() as c:
                c.execute("UPDATE provider_recheck SET state='QUEUED' WHERE id=%s", (job['id'],))
            return
        with database.connection() as c:
            c.execute("UPDATE provider_recheck SET state='INTERRUPTED',finished_at=now() WHERE id=%s", (job['id'],))
        logging.getLogger(__name__).exception('Provider recheck interrupted')
    except Exception:
        logging.getLogger(__name__).exception('Provider recheck interrupted')
        with database.connection() as c:
            c.execute("UPDATE provider_recheck SET state='INTERRUPTED',finished_at=now() WHERE id=%s",(job['id'],))


def run_worker(database, stop):
    # Only the worker holding this session lock may recover abandoned jobs.
    # A second scheduler cannot mark a live worker's jobs interrupted.
    with database.connection() as owner:
        if not owner.execute("SELECT pg_try_advisory_lock(hashtext('provider-recheck-worker')) AS acquired").fetchone()['acquired']:
            return
        try:
            with database.connection() as c:
                c.execute("UPDATE provider_recheck SET state='INTERRUPTED',finished_at=now() WHERE state='RUNNING'")
            while not stop.is_set():
                try:
                    process_one(database)
                except Exception:
                    logging.getLogger(__name__).exception('Provider recheck worker failed')
                stop.wait(5)
        finally:
            owner.execute("SELECT pg_advisory_unlock(hashtext('provider-recheck-worker'))")
