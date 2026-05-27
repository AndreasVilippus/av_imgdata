# Status Concept Integrated

## Purpose

This document defines the integrated status and progress concept for `av_imgdata` checks, face matching, file analysis, and cleanup.

The backend owns status semantics. The UI renders the status structure and must not reconstruct relevant counters or operation state from legacy raw fields when schema status data is available.

## Core Principle

Backend is responsible for:

- status phase
- operation identity
- progress kind and values
- relevant counters
- visibility of zero counters
- cross-operation blocking
- persisted runtime state

UI is responsible for:

- translating label keys
- rendering progress
- rendering counters explicitly sent by the backend
- guarding against stale progress overwrites
- preserving local review state until backend mutation responses replace it

## Operations

Supported long-running operations:

| Operation | Meaning |
|---|---|
| `checks` | metadata and data checks |
| `face_match` | face matching workflows |
| `file_analysis` | file analysis |
| `cleanup` | cleanup workflows |

## Modes

| Mode | Meaning |
|---|---|
| `scan` | backend-owned search, check, cleanup, or analysis work |
| `findings` | stored findings list is being reviewed or applied |
| `snapshot` | refresh without active processing |
| `idle` | no active operation state |
| `none` | no progress display intended, for example blocked start response |

`operation`, `mode`, `action`, and `operation_id` form the process identity. A `scan` state and a `findings` state must not overwrite each other without an explicit transition.

## Phases

| Phase | Meaning |
|---|---|
| `preparing` | preparing candidates or runtime data |
| `running` | active processing |
| `paused` | paused operation |
| `stopping` | stop requested |
| `stopped` | stopped |
| `finished` | finished |
| `failed` | failed |
| `empty` | no result |
| `blocked` | start blocked by another operation |

## Unified Status Schema

Long-running operation payloads should include:

```json
{
  "message_key": "checks:progress_scanning",
  "message_params": {},
  "status": {
    "schema_version": 1,
    "operation": "checks",
    "action": "name_conflicts",
    "mode": "scan",
    "phase": "running",
    "save_only": true,
    "progress": {
      "kind": "files",
      "title_key": "checks:label_images",
      "fallback_title": "Images",
      "current": 120,
      "total": 41070,
      "primary_label_key": "checks:label_scanned",
      "fallback_primary_label": "checked",
      "secondary_label_key": "checks:label_remaining",
      "fallback_secondary_label": "remaining"
    },
    "counters": [
      {
        "key": "findings",
        "label_key": "checks:counter_stored_findings",
        "fallback_label": "In match list",
        "value": 7,
        "show_when_zero": true
      },
      {
        "key": "resolved",
        "label_key": "checks:counter_auto_resolved",
        "fallback_label": "Auto resolved",
        "value": 3,
        "show_when_zero": false
      }
    ]
  }
}
```

## Progress Kinds

| Kind | Meaning |
|---|---|
| `files` | files or images are processed |
| `images` | images are processed |
| `persons` | persons are processed |
| `faces` | faces are processed |
| `entries` | stored findings entries are processed |
| `metadata_faces` | metadata faces are processed |
| `target_faces` | target or Photos faces are processed |
| `none` | no progress bar |

Rules:

- `progress` describes one progress bar.
- `current` and `total` must be numeric.
- If `total` is unknown, `total` may be `0`.
- `finished` must not show an active progress bar just because `current == total`.
- File-list-based scans should write a preparing status before expensive candidate listing.

## Counter Keys

| Key | Meaning |
|---|---|
| `findings` | found entries |
| `processed` | processed |
| `transferred` | transferred or applied |
| `resolved` | resolved |
| `ignored` | ignored |
| `skipped` | skipped |
| `errors` | errors |
| `created` | created |
| `assigned` | assigned |
| `updated` | updated |

Rules:

- Backend sends only relevant counters.
- Irrelevant zero counters are omitted.
- A zero counter is shown only when `show_when_zero: true` is set.
- UI displays only counters from `status.counters` when schema version 1 is present.
- UI must not add counters from legacy fields such as `findings_count`, `resolved_count`, `ignored_count`, `skipped_count`, or `transferred_count`.

## Checks Matrix

### Save-only scan

| Field | Value |
|---|---|
| `operation` | `checks` |
| `mode` | `scan` |
| `save_only` | `true` |
| Progress | `files` |
| Counters | `findings`, optional `resolved` |

For save-only scans, `findings` counts only entries actually written to the later stored findings list. If automatic corrections are enabled, `resolved` counts successfully auto-resolved conflicts. Do not show `ignored`, `transferred`, or old stored findings counts.

### Interactive scan

| Field | Value |
|---|---|
| `operation` | `checks` |
| `mode` | `scan` |
| `save_only` | `false` |
| Progress | `files` |
| Counters | `findings` optional, `resolved` only for real auto-resolve events |

### Stored findings review

| Field | Value |
|---|---|
| `operation` | `checks` |
| `mode` | `findings` |
| Progress | `entries` |
| Counters | `resolved`, `ignored`, `skipped`, `errors` only when relevant |

