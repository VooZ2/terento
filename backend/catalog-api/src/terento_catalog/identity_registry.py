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
from .identity_assessment import assess_identity, apply_corrections, model_label, normalized
from .installation_policy import GENERATION_LABEL_BASE_MODEL_ALIASES

GARMIN_SOURCE = 'https://apps.garmin.com/api/appsLibraryExternalServices/api/asw/deviceTypes'
USB_SOURCE = 'https://github.com/libmtp/libmtp/blob/master/src/music-players.h'


# A source name that states a screen or power variant names only catalog rows
# of that variant: model_label() drops these words, so "fēnix 8 Solar (51mm)"
# and the 51 mm AMOLED row share the label "fenix 8". Garmin's solar models
# use MIP screens, so a solar name excludes AMOLED and MicroLED rows.
_SCREENS = (('AMOLED', re.compile(r'\bamoled\b')), ('MicroLED', re.compile(r'\bmicroled\b')))
_SOLAR = re.compile(r'\b(?:solar|dual power)\b')
_NO_WIFI = re.compile(r'\bno wi fi\b')


def _stated(text: str) -> set[str]:
    facts = {name for name, pattern in _SCREENS if pattern.search(text)}
    return facts | ({'SOLAR'} if _SOLAR.search(text) else set()) | ({'NO_WIFI'} if _NO_WIFI.search(text) else set())


def _device_facts(device: dict) -> tuple[str | None, bool | None, bool]:
    text = normalized(f"{device.get('model') or ''} {device.get('variant') or ''}")
    stated = _stated(text)
    screen = device.get('screen_technology', device.get('screenTechnology'))
    if screen not in {'AMOLED', 'MicroLED', 'MIP'}:
        screens = stated & {'AMOLED', 'MicroLED'}
        screen = next(iter(screens)) if len(screens) == 1 else None
    solar = True if device.get('solar') is True or 'SOLAR' in stated else device.get('solar')
    return screen, solar, 'NO_WIFI' in stated


def _variant_fits(device: dict, facts: set[str], elsewhere: set[str]) -> bool:
    screen, solar, no_wifi = _device_facts(device)
    if 'SOLAR' in facts and (solar is False or screen in {'AMOLED', 'MicroLED'}):
        return False
    if 'SOLAR' not in facts and solar is True and 'SOLAR_ONLY' in elsewhere:
        return False
    screens = facts & {'AMOLED', 'MicroLED'}
    if screens and (screen == 'MIP' or solar is True or (screen is not None and screen not in screens)):
        return False
    if not screens and screen in {'AMOLED', 'MicroLED'} and f'{screen}_ONLY' in elsewhere:
        return False
    if no_wifi != ('NO_WIFI' in facts) and 'NO_WIFI' in elsewhere:
        return False
    return True


def _usb_names(name: str) -> list[str]:
    # libmtp names several products of one USB code as "Fenix 7X/tactix 7/
    # Enduro 2". Split only full product names, never "Fenix 5/5S/5X Plus".
    parts = [part.strip() for part in name.split('/')]
    if len(parts) > 1 and all(re.fullmatch(r'[A-Za-z]{3,} \S.*', part) for part in parts):
        return parts
    return [name]


def _source_label(name: str, aliases: dict[str, str]) -> str:
    label = _NO_WIFI.sub(' ', model_label(name)).strip()
    return aliases.get(label, label)


