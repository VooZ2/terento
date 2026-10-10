"""Synthetic install/update review fixtures. No DB, telemetry or external actions.

PYTHONPATH=src python3.13 tests/admin_diagnostic_parity_preview.py /tmp/admin-parity
Serve the directory locally and run admin_diagnostic_parity_browser.cjs.
"""
from pathlib import Path
from terento_catalog.admin import ADMIN_STYLES, ADMIN_STYLESHEET_PATH, diagnostics_page, device_detail_page, _admin_device_payload
from terento_catalog.update_diagnostics import update_diagnostics_page

DEVICE = 'fenix-8-51-amoled'
INSTALL = '11111111-1111-4111-8111-111111111111'
UPDATE = '22222222-2222-4222-8222-222222222222'
OPERATION = '33333333-3333-4333-8333-333333333333'
NOW = '2026-10-02T18:02:00Z'


def build(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    user = {'username': 'Diagnostic parity preview'}
    identity = 'fēnix 8 · 51 mm, AMOLED'
    device_row = {'id': DEVICE, 'device_id': DEVICE, 'model': 'fēnix 8', 'variant': '51 mm, AMOLED',
        'case_size_mm': 51, 'screen_technology': 'AMOLED', 'family_name': 'fēnix',
        'map_capable': True, 'active': True, 'support_status': 'SUPPORTED',
        'install_authorization': 'APPROVED', 'attempted_install_count': 12,
        'successful_install_count': 11, 'failed_install_count': 1, 'usb_identities': []}
    install = {'event_id': INSTALL, 'operation_id': OPERATION, 'operation_key': OPERATION,
        'map_result_index': 0, 'canonical_device_model_id': DEVICE, 'compatibility_identity': identity,
        'model': 'fēnix 8', 'variant': '51 mm, AMOLED', 'provider': 'bbbike', 'region': 'FRA',
        'phase_outcome': 'FAILED', 'diagnostic_status': 'ACTIVE', 'diagnostic_workflow_status': 'OPEN',
        'error_category': 'TRANSFER_FAILED', 'write_started': True, 'failure_stage': 'verify',
        'failure_code': 'INSTALL_FAILED_HASH_MISMATCH', 'occurred_at': NOW,
        'terento_version': 'Preview', 'app_build': '38'}
    update = {'event_id': UPDATE, 'operation_id': OPERATION, 'canonical_device_model_id': DEVICE,
        'device': device_row, 'provider': 'bbbike', 'region': 'FRA', 'outcome': 'FAILED',
        'occurred_at': NOW, 'diagnostic_status': 'ACTIVE', 'diagnostic_workflow_status': 'OPEN',
        'payload': {'model': 'fēnix 8', 'variant': '51 mm, AMOLED', 'compatibilityIdentity': identity,
            'provider': 'bbbike', 'region': 'FRA', 'phaseOutcome': 'FAILED', 'operationKind': 'update',
            'operationId': OPERATION, 'terentoVersion': 'Preview', 'appBuild': '38',
            'failureCode': 'UPDATE_FAILED_HASH_MISMATCH', 'failureStage': 'verify',
            'writeStarted': True, 'oldMapPreserved': True, 'cleanupAttempted': True, 'cleanupSucceeded': True,
            'automaticFinishingResult': 'FAILED', 'firmwareVersion': '19.10', 'transport': 'MTP',
            'failureContext': {'boundary': 'readback', 'classificationSource': 'native',
                'devicePresence': 'present', 'nativeCodeNamespace': 'terento_file_range', 'nativeResultCode': -1}}}
    pages = {}
    for state in ['open', 'linked', 'resolved']:
        changes = {'linked_github_issue': '#325', 'diagnostic_workflow_status': 'IN_PROGRESS'} if state == 'linked' else {}
        if state == 'resolved':
            changes = {'diagnostic_status': 'RESOLVED', 'resolution_reason': 'FIXED', 'resolution_code': 'FIXED',
                'resolution_note': 'Synthetic fixture review completed.', 'resolved_at': NOW, 'resolved_by': 1}
        install_record = {**install, **changes}
        update_record = {**update, **changes}
        pages['install-' + state] = diagnostics_page([device_row], user, 'fixture', identity=identity,
            canonical_device_model_id=DEVICE, identity_devices=[device_row],
            operations=[] if state == 'resolved' else [install_record],
            resolved_operations=[install_record] if state == 'resolved' else [])
        pages['update-' + state] = update_diagnostics_page({'detail': update_record}, user, 'fixture')
    ambiguous_install = {**install, 'canonical_device_model_id': None,
        'identity_resolution_state': 'UNRESOLVED', 'identity_recommendation': None,
        'compatibility_identity': 'fēnix 8', 'variant': None}
    second_device = {**device_row, 'id': 'fenix-8-47-amoled', 'device_id': 'fenix-8-47-amoled',
        'variant': '47 mm, AMOLED', 'case_size_mm': 47}
    pages['install-ambiguous'] = diagnostics_page([], user, 'fixture', identity='fēnix 8',
        operations=[ambiguous_install], identity_devices=[device_row, second_device], unresolved_only=True)
    unknown = {**update, 'canonical_device_model_id': None, 'device': None,
        'identity_assessment': {'state': 'UNRESOLVED'}}
    pages['update-unknown'] = update_diagnostics_page({'detail': unknown}, user, 'fixture')
    rows = [{**update, 'event_id': '55555555-5555-4555-8555-555555555555', 'outcome': 'SUCCEEDED'}, update,
        {**update, 'event_id': '44444444-4444-4444-8444-444444444444', 'outcome': 'NOT_STARTED'}]
    summary = {'successfulUpdateCount': 7, 'failedUpdateCount': 2, 'attemptedUpdateCount': 9, 'notStartedCount': 1}
    device = _admin_device_payload([device_row], None)['devices'][0]
    device['update_statistics'] = summary
    args = {'operations': [install], 'identity_devices': [device_row]}
    args['update_history'] = {'summary': summary, 'rows': rows, 'offset': 0, 'has_more': False}
    pages['device-updates'] = device_detail_page(device, user, 'fixture', **args)
    for name, body in pages.items():
        (root / (name + '.html')).write_bytes(body)
    # Signed-in pages link the content-versioned Admin stylesheet.
    (root / ADMIN_STYLESHEET_PATH.lstrip('/')).parent.mkdir(parents=True, exist_ok=True)
    (root / ADMIN_STYLESHEET_PATH.lstrip('/')).write_text(ADMIN_STYLES, encoding='utf-8')
    return pages


if __name__ == '__main__':
    import sys
    build(sys.argv[1])
