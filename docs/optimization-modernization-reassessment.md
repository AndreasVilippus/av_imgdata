# Optimization And Modernization Reassessment

## Scope

This document reassesses `docs/optimization-modernization-plan.md` after the new status implementation work on `main`.

The reassessment is based on the current `docs/` documents and the current implementation state visible in `src/imgdata.py`, `src/api/imgdata_api.py`, `ui/src/App.vue`, and recent status-related commits.

## Summary

Priority 1 is no longer fully open. The status implementation has completed or partially completed several Priority 1 items:

- schema version 1 status payload builders exist
- Checks and FaceMatch status payloads exist
- relevant counter filtering exists
- operation IDs and revisions are written for Checks progress
- cross-operation blocking exists
- runtime polling has an opt-in overlap guard
- saved findings and stored review behavior have been improved

However, much of the implementation still lives inside `ImgDataService` / `src/imgdata.py`. Therefore, the next architectural priority shifts from inventing status semantics to extracting and stabilizing the now-working status/runtime logic.

## Updated Priority Assessment

| Original item | Previous priority | New status | New priority | Reason |
|---|---:|---|---:|---|
| 1.1 Centralize status payload builders | 1 | Mostly implemented in `ImgDataService` | 2 | Semantics exist; remaining work is extraction, cleanup, and broader coverage. |
| 1.2 Introduce explicit runtime operation identity | 1 | Partially implemented | 1 | `operation_id` and `revision` exist for Checks; full uniform operation model is still missing. |
| 1.3 Shared runtime polling behavior | 1 | Partially implemented in `App.vue` | 2 | `skipIfPending` exists; remaining work is extraction from root component and broader contract tests. |
| 1.4 Normalize save-only findings persistence | 1 | Partially implemented | 1 | Historical progress and stored findings handling improved, but this remains correctness-critical. |
| 1.5 Extract write locking | 1 | Not completed as dedicated service | 1 | Locking exists in-process, but not as focused service; still high stability value. |
| 2.1 Split broad orchestration from `ImgDataService` | 2 | Not completed; need increased | 1 | Status work increased `imgdata.py` responsibility; extraction is now the key next step. |
| 2.2 Keep API routes thin | 2 | Partially implemented | 2 | Checks routes attach status via helper; broader route cleanup remains useful. |
| 2.3 Split metadata parsers by schema | 2 | Not started | 3 | Still useful, but less urgent than runtime/status extraction. |
| 3.1 Findings storage abstraction | 3 | Not completed | 2 | More important now because status/finding semantics are clearer and should be backed by a stronger storage boundary. |
| 3.2 Findings pagination | 3 | Not completed | 3 | Keep behind storage abstraction. |
| 3.3 SQLite evaluation | 3 | Not started | 4 | Still behind abstraction and measurements. |

## New Highest Priorities

### Priority 1A: Extract status/runtime logic from `ImgDataService`

The new status implementation solves semantic problems but concentrates more logic inside `src/imgdata.py`.

Extract the following into focused services:

```text
src/services/status_payload_builder.py
src/services/runtime_operation_service.py
src/services/write_lock_service.py
```

Suggested split:

- generic status builder
- Checks status builder
- FaceMatch status builder
- phase derivation
- cross-operation blocked response builder
- operation ID and revision handling
- stale stopping detection
- write conflict handling

Expected speed impact: Low to Medium.

Expected stability impact: High.

Verification:

- existing status payload contract tests must pass unchanged
- no response shape changes
- no UI status behavior changes
- no route-level workflow duplication introduced

### Priority 1B: Complete runtime operation identity across all long-running operations

Checks currently writes `operation_id` and `revision`; the same model should be consistently applied to:

- file analysis
- checks
- face match
- cleanup

Required fields should include:

- `operation`
- `action`
- `mode`
- `operation_id`
- `revision`
- `phase`
- `running`
- `stop_requested`
- updated timestamp

Expected speed impact: Medium.

Expected stability impact: High.

Verification:

- stale responses cannot overwrite newer ones
- reconnect applies only matching operation/mode/action
- cross-operation blocking reports the running operation identity
- stale stopping timeout behaves consistently

### Priority 1C: Extract write locking as a dedicated service

Write safety remains high priority. Current in-process lock behavior should be separated from workflow orchestration.

