"""Closed, nonrecursive installation failure observations; never raw native data."""
from typing import Any

BOUNDARIES = (
    'initial_snapshot', 'initial_inventory', 'prewrite_inventory', 'prewrite_protection',
    'write', 'readback', 'postwrite_inventory', 'postwrite_snapshot', 'target_validation',
    'postwrite_protection', 'cleanup', 'manifest', 'source_validation_complete', 'preflight_policy_passed',
)
CONTEXT_ENUMS = {
    'boundary': BOUNDARIES, 'lastSuccessfulBoundary': BOUNDARIES,
    'classificationSource': ('native', 'derived'),
    'devicePresence': ('unknown', 'present', 'absent'),
    'operation': ('snapshot', 'inventory', 'file_prefix', 'file_range', 'write', 'readback', 'cleanup', 'manifest', 'protection_check'),
    'executionMode': ('in_process', 'worker'),
    'resultKind': ('native_error', 'timeout', 'cancelled', 'process_launch_error', 'process_exit', 'request_io_error', 'response_io_error', 'decode_error', 'invalid_response', 'app_error', 'protection_failed'),
    'nativeCategory': ('detection', 'session_open', 'storage_read', 'inventory_read', 'object_read', 'allocation', 'invalid_argument', 'unspecified'),
    'nativeCodeNamespace': ('terento_snapshot', 'terento_inventory', 'terento_file_prefix', 'terento_file_range'),
    'componentKind': ('main', 'contours'),
}
PROTECTION_ENUMS = {
    'protectionBoundary': ('pre-write', 'post-write'),
    'protectionReason': ('target-present-before-write', 'non-target-object-added', 'preexisting-object-removed', 'preexisting-object-changed', 'inventory-ambiguous', 'target-missing', 'target-duplicate', 'target-invalid', 'target-filename-mismatch', 'target-size-mismatch'),
}
COUNT_FIELDS = ('beforeObjectCount', 'afterObjectCount', 'addedObjectCount', 'removedObjectCount', 'changedObjectCount')
TARGET_FIELDS = ('targetPresent', 'targetUnique', 'targetKindMatches', 'targetFilenameMatches', 'targetSizeMatches', 'targetPathMatches', 'targetItemIDMatches')
BOUNDARY_STAGES = {
    'initial_snapshot': 'preflight', 'initial_inventory': 'preflight',
    'prewrite_inventory': 'preflight', 'prewrite_protection': 'preflight',
    'write': 'write', 'readback': 'verify', 'postwrite_inventory': 'verify',
    'postwrite_snapshot': 'verify', 'target_validation': 'verify',
    'postwrite_protection': 'verify', 'cleanup': 'cleanup', 'manifest': 'manifest',
    'source_validation_complete': 'source-validation', 'preflight_policy_passed': 'preflight',
}