Do not show `findings` when `entries.total` already describes list size.

## Face Match Matrix

### Save-only scan

| Field | Value |
|---|---|
| `operation` | `face_match` |
| `mode` | `scan` |
| `save_only` | `true` |
| Counters | `findings` |

Do not show `transferred`, `skipped`, or old stored findings counts. If auto-transfer is active, `findings` counts only entries that remain in the later findings list.

### Auto transfer or assignment

| Field | Value |
|---|---|
| `operation` | `face_match` |
| `mode` | `scan` |
| `save_only` | `false` |
| Counters | `transferred`, optional `skipped`, optional `errors` |

Do not show `findings` unless findings are actually stored.

### Stored findings review

| Field | Value |
|---|---|
| `operation` | `face_match` |
| `mode` | `findings` |
| Progress | `entries` |
| Counters | `transferred`, `skipped`, `errors` only when relevant |

Rules:

- `entries.total` remains the loaded initial list size during review.
- `entries.current` must not decrease after `next` or successful apply.
- A removed entry counts as completed.
- Persisted scan progress must not reset a running findings review.

## Reconnect Rules

- Persisted `running: true` progress remains authoritative after DSM window close/reopen.
- UI must read persisted progress on view open.
- UI must not immediately apply scan progress over an active findings review.
- Checks views must discover running check scans across check types and adopt only matching scan state.
- `stop_requested` applies only to the operation, action/check type, and mode that produced it.
- A stored findings review remains visible until the backend replaces, resolves, skips, ignores, or clears the current item.

## Polling Rules

Runtime polling applies to:

| Poll key | Operation |
|---|---|
| `checks_progress` | `checks` |
| `face_match_progress` | `face_match` |
| `file_analysis_progress` | `file_analysis` |
| `cleanup_progress` | `cleanup` |

Rules:

- Polling overlap protection is opt-in for runtime progress timers.
- At most one request should be in flight per runtime progress timer when `skipIfPending` is enabled.
- Skipped poll ticks must not increment request ID, revision, or stale detection.
- `pending` must reset in `finally`.
- Normal status, config, ExifTool, pip package, and findings status requests must not use the runtime polling guard.
- Polling errors are communication problems, not proof that the backend operation failed.
- Polling errors must not overwrite persisted backend progress.
- Reconnect can restart polling after stopped or failed polling.

## Cross-Operation Blocking

Only one long-running operation may run at a time across:

- file analysis
- checks scan
- face matching
- cleanup

If a new operation is requested while another is running, the backend must not spawn a new worker. It should return:

- `blocked_by_running_operation: true`
- `requested_operation`
- `running_operation`
- `running_progress` if known
- `message_key: "status:operation_blocked_by_running_operation"`
- `status.schema_version: 1`
- `status.operation: <requested_operation>`
- `status.mode: "none"`
- `status.phase: "blocked"`

A stale `stopping` state may stop blocking only through an explicit stale timeout rule.

## Stored Findings And Historical Progress

- Persisted runtime progress is not the source of truth for the current stored findings list content.
- Stored findings status/list must provide the current count.
- A completed save-only progress count is historical after findings change.
- Empty stored findings must report `0` even if old progress has a historical count.
- Save-only scans must write findings debounced while running and force-write them on `stopped`, `failed`, or `finished`.
- Resume must use persisted findings and skip lists so already stored entries are not duplicated or replaced.

## Button State Rules

Primary button priority:

1. active run or stop requested -> `Stop`
2. auth/session continuation required -> `Resume after login` for face matching
3. explicitly repeatable stored scan -> `Restart`
4. otherwise -> `Start`

Checks restart condition:

```text
selectedChecksAction == "scan"
AND (checksSaveOnly OR hasChecksStoredFindings)
AND NOT isChecksReviewActive
AND NOT isChecksReviewStopping
```

FaceMatch restart condition:

```text
selectedFaceMatchingAction == "search_photo_face_in_file"
AND (faceMatchSaveOnly OR hasFaceMatchStoredFindings)
AND faceMatchIsPaused
```

`faceMatchIsPaused` is only a helper state and must not directly imply `Restart`.

## Result Action Rules

- An interactive FaceMatch result is not a generic completed scan message.
- A usable result must show the actual finding state.
- Generic finished messages must not hide an available result.
- Result action buttons must lock immediately during apply, create, assign, rename, suggestion, skip, or next operations.
- Visible result must remain stable until the backend returns the next stable state.

## Test Strategy

Backend status contract tests should verify:

- schema version
- operation/mode/action/phase
- progress kind
- relevant counters only
- irrelevant counters omitted
- blocked operation payload
- stale stopping behavior

UI status contract tests should verify:

- schema counters are preferred
- no legacy counter reconstruction with schema version 1
- no duplicate status line under visible progress
- reconnect does not overwrite active findings review
- scan progress does not overwrite findings mode
- `stop_requested` is scoped to matching operation/mode/action

Regression tests should cover Checks save-only, FaceMatch save-only, auto-transfer, findings review, final `running: false` start responses, hidden finished progress bars, stale stop timeout, and monotonically increasing findings positions.