The target service should cover:

- metadata path locks
- sidecar path locks
- Photos face locks
- Photos item locks
- structured conflict errors

Expected speed impact: Low.

Expected stability impact: High.

Verification:

- same-target writes conflict
- unrelated writes do not block
- conflict responses include phase and object identity
- UI receives retryable/non-retryable information

### Priority 1D: Finish save-only findings correctness

Status and stored finding review behavior improved, but save-only persistence remains correctness-critical.

Remaining focus:

- force-write findings on all terminal states
- resume without duplication
- skip lists built from persisted entries
- current stored list count overrides historical completed progress
- stored review item remains stable until backend mutation response

Expected speed impact: Medium.

Expected stability impact: High.

Verification:

- stopped scan keeps written findings
- failed scan keeps written findings
- resume appends without replacing existing persisted entries
- empty list reports zero even with historical progress

## Priority 2 After Reassessment

### 2A: Move status builder implementation out of `imgdata.py`

This is the follow-up to Priority 1A once extraction seams are clear. The status builders are implemented enough to be moved, but the first extraction must preserve behavior exactly.

### 2B: Extract runtime polling from `App.vue`

The current root component contains `startNamedPolling` with `skipIfPending`. That is a useful improvement but still violates the broader frontend architecture goal of keeping behavior out of root/view components.

Target:

```text
ui/src/services/runtime-polling.js
```

Expected speed impact: Low to Medium.

Expected stability impact: High.

### 2C: Add or strengthen status contract tests

Current commits added several status-related tests, but the plan should still require explicit contract coverage for:

- generic status builder
- Checks status builder
- FaceMatch status builder
- blocked operation payload
- UI counter rendering from schema status
- no legacy counter reconstruction
- runtime polling guard behavior

### 2D: Start route cleanup after services exist

Route helpers such as status attachment are acceptable as a bridge. After service extraction, routes should delegate status/workflow behavior instead of assembling too much response logic inline.

## Priority 3 After Reassessment

### 3A: Findings storage abstraction

This moves from medium-term to near-term follow-up, but still after status/runtime extraction.

Reason: status correctness now depends heavily on persisted findings state. A storage boundary would make status reads cheaper and mutation responses more reliable.

### 3B: Metadata parser split

Still useful, but no longer Priority 2. It should wait until runtime/status extraction is stable.

### 3C: Photos caching and performance profiling

Keep behind tests and measurements. Do not optimize Photos caching before write invalidation rules are explicit.

## Deferred Items

The following remain deferred:

- SQLite evaluation
- Vue 3 migration
- separate face-detection worker
- face matching algorithm optimization
- broad backend language rewrite

## Revised Suggested Implementation Order

| Order | Work package | New priority | Speed impact | Stability impact |
|---:|---|---:|---|---|
| 1 | Extract status payload builders from `ImgDataService` | 1 | Low | High |
| 2 | Complete runtime operation identity for all long-running operations | 1 | Medium | High |
| 3 | Extract write lock service | 1 | Low | High |
| 4 | Finish save-only findings persistence/resume correctness | 1 | Medium | High |
| 5 | Extract runtime polling from `App.vue` | 2 | Low to Medium | High |
| 6 | Strengthen status and UI contract tests | 2 | Indirect | High |
| 7 | Refactor Checks and FaceMatch workflow orchestration out of `imgdata.py` | 2 | Medium | High |
| 8 | Add findings storage abstraction | 3 | Medium | High |
| 9 | Add findings pagination | 3 | High for large libraries | Medium to High |
| 10 | Split metadata parsers by schema | 3 | Low | Medium to High |
| 11 | Move lifecycle complexity into Python helper | 4 | Low to Medium | High |
| 12 | Improve optional dependency status | 4 | Low | High |
| 13 | Profile large scans before optimizing matching/listing | 5 | Conditional | Medium |
| 14 | Evaluate SQLite behind abstraction | 5 | High for large libraries | High |

## Decision

The strongest current architectural recommendation is now:

> Do not add more status/runtime logic directly to `src/imgdata.py`. First extract the implemented status and runtime primitives into focused services, then continue functional improvements.

This changes the practical priority of `2.1 Split broad orchestration from ImgDataService` from Priority 2 to Priority 1 for the status/runtime subset.
