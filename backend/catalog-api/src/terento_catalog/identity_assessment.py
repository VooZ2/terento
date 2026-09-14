"""Deterministic evidence checks; never grants transport or publication permission."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

VERSION = 3

# Historical review statuses are not observations of a device model. Match
# only the legacy model field; original MTP/XML values remain evidence.
LEGACY_MODEL_PLACEHOLDERS = frozenset({
    'identity pending', 'identity unresolved',
    'identity not identifiable', 'identity resolved',
})

CORRECTABLE_FIELDS = {'model', 'variant', 'rawMTPModel', 'garminModelDescription',
                      'garminModelPartNumber', 'caseSizeMm', 'displayType', 'usbVendorID', 'usbProductID'}


def validate_correction(field: str, value: Any) -> None:
    if field not in CORRECTABLE_FIELDS:
        raise ValueError('unsupported identity source field')
    if value is None:
        return
    if field in {'caseSizeMm', 'usbVendorID', 'usbProductID'}:
        lower, upper = (1, 999) if field == 'caseSizeMm' else (0, 65535)
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError('invalid numeric identity source')
    elif (not isinstance(value, str) or not value.strip() or len(value) > 160
          or '/Users/' in value or 'file://' in value or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('invalid identity text')
    elif field == 'garminModelPartNumber' and re.fullmatch(r'[A-Za-z0-9-]{1,64}', value) is None:
        raise ValueError('invalid XML part number')


def apply_corrections(event: dict, corrections: list[dict]) -> dict:
    effective = dict(event)
    effective['_sourceOverrides'] = {}
    for correction in corrections:
        field = correction['field']
        effective[field] = correction['corrected_value']
        effective['_sourceOverrides'][field] = f"admin correction {correction['id']} ({field})"
    return effective


def normalized(value: Any) -> str:
    text = unicodedata.normalize('NFKD', str(value or '')).lower()
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def model_label(value: Any) -> str:
    text = normalized(value).removeprefix('garmin ')
    return re.split(r'\b(?:\d{2,3}\s*mm|amoled|microled|mip|solar|sapphire|inreach)\b', text)[0].strip()


def assess_identity(event: dict, devices: list[dict], mappings: list[dict]) -> dict:
    """Five checks per candidate, retaining ambiguity and shared provenance."""
    sources = event.get('_sourceOverrides', {})
    labels = [(sources.get(key, key), event.get(key))
              for key in ('rawMTPModel', 'garminModelDescription', 'model')
              if event.get(key) and not (
                  key == 'model' and normalized(event[key]) in LEGACY_MODEL_PLACEHOLDERS)]
    texts = [(key, normalized(value)) for key, value in labels]
    if event.get('variant'):
        texts.append((sources.get('variant', 'variant'), normalized(event['variant'])))
    sizes = [(key, int(match.group(1))) for key, text in texts
             for match in re.finditer(r'\b(\d{2,3})\s*mm\b', text)]
    if event.get('caseSizeMm') is not None:
        sizes.append((sources.get('caseSizeMm', 'caseSizeMm'), event['caseSizeMm']))
    screens = []
    for key, text in texts + [(sources.get('displayType', 'displayType'), normalized(event.get('displayType')))]:
        for token, screen in (('microled', 'MicroLED'), ('amoled', 'AMOLED'), ('mip', 'MIP')):
            if token in text.split():
                screens.append((key, screen))
    solar = any('solar' in text.split() for _, text in texts) or normalized(event.get('displayType')) == 'solar'
    inreach = any('inreach' in text.split() for _, text in texts)
    part_number = event.get('garminModelPartNumber')
    part_kind = 'RETAIL_SKU' if str(part_number or '').startswith('010-') else 'XML_PART_NUMBER'
    codes = {part_kind: part_number, 'USB': None}
    if isinstance(event.get('usbVendorID'), int) and isinstance(event.get('usbProductID'), int):
        codes['USB'] = f"{event['usbVendorID']:04x}:{event['usbProductID']:04x}"
    observed_mappings = {kind: [m for m in mappings if m['kind'] == kind and m['value'] == value]
                         for kind, value in codes.items()}
    matched = {kind: [m for m in group if m['status'] == 'APPROVED'] for kind, group in observed_mappings.items()}
    # Reviewing only one target of a shared code must not turn that code into
    # an apparently unique identifier. Pending alternative targets block
    # positive checks and derived properties until the whole scope is reviewed.
    incomplete = {kind: bool({m['device_model_id'] for m in observed_mappings[kind] if m['status'] == 'PENDING'}
                             - {m['device_model_id'] for m in group}) for kind, group in matched.items()}
    by_id = {d['id']: d for d in devices}
    # XML provides the primary model. Specifications may fill an unobserved
    # property only when every variant compatible with the observations agrees
    # and each fact has reviewed provenance. Shared USB codes cannot widen it.
    xml_label = model_label(event.get('garminModelDescription'))
    specification_targets = [d for d in devices if xml_label
        and model_label(d.get('model')) == xml_label
        and all(model_label(value) == xml_label for _, value in labels)
        and all(d.get('case_size_mm') == value for _, value in sizes)
        and all(d.get('screen_technology') == value for _, value in screens)
        and (not solar or d.get('solar') is True)
        and (not inreach or d.get('inreach') is True)]
    specification_facts = {}
    for field in ('screen_technology', 'solar', 'inreach'):
        values = {d.get(field) for d in specification_targets}
        if specification_targets and len(values) == 1 and None not in values and all(
                (d.get('specification_evidence') or {}).get(field, {}).get('source')
                for d in specification_targets):
            specification_facts[field] = [
                ('catalog specification: ' + d['specification_evidence'][field]['source'], d[field])
                for d in specification_targets]
    candidates = []
    for device in devices:
        device_id = device['id']
        expected = model_label(device.get('model'))
        label_matches = [(key, value) for key, value in labels if model_label(value) == expected]
        linked = any(any(m['device_model_id'] == device_id for m in group) for group in matched.values())
        if not label_matches and not linked and event.get('canonicalDeviceId') != device_id:
            continue
        checks = []

        def check(name, evidence, target, conflict=False):
            values = [value for _, value in evidence]
            state = 'CONFLICT' if conflict or (target is not None and any(v != target for v in values)) else (
                'MATCH' if target is not None and values and all(v == target for v in values) else 'MISSING')
            checks.append({'name': name, 'state': state, 'expected': target,
                           'evidence': [{'source': key, 'value': value} for key, value in evidence]})

        check('model', [(key, model_label(value)) for key, value in labels], expected)
        model_check = checks[-1]
        model_check['observedState'] = model_check['state']
        derived_size, derived_screen = list(sizes), list(screens)
        features = {'solar': [('model text', True)] if solar else [],
                    'inreach': [('model text', True)] if inreach else []}
        for kind, group in matched.items():
            if incomplete[kind]:
                continue
            # A shared mapping only proves a property when every mapped variant agrees.
            targets = [by_id.get(m['device_model_id'], {}) for m in group]
            for field, result in (('case_size_mm', derived_size), ('screen_technology', derived_screen),
                                  ('solar', features['solar']), ('inreach', features['inreach'])):
                values = {d.get(field) for d in targets}
                if targets and len(values) == 1 and None not in values:
                    result.append((kind + ':' + str(codes[kind]), next(iter(values))))
        if not derived_screen:
            derived_screen.extend(specification_facts.get('screen_technology', []))
        for feature in features:
            if not features[feature]:
                features[feature].extend(specification_facts.get(feature, []))
        # An absent word is never a negative feature observation. Keep the
        # feature checks inside the model row with their original provenance.
        model_check['features'] = []
        for feature, evidence in features.items():
            target = device.get(feature)
            values = [value for _, value in evidence]
            state = ('CONFLICT' if target is not None and any(v != target for v in values)
                     else 'MATCH' if target is not None and values else 'MISSING')
            model_check['features'].append({'name': feature, 'state': state, 'expected': target,
                'evidence': [{'source': key, 'value': value} for key, value in evidence]})
            if state == 'CONFLICT' or (state == 'MISSING' and model_check['state'] == 'MATCH'):
                model_check['state'] = state
        check('size', derived_size, device.get('case_size_mm'))
        check('screen', derived_screen, device.get('screen_technology'))
        checks[-1]['catalogSource'] = (device.get('specification_evidence') or {}).get('screen_technology')
        for name, kind in (('xmlPartNumber', part_kind), ('usb', 'USB')):
            group = matched[kind]
            matches = [m for m in group if m['device_model_id'] == device_id]
            checks.append({'name': name, 'state': 'MISSING' if incomplete[kind] else ('MATCH' if matches else ('CONFLICT' if group else 'MISSING')),
                           'pendingAlternativeTargets': incomplete[kind],
                           'value': codes[kind], 'codeKind': kind, 'evidence': [
                               {'source': m['source_url'], 'version': m['source_version'],
                                'value': m['value'], 'deviceId': m['device_model_id']} for m in group]})
        candidates.append({'deviceId': device_id, 'model': device['model'],
                           'checks': checks, 'conflict': any(c['state'] == 'CONFLICT' for c in checks)})
    possible = [c for c in candidates if not c['conflict']]
    exact = [c for c in possible if all(k['state'] == 'MATCH' for k in c['checks'])]
    resolved = exact[0]['deviceId'] if len(possible) == 1 and len(exact) == 1 else None
    return {'version': VERSION, 'reportedCanonicalDeviceId': event.get('canonicalDeviceId'), 'canonicalDeviceId': resolved,
            'state': 'RESOLVED' if resolved else 'UNRESOLVED', 'candidates': candidates}