def _integer(value: Any, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def validate_context(context: Any) -> None:
    allowed = set(CONTEXT_ENUMS) | {'nativeResultCode', 'retryCount', 'protection'}
    if not isinstance(context, dict) or set(context) - allowed:
        raise ValueError('invalid_failure_context_fields')
    if not {'boundary', 'classificationSource', 'devicePresence'} <= set(context):
        raise ValueError('missing_failure_context_fields')
    for key, values in CONTEXT_ENUMS.items():
        if key in context and context[key] not in values:
            raise ValueError('invalid_failure_context_enum')
    if ('nativeCodeNamespace' in context) != ('nativeResultCode' in context):
        raise ValueError('missing_native_code_pair')
    if 'nativeResultCode' in context and not _integer(context['nativeResultCode'], -(2**31), 2**31 - 1):
        raise ValueError('invalid_native_result_code')
    if 'retryCount' in context and not _integer(context['retryCount'], 0, 255):
        raise ValueError('invalid_retry_count')
    if 'protection' not in context:
        return
    protection = context['protection']
    allowed = set(PROTECTION_ENUMS) | set(COUNT_FIELDS) | set(TARGET_FIELDS) | {'stableIdentityComparisonVersion'}
    if not isinstance(protection, dict) or set(protection) - allowed:
        raise ValueError('invalid_protection_fields')
    if not set(PROTECTION_ENUMS) <= set(protection):
        raise ValueError('missing_protection_fields')
    for key, values in PROTECTION_ENUMS.items():
        if protection[key] not in values:
            raise ValueError('invalid_protection_enum')
    for key in COUNT_FIELDS:
        if key in protection and not _integer(protection[key], 0, 16384):
            raise ValueError('invalid_protection_count')
    for key in TARGET_FIELDS:
        if key in protection and protection[key] is not None and type(protection[key]) is not bool:
            raise ValueError('invalid_protection_target')
    if 'stableIdentityComparisonVersion' in protection and not _integer(protection['stableIdentityComparisonVersion'], 1, 2):
        raise ValueError('invalid_comparison_version')
    expected = {'prewrite_protection': 'pre-write', 'postwrite_protection': 'post-write', 'target_validation': 'post-write'}.get(context['boundary'])
    if expected is None or protection['protectionBoundary'] != expected:
        raise ValueError('inconsistent_protection_boundary')
    reason = protection['protectionReason']
    if reason == 'target-present-before-write':
        allowed_boundaries = ('prewrite_protection',)
    elif reason.startswith('target-'):
        allowed_boundaries = ('target_validation', 'postwrite_protection')
    else:
        allowed_boundaries = ('prewrite_protection', 'postwrite_protection')
    if context['boundary'] not in allowed_boundaries:
        raise ValueError('inconsistent_protection_reason_boundary')
    expected_facts = {
        'target-present-before-write': {'targetPresent': True},
        'target-missing': {'targetPresent': False},
        'target-duplicate': {'targetPresent': True, 'targetUnique': False},
        'target-filename-mismatch': {'targetFilenameMatches': False},
        'target-size-mismatch': {'targetSizeMatches': False},
    }.get(protection['protectionReason'], {})
    if any(protection.get(key) is not None and protection[key] is not value for key, value in expected_facts.items()):
        raise ValueError('inconsistent_protection_reason')


def validate_event_contexts(event: dict[str, Any]) -> None:
    for key in ('failureContext', 'originalFailureContext'):
        if key not in event:
            continue
        if event['schemaVersion'] != 4:
            raise ValueError('failure_context_requires_v4')
        context = event[key]
        if context is None:
            continue
        validate_context(context)
        if event['phaseOutcome'] == 'NOT_STARTED':
            raise ValueError('inconsistent_not_started_context')
        if context.get('componentKind') == 'contours' and (
            event.get('optionalComponentSelected') is not True
            or event.get('optionalComponentOutcome') != 'FAILED'
        ):
            raise ValueError('inconsistent_context_component')
        if event['phaseOutcome'] == 'SUCCEEDED' and context.get('componentKind') != 'contours':
            raise ValueError('inconsistent_success_context')
        if key == 'failureContext':
            if context['boundary'] == 'cleanup' and event.get('cleanupAttempted') is not True:
                raise ValueError('cleanup_context_requires_attempt')
            stage = event.get('optionalComponentFailureStage') if context.get('componentKind') == 'contours' else event.get('failureStage')
            if stage is not None and stage != BOUNDARY_STAGES[context['boundary']]:
                raise ValueError('inconsistent_context_stage')
    if event.get('originalFailureContext') is not None:
        context = event.get('failureContext') or {}
        stage = event.get('optionalComponentFailureStage') if context.get('componentKind') == 'contours' else event.get('failureStage')
        if context.get('boundary') != 'cleanup' or stage != 'cleanup':
            raise ValueError('original_context_requires_cleanup')
        original_component = event['originalFailureContext'].get('componentKind')
        if original_component is not None and context.get('componentKind') is not None and original_component != context['componentKind']:
            raise ValueError('inconsistent_original_component')