def _name_facts(names: list[str], aliases: dict[str, str]) -> dict[str, set[str]]:
    # Each product name of a code is its own variant: "Instinct Crossover" and
    # "Instinct Crossover Dual Power" share one code. Bare tags such as "AMOLED"
    # or "Solar" carry no model name and describe every name of the code.
    tags = set().union(*(_stated(normalized(name)) for name in names if not _source_label(name, aliases)))
    return {name: _stated(normalized(name)) | tags for name in names}


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
            observations.append(('USB', f'091e:{int(pid, 16):04x}', _usb_names(name), USB_SOURCE))
    # The reviewed generation alias ("epix Pro" is the catalog "epix Pro (Gen 2)")
    # applies as in identity assessment: never over a real catalog name.
    catalog_labels = {model_label(device['model']) for device in devices}
    aliases = {alias: target for alias, target in GENERATION_LABEL_BASE_MODEL_ALIASES.items() if alias not in catalog_labels}
    # Variants that some code of the same source states per model name. A code
    # that states no Solar or No Wi-Fi skips the rows another code names that
    # way: Garmin lists "fenix 9 Pro - 47 mm" next to "fenix 9 Pro - Solar 47 mm".
    stated_elsewhere: dict[str, set[str]] = {}
    for _, _, names, _ in observations:
        by_label: dict[str, list[set[str]]] = {}
        for name, facts in _name_facts(names, aliases).items():
            by_label.setdefault(_source_label(name, aliases), []).append(facts)
        for label, facts in by_label.items():
            stated = stated_elsewhere.setdefault(label, set())
            stated.update(*facts)
            # Only a code whose every name states Solar or a screen sets those
            # rows apart; "fēnix 7X Pro" and its Solar Edition share one code.
            stated.update(f'{fact}_ONLY' for fact in set.intersection(*facts) - {'NO_WIFI'})
    # A sibling's variant sets rows apart only from other rows of the model:
    # quatix 7X exists only as a Solar row, so a plain "quatix 7X" still names it.
    for label, stated in stated_elsewhere.items():
        facts = [_device_facts(device) for device in devices if model_label(device['model']) == label]
        if all(solar is True for _, solar, _ in facts):
            stated.discard('SOLAR_ONLY')
        for screen in ('AMOLED', 'MicroLED'):
            if all(row_screen == screen for row_screen, _, _ in facts):
                stated.discard(f'{screen}_ONLY')
    sized_rows = {(model_label(device['model']), device.get('case_size_mm', device.get('caseSizeMm'))) for device in devices}
    rows = {}
    for code_kind, value, names, source in observations:
        name_facts = _name_facts(names, aliases)
        for device in devices:
            # Explicit source sizes narrow candidates; an omitted size or
            # feature still proves nothing. Keep original names for review.
            matching_names = []
            for name in names:
                label = _source_label(name, aliases)
                if label != model_label(device['model']):
                    continue
                sizes = {int(n) for n in re.findall(r'\b(\d{2,3})\s*mm\b', name, re.IGNORECASE)}
                size = device.get('case_size_mm', device.get('caseSizeMm'))
                if sizes and size is not None and size not in sizes:
                    continue
                # A stated size names the sized rows, not the unsized legacy
                # row of the same model (epix Pro (Gen 2) next to 42/47/51 mm).
                if sizes and size is None and any((label, stated_size) in sized_rows for stated_size in sizes):
                    continue
                if not _variant_fits(device, name_facts[name], stated_elsewhere.get(label, set())):
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
    auto = sub.add_parser('auto-resolve')
    auto.add_argument('--apply', action='store_true', help='Assign; without it only counts')
    args = parser.parse_args()
    settings = Settings.from_env()
    database = Database(settings.database_url, connect_timeout_seconds=settings.database_connect_timeout_seconds)
    if args.command == 'auto-resolve':
        print(json.dumps({'readOnly': not args.apply, **database.auto_resolve_pending_identities(apply=args.apply)}))
        return
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
                    database.enrich_device_specifications(connection, device['id'], specs, url, version, specs.get('retail_skus', []),
                                                           evidence_fields={'map_capable': specs.get('map_evidence_row')})
            print(json.dumps({'readOnly': not args.apply, 'devices': report}, ensure_ascii=False, indent=2))
            return
        if args.command == 'import':
            rows = prepare_mappings(args.kind, args.snapshot.read_text(), devices)
            if args.apply:
                connection.execute("SELECT pg_advisory_xact_lock(hashtext('device_identity_mapping'))")
                for row in rows:
                    # A newer snapshot of a link already stored adds no second row.
                    connection.execute('INSERT INTO device_identity_mapping (kind,value,device_model_id,source_url,source_version,source_names) SELECT %(kind)s,%(value)s,%(device_model_id)s,%(source_url)s,%(source_version)s,%(source_names)s::jsonb WHERE NOT EXISTS (SELECT 1 FROM device_identity_mapping m WHERE m.kind=%(kind)s AND m.value=%(value)s AND m.device_model_id=%(device_model_id)s)', dict(row, source_names=json.dumps(row['source_names'])))
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
