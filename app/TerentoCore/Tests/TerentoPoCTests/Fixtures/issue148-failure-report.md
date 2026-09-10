## Summary

- Result: FAILED
- Failure stage: cleanup
- Error category: transport
- Error code: INSTALL_FAILED_CLEANUP

## Device

- Model: fēnix 8
- Variant: 47 mm, AMOLED
- Family: fēnix
- Firmware: 2331
- Raw MTP model: fenix 8 - 47mm

## Operation

- Operation: Map installation
- Provider: MapRando
- Region: lituanie
- Map version: 2026-09-02
- App version: 1.0.0-beta.11-local
- Build: 19-local
- macOS: Version 26.6.2 (Build 25G83)
- Timestamp: 2026-09-10T19:44:45Z

## Map packages

- MapRando / lituanie: release=2026-09-02, planned installed bytes=182239232

## Failure details

- Write started: Yes
- Transfer progress: 100%
- Object created: Yes
- Cleanup attempted: Yes
- Cleanup succeeded: No
- Transport: MTP
- Detail: INSTALL_FAILED_CLEANUP — Installation failed and a partial map may still remain on the Garmin device. Terento did not retry or remove it automatically. Reconnect the watch and refresh its maps before any further action.

## Verification details

- Original failure: INSTALL_FAILED_DEVICE_DISCONNECTED
- Cleanup failure: INSTALL_FAILED_CLEANUP
- Transport classification (mapped; native return codes are in the trace): DELETE_FAILED
- Failed component: main
- Validated source bytes: 182239232
- Reported remote bytes (not proof of content verification): 182239232
- Transferred bytes: 182239232
- Elapsed at failure (ms): 273621
- Verified sample bytes: Unavailable
- Planned samples: Unavailable
- Matched samples: Unavailable


## Finishing diagnostics

Fixed-field diagnostic sequence; raw native return codes use rc. Swift elapsed values are seconds except installation_failure, which uses milliseconds. target_matches detail is the match count; target_size detail is the reported size, with expected bytes in offset. Missing events are unavailable evidence, not success.

FINISH_TRACE native event=read_failed offset=1572864 rc=-1 detail=0 last_verified_end=1572864 verified_bytes=1572864
FINISH_TRACE native event=read_error_code offset=1572864 rc=2 detail=65536 last_verified_end=1572864 verified_bytes=1572864
FINISH_TRACE native event=read_ptp_response offset=1572864 rc=767 detail=65536 last_verified_end=1572864 verified_bytes=1572864
FINISH_TRACE native event=retry_close_begin offset=1572864 rc=0 detail=1 last_verified_end=1572864 verified_bytes=1572864
FINISH_TRACE native event=retry_close_returned offset=1572864 rc=0 detail=1 last_verified_end=1572864 verified_bytes=1572864
FINISH_TRACE native event=open_begin offset=1572864 rc=0 detail=1 last_verified_end=1572864 verified_bytes=1572864
FINISH_TRACE native event=read_checkpoint offset=1114112 rc=0 detail=1114112 last_verified_end=1114112 verified_bytes=1114112
FINISH_TRACE swift event=installation_begin
FINISH_TRACE swift event=operation_begin operation=inventory
FINISH_TRACE swift event=worker_started timeout=45.0
FINISH_TRACE swift event=worker_exited status=0 reason=1
FINISH_TRACE swift event=worker_operation_begin operation=inventory
FINISH_TRACE swift event=operation_complete operation=inventory elapsed=1.0159572499687783
FINISH_TRACE swift event=readback_attempt worker=false attempt=1 delay=0.0
FINISH_TRACE swift event=operation_begin operation=samples
FINISH_TRACE swift event=worker_operation_failed error=operationFailed
FINISH_TRACE swift event=operation_failed operation=samples elapsed=68.78135900001507 error=operationFailed
FINISH_TRACE swift event=readback_failed worker=false attempt=2 error=operationFailed
FINISH_TRACE swift event=readback_attempt worker=false attempt=3 delay=2.0
FINISH_TRACE swift event=operation_begin operation=samples
FINISH_TRACE swift event=worker_started timeout=120.0
FINISH_TRACE swift event=worker_exited status=0 reason=1
FINISH_TRACE swift event=worker_operation_begin operation=samples
FINISH_TRACE swift event=readback_attempt worker=true attempt=1 delay=0.0
FINISH_TRACE native event=verify_begin offset=0 rc=0 detail=7 last_verified_end=0 verified_bytes=0
FINISH_TRACE native event=open_begin offset=0 rc=0 detail=0 last_verified_end=0 verified_bytes=0
FINISH_TRACE native event=open_end offset=0 rc=-8 detail=0 last_verified_end=0 verified_bytes=0
FINISH_TRACE native event=verify_result offset=0 rc=-8 detail=0 last_verified_end=0 verified_bytes=0
FINISH_TRACE swift event=readback_failed worker=true attempt=1 error=operationFailed
FINISH_TRACE swift event=readback_attempt worker=true attempt=2 delay=1.0
FINISH_TRACE native event=verify_begin offset=0 rc=0 detail=7 last_verified_end=0 verified_bytes=0
FINISH_TRACE native event=open_begin offset=0 rc=0 detail=0 last_verified_end=0 verified_bytes=0
FINISH_TRACE native event=open_end offset=0 rc=-8 detail=0 last_verified_end=0 verified_bytes=0
FINISH_TRACE native event=verify_result offset=0 rc=-8 detail=0 last_verified_end=0 verified_bytes=0
FINISH_TRACE swift event=readback_failed worker=true attempt=2 error=operationFailed
FINISH_TRACE swift event=readback_attempt worker=true attempt=3 delay=2.0
FINISH_TRACE native event=verify_begin offset=0 rc=0 detail=7 last_verified_end=0 verified_bytes=0
FINISH_TRACE native event=open_begin offset=0 rc=0 detail=0 last_verified_end=0 verified_bytes=0
FINISH_TRACE native event=open_end offset=0 rc=-8 detail=0 last_verified_end=0 verified_bytes=0
FINISH_TRACE native event=verify_result offset=0 rc=-8 detail=0 last_verified_end=0 verified_bytes=0
FINISH_TRACE swift event=readback_failed worker=true attempt=3 error=operationFailed
FINISH_TRACE swift event=worker_operation_failed error=operationFailed
FINISH_TRACE swift event=operation_failed operation=samples elapsed=68.82535641669529 error=operationFailed
FINISH_TRACE swift event=readback_failed worker=false attempt=3 error=operationFailed
FINISH_TRACE swift event=installation_failure elapsed=273621
FINISH_TRACE swift event=operation_begin operation=cleanup
FINISH_TRACE swift event=worker_started timeout=45.0
FINISH_TRACE swift event=worker_deadline
FINISH_TRACE swift event=worker_operation_begin operation=cleanup
FINISH_TRACE swift event=operation_worker_failed operation=cleanup elapsed=45.110795083339326
FINISH_TRACE swift event=cleanup_result attempt=1 succeeded=0

## Reference

- Diagnostic ID: 11111111-1111-1111-1111-111111111111
- Installation ID: 22222222-2222-2222-2222-222222222222

---
Prepared by Terento. Please review before submitting.
