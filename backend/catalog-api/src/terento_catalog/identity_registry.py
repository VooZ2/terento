"""Reviewable identity imports and read-only historical assignment audits.

No network requests during API handling; source snapshots are supplied by the
operator and identified by their SHA-256. Imports never approve themselves.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from .config import Settings
from .db import Database
from .identity_assessment import assess_identity, apply_corrections, model_label

GARMIN_SOURCE = 'https://apps.garmin.com/api/appsLibraryExternalServices/api/asw/deviceTypes'
USB_SOURCE = 'https://github.com/libmtp/libmtp/blob/master/src/music-players.h'


def prepare_mappings(kind: str, content: str, devices: list[dict]) -> list[dict]:
    version = hashlib.sha256(content.encode()).hexdigest()
    observations = []
    if kind == 'garmin':
        for row in json.loads(content):
            code = row.get('partNumber', '')
            if not re.fullmatch(r'006-[A-Za-z0-9-]{1,60}', code):
                continue
            observations.append(('XML_PART_NUMBER', code, [row.get('name', ''), *row.get('additionalNames', [])], GARMIN_SOURCE))
    else:
        for name, pid in re.findall(r'\{\s*"Garmin",\s*0x091e,\s*"([^"]+)",\s*(0x[0-9a-fA-F]+)', content):
            observations.append(('USB', f'091e:{int(pid, 16):04x}', [name], USB_SOURCE))
    rows = {}
    for code_kind, value, names, source in observations:
        for device in devices:
            # Explicit source sizes narrow candidates; an omitted size or
            # feature still proves nothing. Keep original names for review.
            matching_names = []
            for name in names:
                if model_label(name) != model_label(device['model']):
                    continue
                sizes = {int(n) for n in re.findall(r'\b(\d{2,3})\s*mm\b', name, re.IGNORECASE)}
                size = device.get('case_size_mm', device.get('caseSizeMm'))
                if sizes and size is not None and size not in sizes:
                    continue
                matching_names.append(name)
            if matching_names:
                key = (code_kind, value, device['id'])
                rows[key] = dict(kind=code_kind, value=value, device_model_id=device['id'],
                                 source_url=source, source_version=version,
                                 source_names=matching_names, status='PENDING')
    return sorted(rows.values(), key=lambda r: (r['kind'], r['value'], r['device_model_id']))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    source = sub.add_parser('import')
    source.add_argument('kind', choices=['garmin', 'usb'])
    source.add_argument('snapshot', type=Path)
    source.add_argument('--apply', action='store_true', help='Stage candidates; never approves them')
    review = sub.add_parser('review')
    review.add_argument('mapping_id', type=int)
    review.add_argument('--status', required=True, choices=['APPROVED', 'REJECTED'])
    review.add_argument('--reason', required=True)
    review.add_argument('--admin-id', required=True, type=int)
    enrich = sub.add_parser('specifications')
    enrich.add_argument('snapshot_directory', type=Path)
    enrich.add_argument('--apply', action='store_true', help='Enrich exact existing product URLs; never reassigns events')
    sub.add_parser('audit')
    args = parser.parse_args()
    settings = Settings.from_env()
    database = Database(settings.database_url, connect_timeout_seconds=settings.database_connect_timeout_seconds)
    if args.command == 'review':
        if not database.review_identity_mapping(args.mapping_id, args.status, args.reason, args.admin_id):
            parser.error('mapping not found')
        print(json.dumps({'mappingId': args.mapping_id, 'status': args.status}))
        return
    with database.connection() as connection:
        devices = list(connection.execute('SELECT * FROM device_model').fetchall())
        if args.command == 'specifications':
            from .collectors.garmin.specifications import parse_specifications
            report = []
            for device in devices:
                url = device.get('product_url') or ''
                match = re.fullmatch(r'https://www\.garmin\.com/en-US/p/(\d+)/', url)
                if not match:
                    report.append({'deviceId': device['id'], 'status': 'NO_EXACT_PRODUCT_SOURCE'})
                    continue
                path = args.snapshot_directory / (match[1] + '.html')
                if not path.is_file():
                    report.append({'deviceId': device['id'], 'status': 'SOURCE_NOT_CAPTURED'})
                    continue
                content = path.read_text()
                specs = parse_specifications(content, match[1])
                version = hashlib.sha256(path.read_bytes()).hexdigest()
                report.append({'deviceId': device['id'], 'source': url, 'version': version, 'specifications': specs})
                if args.apply:
                    database.enrich_device_specifications(connection, device['id'], specs, url, version, specs.get('retail_skus', []))
            print(json.dumps({'readOnly': not args.apply, 'devices': report}, ensure_ascii=False, indent=2))
            return
        if args.command == 'import':
            rows = prepare_mappings(args.kind, args.snapshot.read_text(), devices)
            if args.apply:
                for row in rows:
                    connection.execute('INSERT INTO device_identity_mapping (kind,value,device_model_id,source_url,source_version,source_names) VALUES (%(kind)s,%(value)s,%(device_model_id)s,%(source_url)s,%(source_version)s,%(source_names)s::jsonb) ON CONFLICT DO NOTHING', dict(row, source_names=json.dumps(row['source_names'])))
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return
        mappings = list(connection.execute('SELECT * FROM device_identity_mapping').fetchall())
        events = connection.execute('SELECT * FROM compatibility_evidence_event WHERE is_local_test IS NOT TRUE ORDER BY occurred_at,event_id').fetchall()
        corrections = list(connection.execute('SELECT * FROM device_identity_source_correction ORDER BY id').fetchall())
        print(json.dumps(build_assignment_audit(events, devices, mappings, corrections), ensure_ascii=False, indent=2))


def build_assignment_audit(events: list[dict], devices: list[dict], mappings: list[dict], corrections: list[dict]) -> dict:
    report = []
    for row in events:
        effective = apply_corrections(Database._identity_event(row), [c for c in corrections if c['event_id'] == row['event_id']])
        assessment = assess_identity(effective, devices, mappings)
        assigned = row.get('canonical_device_model_id')
        candidate = next((c for c in assessment['candidates'] if c['deviceId'] == assigned), None)
        report.append({'eventId': str(row['event_id']), 'assignedDeviceId': assigned,
                       'proposedDeviceId': assessment['canonicalDeviceId'],
                       'outcome': row['phase_outcome'],
                       'classification': 'CONFLICT' if candidate and candidate['conflict'] else (
                           'SUPPORTED' if assigned and assessment['canonicalDeviceId'] == assigned else 'INSUFFICIENT'),
                       'assessment': assessment})
    from collections import Counter
    old_counts, strict_counts = Counter(), Counter()
    for row, finding in zip(events, report):
        if row['phase_outcome'] == 'SUCCEEDED' and row['automatic_finishing_result'] == 'VERIFIED' and row['diagnostic_status'] == 'ACTIVE':
            if finding['assignedDeviceId']:
                old_counts[finding['assignedDeviceId']] += 1
            if finding['proposedDeviceId']:
                strict_counts[finding['proposedDeviceId']] += 1
    from .compatibility_status import calculate_compatibility_status
    impact = []
    by_id = {d['id']: d for d in devices}
    for device_id in sorted(old_counts.keys() | strict_counts.keys()):
        capable = by_id[device_id].get('map_capable') is True
        before, after = old_counts[device_id], strict_counts[device_id]
        impact.append({'deviceId': device_id, 'currentSuccessfulCount': before, 'strictAutomaticOnlyCount': after,
            'currentEvidenceStatus': calculate_compatibility_status(successful_install_count=before, recognized_map_capable_evidence=capable),
            'strictAutomaticOnlyStatus': calculate_compatibility_status(successful_install_count=after, recognized_map_capable_evidence=capable)})
    return {'readOnly': True, 'approvalRequiredBeforeReassignment': True,
        'scenario': 'Strict automatic evidence only; manual evidence may retain assignments after owner review. Publication approvals are not changed.',
        'summary': dict(Counter(r['classification'] for r in report)), 'counterImpact': impact, 'events': report}


if __name__ == '__main__':
    main()
