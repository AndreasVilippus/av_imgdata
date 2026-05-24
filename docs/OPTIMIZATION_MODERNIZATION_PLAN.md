# Optimization And Modernization Plan

## Purpose

This document records optional optimizations and modernizations for `av_imgdata`, ordered by priority and evaluated by expected speed and stability impact.

It is intentionally a planning document. It does not authorize broad rewrites. Every implementation step must follow `docs/ARCHITECTURE_AND_DEVELOPMENT_GUIDELINES.md` and `docs/status-concept-integrated.md`.

## Evaluation Scale

| Value | Meaning |
|---|---|
| High | Clear and broad improvement expected for realistic package use |
| Medium | Improvement expected in specific flows or larger libraries |
| Low | Minor or indirect improvement |
| Conditional | Useful only after profiling, logs, HAR data, or reproducible evidence |

## Governing Constraints

The following constraints apply to every item in this plan:

- Do not guess. Inspect current implementation, tests, runtime state, logs, HAR data, or direct API behavior before changing logic.
- Keep changes narrow and task-focused.
- Preserve DSM package installability without manual post-installation steps.
- Keep optional external capabilities explicit, status-visible, and license-aware.
- Do not silently bundle InsightFace models or other license-sensitive assets.
- Treat long-running process state as backend-owned.
- Preserve `operation`, `mode`, `action`, `operation_id`, and `revision` semantics when touching runtime progress.
- Use `status.schema_version == 1`, `status.progress`, and `status.counters` for status/progress modernization.
- Do not infer relevant UI counters from legacy raw fields once schema counters are available.
- Keep UI strings translated in English and German together.
- Keep view components slim; behavioral logic belongs in mixins or dedicated modules.
- Use focused verification first; broaden tests only when the touched area requires it.

---

# Priority 1: Stabilize Long-Running Operations And State Ownership

## 1.1 Introduce a focused runtime operation model

### Current finding

Long-running flows involve several parallel state concepts: in-memory thread references, progress dictionaries, runtime-state files, stop requests, candidate caches, findings files, and UI polling. The status concept requires deterministic ownership and reconnect behavior for `file_analysis`, `checks`, `face_match`, and `cleanup`.

### Goal

Create a small shared operation model for backend-owned long-running operations.

### Proposed scope

Introduce focused backend helpers, for example:

```text
src/services/runtime_operation.py
src/services/runtime_status_builder.py
src/services/runtime_progress_store.py
```

The names are suggestions. Use existing project naming patterns when implementing.

The model should represent:

- `operation`
- `action` or `check_type`
- `mode`
- `operation_id`
- `revision`
- `phase`
- `running`
- `stop_requested`
- `started_at`
- `updated_at`
- relevant object identity
- structured error context

### Expected speed impact

Medium.

The direct processing speed gain is limited, but status endpoints can become cheaper and less likely to trigger expensive live revalidation.

### Expected stability impact

High.

This directly reduces stale progress, wrong reconnect behavior, scan/findings overwrites, and cross-operation blocking mistakes.

### Verification

Add or update focused tests for:

- reconnect after DSM window close/reopen
- `scan` not overwriting active `findings`
- stale `stopping` timeout
- cross-operation start blocking
- persisted `running: true` remaining authoritative
- operation-specific `stop_requested`

## 1.2 Centralize status payload builders

### Current finding

The status concept requires the backend to decide which counters are relevant. The UI must not infer relevance from raw legacy fields.

### Goal

Create central status builders for all long-running operation payloads.

### Proposed scope

Add builder functions or a small builder service for:

```python
_buildStatusPayload(...)
_buildStatusProgress(...)
_buildStatusCounter(...)
```

or equivalent project-style names.

The builders must produce:

- `status.schema_version == 1`
- `status.operation`
- `status.action`
- `status.mode`
- `status.phase`
- optional `status.save_only`
- exactly one `status.progress`
- only relevant `status.counters`

### Expected speed impact

Low.

### Expected stability impact

High.

It prevents inconsistent status payloads across Checks, FaceMatch, Cleanup, and File Analysis.

### Verification

Add contract tests for:

- Checks save-only scan sends only `findings`
- Checks findings review sends only event counters such as `resolved`, `ignored`, `skipped`, `errors`
- FaceMatch save-only scan sends only `findings`
- FaceMatch auto-apply sends `transferred`, optional `skipped`, optional `errors`
- FaceMatch findings review uses `entries`
- finished progress does not show an active progress bar only because `current == total`

## 1.3 Extract write locking into a dedicated service

### Current finding

Write locks are sensitive because file metadata writes and Synology Photos writes can affect the same image, sidecar, face, item, or person.

### Goal

Move process-level write lock handling out of broad orchestration code and into a small, testable service.

### Proposed scope

Create a helper such as:

```text
src/services/write_lock_service.py
```

It should support lock keys for:

- metadata path
- sidecar path
- Photos face
- Photos item
- optional person-related operations

It should return structured conflict errors with:

- `code`
- `message_key`
- `phase`
- `retryable`
- affected path/item/face/person identity

### Expected speed impact

Low.

### Expected stability impact

High.

This reduces race conditions and makes write conflicts explicit instead of accidental.

### Verification

Tests should cover:

- same-image concurrent metadata write conflict
- same Photos face concurrent assignment conflict
- unrelated writes not blocking each other
- conflict payload includes enough UI-safe context

## 1.4 Keep save-only findings persistently authoritative

### Current finding

The status concept requires save-only scans to persist findings during the scan and force-write them at `stopped`, `failed`, or `finished`.

### Goal

Ensure Checks and FaceMatch use the same persistence principle for save-only findings.

### Proposed scope

Audit and normalize:

- debounced findings writes
- forced final findings writes
- resume behavior
- skip-list reconstruction from persisted entries
- findings count semantics

### Expected speed impact

Medium.

Persisted append/resume behavior can reduce reprocessing after process loss.

### Expected stability impact

High.

This prevents lost findings, duplicated findings, and stale historical counts.

### Verification

Regression tests for:

- resumed save-only scan appends to existing persisted findings
- final write does not replace persisted findings with worker-local partial state
- `findings_count` means persisted open findings, not only new findings since resume
- current stored findings count is used after completed progress becomes historical

## 1.5 Preserve action locks for interactive results

### Current finding

The concept requires interactive FaceMatch result actions to disable transfer, create, rename, suggestion, and next buttons immediately until the next stable UI phase.

### Goal

Ensure result actions cannot be double-triggered and cannot clear visible results before backend acknowledgment.

### Proposed scope

Audit FaceMatch and Checks result actions for:

- immediate local action lock
- backend mutation response as the state transition source
- no premature result clearing
- no generic completion message overriding a real result

### Expected speed impact

Low.

### Expected stability impact

High.

This prevents duplicate writes and confusing UI state transitions.

### Verification

UI/static tests for:

- result buttons disabled immediately after action click
- `next`, `skip`, `resume`, `apply`, `create`, or `assign` do not clear visible result before backend response
- generic `finished` message does not hide an available FaceMatch result

---

# Priority 2: Modularize The Backend Without Changing Language

## 2.1 Split broad orchestration from `ImgDataService`

### Current finding

`ImgDataService` coordinates business workflows, progress state, thread management, candidate caches, write locks, metadata parsing, Photos access, file access, and findings handling.

### Goal

Reduce the main service into explicit orchestration boundaries while preserving existing behavior.

### Proposed scope

Extract only when tests or implementation work require it. Candidate service boundaries:

```text
src/services/checks_workflow_service.py
src/services/face_match_workflow_service.py
src/services/cleanup_workflow_service.py
src/services/file_analysis_workflow_service.py
src/services/runtime_operation_service.py
src/services/write_lock_service.py
```

Do not perform a broad rename-only rewrite. Each extraction must be behavior-preserving and covered by focused tests.

### Expected speed impact

Medium.

The main speed benefit is indirect: smaller services make targeted performance work possible.

### Expected stability impact

High.

This reduces accidental cross-flow regressions.

### Verification

For each extracted flow:

- existing focused tests still pass
- route/API behavior remains unchanged
- status contract remains unchanged
- no duplicate write workflow appears in route handlers

## 2.2 Keep API routes thin and mutation responses complete

### Current finding

The guidelines require API entrypoints to stay thin and mutation routes to return enough updated state for the UI.

### Goal

Prevent route handlers from duplicating multi-step business workflows.

### Proposed scope

Audit routes that mutate:

- findings
- mappings
- ignore lists
- runtime progress
- Photos assignments
- metadata writes

Each route should delegate workflow steps to service methods and return updated state needed by UI.

### Expected speed impact

Low.

### Expected stability impact

High.

This prevents stale UI state and duplicate backend logic.

### Verification

Tests for mutation routes should assert:

- response contains updated current item or list status
- response contains updated progress/status where relevant
- route does not require UI to reconstruct backend state from stale local data

## 2.3 Separate metadata parsers by schema

### Current finding

ACDSee, Microsoft, and MWG region parsing are currently related but semantically distinct. Guidelines require preserving schema-specific behavior, orientation, dimensions, source format, source identity, and coordinate precision rules.

### Goal

Make parser behavior easier to test and change without cross-schema side effects.

### Proposed scope

Potential module split:

```text
src/parser/acd_region_parser.py
src/parser/microsoft_region_parser.py
src/parser/mwg_region_parser.py
src/parser/metadata_parser.py
```

`metadata_parser.py` may remain the facade.

### Expected speed impact

Low.

### Expected stability impact

Medium to High.

The main benefit is safer handling of edge cases and format-specific regressions.

### Verification

Fixture-based tests for:

- ACD named faces
- unnamed ACD opt-in behavior
- ACD `NameAssignType == denied`
- Microsoft regions
- MWG regions
- MWG `AppliedToDimensions`
- orientation handling
- dimension mismatch context
- source format and source identity preservation

## 2.4 Centralize coordinate precision and signature use

### Current finding

The guidelines require face coordinate comparison and signatures to use shared precision helpers.

### Goal

Prevent divergent coordinate formatting or matching rules.

### Proposed scope

Audit all face signature, comparison, and display normalization paths for direct rounding or string formatting.

### Expected speed impact

Low.

### Expected stability impact

Medium.

This avoids duplicate or missed face detections caused by inconsistent rounding.

### Verification

Focused tests for:

- identical metadata face signature across flows
- tolerant comparison at boundary values
- display normalization preserving source format and orientation behavior

---

# Priority 3: Improve Persisted Findings And Runtime Storage

## 3.1 Add a storage abstraction before considering SQLite

### Current finding

Findings and runtime state are currently JSON-backed through `FileAnalysisService`. The guidelines require change-aware atomic writes through this service, not ad hoc file writes.

### Goal

Introduce a storage boundary that allows JSON to remain current behavior while enabling SQLite later.

### Proposed scope

Add an interface-like service layer for:

- read findings status
- read page of findings entries
- append findings entries
- replace/update one finding
- remove/ignore/resolve one finding
- force flush
- read/write runtime state

Keep JSON as the first backend.

### Expected speed impact

Medium.

The interface enables pagination and avoids full-file loading in status paths.

### Expected stability impact

High.

It makes persistence semantics explicit.

### Verification

Tests for both current JSON behavior and new abstraction:

- atomic write remains used
- status reads do not materialize full findings list unnecessarily
- mutation responses return current status
- invalid state files fail safely with structured error or empty state as currently intended

## 3.2 Add pagination for stored findings

### Current finding

Large findings lists can make UI loading and status endpoints expensive.

### Goal

Load only the required page or current item where possible.

### Proposed scope

Backend APIs should support:

- current item
- total open entries
- page size
- cursor or index
- mutation result with next current item

Do not change UI semantics: a displayed result remains stable until backend replaces, resolves, skips, or clears it.

### Expected speed impact

High for large libraries.

### Expected stability impact

Medium to High.

Less memory pressure and less full-list rewriting.

### Verification

Tests for:

- first page load
- next item after resolve
- next item after ignore
- current item remains stable during action in flight
- empty list returns explicit zero status
- historical progress count does not override current findings count

## 3.3 Evaluate SQLite only after storage boundary exists

### Current finding

SQLite could improve large findings persistence, but switching storage directly would create migration risk.

### Goal

Make SQLite an implementation option, not a broad behavioral rewrite.

### Proposed scope

Evaluate SQLite only after:

- JSON storage abstraction exists
- status/finding APIs use the abstraction
- tests define expected behavior

SQLite schema candidates:

```sql
operations(operation_id, operation, action, mode, phase, revision, started_at, updated_at, payload_json)
findings(id, finding_type, action, entry_token, status, payload_json, created_at, updated_at)
ignore_entries(ignore_type, entry_token, payload_json, created_at)
```

### Expected speed impact

High for large findings lists.

### Expected stability impact

High if introduced behind tests; Medium if introduced directly.

### Verification

Migration tests:

- existing JSON findings remain readable or are deterministically migrated
- migration is idempotent
- rollback/failure does not delete JSON source data
- package start remains functional without manual steps

---

# Priority 4: Make DSM Startup And Optional Dependencies More Diagnosable

## 4.1 Move complex shell logic into Python helpers

### Current finding

The DSM lifecycle script must remain, but it currently contains complex venv, pip, wheelhouse, manifest, and optional package logic.

### Goal

Keep Shell as DSM wrapper and move complex behavior to Python helpers.

### Proposed scope

Potential helper:

```text
src/package_runtime.py
```

or:

```text
scripts/runtime_helper.py
```

Functions:

- validate core Python packages
- validate optional package config
- prepare wheelhouse
- install from manifest
- validate InsightFace/OpenCV import status
- write status JSON
- emit clear exit codes

The shell script should call these helpers and keep process start/stop/status responsibility.

### Expected speed impact

Low to Medium.

It can avoid repeated expensive checks when status files are valid.

### Expected stability impact

High.

Python is easier to test and safer for JSON/config handling.

### Verification

Focused tests for:

- missing venv
- missing core packages
- optional package disabled
- optional package enabled without model
- wheelhouse manifest invalid
- OpenCV conflict cleanup
- no optional package required for normal startup

## 4.2 Make optional dependency status explicit and license-aware

### Current finding

InsightFace, ONNXRuntime, OpenCV, wheelhouse packages, and models are optional and must remain explicit.

### Goal

Improve status visibility without hidden downloads or silent bundling.

### Proposed scope

Status should include:

- package enabled/disabled
- install-on-start enabled/disabled
- import result per module
- active model name
- model root
- model store exists
- available models
- wheelhouse enabled/disabled
- manifest target
- conflict state for OpenCV variants
- license notice location if provided

### Expected speed impact

Low.

### Expected stability impact

High.

Reduces startup failures and misconfiguration confusion.

### Verification

Tests must pass without optional packages installed.

Use mocks for import checks and filesystem status.

## 4.3 Add explicit package-runtime diagnostics

### Current finding

Failures in package start, dependency installation, or backend startup need to be diagnosable without manual guessing.

### Goal

Write structured diagnostic status below package var.

### Proposed scope

Add files such as:

```text
runtime_state/package_start_status.json
runtime_state/optional_dependencies_status.json
```

Avoid tokens, cookies, and credentials.

### Expected speed impact

Low.

### Expected stability impact

Medium to High.

Faster diagnosis means less guessed recovery code.

### Verification

Tests for:

- no secret values written
- failed install records command phase and error code
- status is overwritten atomically
- UI can read and display summary

---

# Priority 5: Harden Synology Photos And Session Handling

## 5.1 Keep Synology API behavior observed, not assumed

### Current finding

Guidelines require HAR, browser traces, direct API inspection, or observed behavior before changing Synology-specific logic.

### Goal

Prevent product logic from depending on undocumented or ineffective API parameters.

### Proposed scope

For each Photos API change:

- record observed request/response sample in test fixture or notes
- centralize request construction in handler
- preserve remote API name and error code in structured errors

### Expected speed impact

Low.

### Expected stability impact

High.

### Verification

Tests for:

- request parameters built as expected
- error payload preserves remote API and code
- retry only on known session/transient failures

## 5.2 Improve Photos lookup caching with explicit invalidation

### Current finding

Photos lookups can be expensive, but caches must not hide writes or stale object states.

### Goal

Cache read-heavy data while invalidating after known writes.

### Proposed scope

Cache candidates:

- folder ID by path
- items by folder
- persons by normalized name
- thumbnails or item metadata where safe

Invalidation triggers:

- person create
- face assign
- item metadata mutation
- explicit refresh

### Expected speed impact

Medium to High for large libraries.

### Expected stability impact

Medium.

Bad invalidation can reduce stability, so implement narrowly.

### Verification

Tests for:

- cache hit on repeated read
- invalidation after create/assign
- stale cache not used before sensitive write verification
- cache metrics optional and debug-only

## 5.3 Preserve structured session and retry errors

### Current finding

Retries must be limited to understood failure modes. Session handling belongs in `SessionManager`.

### Goal

Avoid duplicate login/resume logic in route handlers and services.

### Proposed scope

Audit for:

- duplicated auth handling
- retry logic outside `SessionManager`
- generic 500 errors for known session states
- missing safe request context in errors

### Expected speed impact

Medium in transient DSM/API issues.

### Expected stability impact

High.

### Verification

Tests for:

- session bootstrap required
- transient 502/503/504 retry where allowed
- non-idempotent write not retried without safe condition
- request failures mapped to structured errors

---

# Priority 6: Modernize Frontend State Handling Without A Framework Rewrite

## 6.1 Extract DSM API client from `App.vue`

### Current finding

`App.vue` contains DSM credential context, API calls, timeout mapping, error formatting, polling helpers, and some display helpers.

### Goal

Move behavior out of the root view component.

### Proposed scope

Create modules such as:

```text
ui/src/services/dsmApiClient.js
ui/src/services/backendErrorFormatter.js
ui/src/services/runtimePolling.js
```

Keep DSM app registration behavior intact.

### Expected speed impact

Low.

### Expected stability impact

High.

It reduces UI state regressions and makes request behavior testable.

### Verification

Static/UI tests for:

- `callDsmApi` still includes required cookies/token/context
- endpoint-specific timeouts preserved
- backend error formatting preserved
- no direct prop mutation introduced

## 6.2 Implement a shared runtime polling layer

### Current finding

The status concept defines polling keys, opt-in overlap guard, pending reset in `finally`, and separation from ordinary status/config requests.

### Goal

Make polling behavior consistent for:

- `checks_progress`
- `face_match_progress`
- `file_analysis_progress`
- `cleanup_progress`

### Proposed scope

Create a polling service or mixin utility with:

- `poll_key`
- `pending`
- `run_id`
- `skipIfPending`
- no `force` for normal interval polling
- no request-id/revision increment on skipped ticks
- reconnect support

### Expected speed impact

Medium.

Avoids request storms against slow/hanging backend status endpoints.

### Expected stability impact

High.

Prevents polling errors from overwriting backend operation state.

### Verification

Tests from the concept:

- overlap guard is opt-in
- normal status/config requests do not use the guard
- guard runs before request-id/revision changes
- pending resets in `finally`
- polling errors do not mark backend operation failed
- reconnect can restart polling

## 6.3 Remove legacy counter inference after schema status is complete

### Current finding

The concept states that legacy fallback ends once schema status fields are present.

### Goal

Make UI counter display backend-driven.

### Proposed scope

For Checks and FaceMatch:

- use `progress.status.counters`
- filter by `show_when_zero || value > 0`
- do not add raw legacy counters when schema counters exist
- render status text inside progress element when progress is visible

### Expected speed impact

Low.

### Expected stability impact

High.

Prevents wrong counters and duplicate messages.

### Verification

UI tests for:

- save-only scan shows only `findings`
- auto apply shows `transferred` but not `findings`
- findings review shows event counters only
- status text is not duplicated below progress

## 6.4 Keep Vue 2 unless DSM compatibility is proven

### Current finding

The DSM UI integration relies on Synology app registration and Vue 2-era component conventions.

### Goal

Avoid framework churn.

### Proposed scope

Do not migrate to Vue 3, Vite, or a new UI framework unless:

- DSM app registration works
- Synology components work
- package build chain works
- UI tests or manual DSM smoke tests prove compatibility

### Expected speed impact

Conditional.

### Expected stability impact

Conditional to negative unless proven.

### Recommendation

Do not prioritize this migration. Prefer modular JS extraction first.

---

# Priority 7: Improve Tests And Verification Strategy

## 7.1 Add status payload contract tests

### Goal

Lock down backend status correctness before broader refactors.

### Proposed tests

```text
tests/test_status_payload_contract.py
```

Coverage:

- schema version
- operation/mode/action/phase
- progress kind
- relevant counters only
- no irrelevant zero counters
- blocked operation payload
- stale stopping behavior

### Expected speed impact

Indirect.

### Expected stability impact

High.

## 7.2 Add UI status contract tests

### Goal

Lock down UI display semantics.

### Proposed tests

```text
tests/test_status_ui_contract.py
```

or existing UI test structure if already present.

Coverage:

- schema counters preferred
- no legacy counter reconstruction
- no duplicate status line when progress visible
- reconnect reads without unsafe apply
- scan progress does not overwrite findings review
- `stop_requested` scoped to same operation/mode/action

### Expected speed impact

Indirect.

### Expected stability impact

High.

## 7.3 Add large-library synthetic performance tests

### Goal

Identify real hot paths before language or storage changes.

### Proposed scope

Synthetic tests should cover:

- many image paths
- many metadata faces
- many Photos faces
- large findings list
- repeated status polling
- repeated persisted findings mutations

### Expected speed impact

Indirect.

### Expected stability impact

Medium.

### Output

Record baseline metrics for:

- scan setup time
- per-file processing time
- findings append/write time
- status endpoint time
- memory use if practical
- Photos API call count when mocked

## 7.4 Keep optional dependency tests mock-based

### Goal

Ensure normal test suite does not require optional packages or model downloads.

### Proposed scope

Mock:

- `cv2`
- `insightface.app.FaceAnalysis`
- `onnxruntime`
- model-store filesystem

### Expected speed impact

Medium for CI/test runtime.

### Expected stability impact

High.

---

# Priority 8: Conditional Performance Work After Profiling

## 8.1 Optimize face matching only if it dominates runtime

### Current finding

IoU matching is simple and isolated. It should not be rewritten without evidence.

### Possible optimization

If profiling shows matching is expensive:

- group by image/source first
- apply coordinate-range prefilter
- avoid comparing faces from incompatible sources
- keep deterministic sorting

### Expected speed impact

Conditional; Medium to High only for many faces per image or very large candidate sets.

### Expected stability impact

Medium if implemented narrowly.

### Verification

Performance tests must show improvement while preserving exact match results for fixtures.

## 8.2 Optimize image file listing only if scan startup is slow

### Current finding

The status concept requires preparing status before long file listing, so the UI does not look stuck.

### Possible optimization

- cache candidate path lists with config fingerprint
- stream candidates where possible
- update preparing status before listing
- avoid rescanning unchanged folders if reliable change criteria exist

### Expected speed impact

Conditional; High for very large libraries.

### Expected stability impact

Medium.

### Caution

Do not add guessed cache invalidation. Use deterministic fingerprints or explicit refresh.

## 8.3 Consider a separate face-detection worker only after evidence

### Current finding

Face detection is optional and dependency-heavy. Python remains the best fit because OpenCV, InsightFace, and ONNXRuntime integration are Python-oriented.

### Possible optimization

Use a separate process worker for optional detection if:

- detection blocks the API process too long
- memory fragmentation or model lifecycle causes instability
- DSM process management remains clear

### Expected speed impact

Conditional.

### Expected stability impact

Conditional.

It can isolate failures, but adds process management complexity.

### Caution

Do not introduce model downloads, hidden installs, or untracked dependencies.

---

# Priority 9: Low-Risk Maintenance Modernizations

## 9.1 Add config schema validation and migration tests

### Goal

Ensure new settings are normalized and legacy migration stays deterministic and idempotent.

### Expected speed impact

Low.

### Expected stability impact

High.

### Verification

Tests for:

- default config contains new keys
- `normalizeConfig()` preserves unrelated areas
- migration runs repeatedly without changing valid config
- UI config save does not drop unrelated config sections

## 9.2 Improve structured logging with operation identity

### Goal

Make runtime failures diagnosable without guessing.

### Proposed scope

Log important events with:

- operation
- action
- mode
- operation_id
- revision
- phase
- path/item/face/person identity where safe
- error code
- retryable flag

No cookies, tokens, credentials, or full secrets.

### Expected speed impact

Low.

### Expected stability impact

Medium to High.

## 9.3 Keep build and dependency pins explicit

### Goal

Avoid build drift, especially with DSM/Python/OpenSSL compatibility.

### Proposed scope

- keep core requirements minimal
- keep optional requirements explicit
- document why pins exist
- keep wheelhouse handling explicit
- update README when build behavior changes

### Expected speed impact

Low.

### Expected stability impact

Medium.

---

# Items Explicitly Not Recommended Now

## Full backend rewrite to Go, Rust, Java, or Node

### Reason

The current backend depends on Python-friendly ecosystems: FastAPI, Requests, OpenCV, InsightFace, ONNXRuntime, XML/XMP parsing, and DSM package scripting. A rewrite would increase packaging and test risk without a proven performance bottleneck.

## Rewriting face detection in Rust or Go

### Reason

The optional detection stack is Python-oriented. Native rewrites would create binary compatibility and DSM packaging risk.

## Vue 3 or framework migration as a primary optimization

### Reason

The DSM UI integration and current Vue 2 component path are working constraints. Modularizing the current UI is safer.

## Hidden automatic model or dependency downloads

### Reason

This violates the distribution and optional dependency rules. Optional models and packages must remain explicit, status-visible, and license-aware.

## Broad fallback or retry logic for unknown failures

### Reason

Project rules require observed failure modes. Unknown failures should be diagnosable, not silently hidden.

---

# Suggested Implementation Order

| Order | Work Package | Speed Impact | Stability Impact | Verification |
|---:|---|---|---|---|
| 1 | Add/confirm status payload contract tests | Indirect | High | Backend status tests |
| 2 | Add/confirm UI status contract tests | Indirect | High | UI/static tests |
| 3 | Centralize status builders | Low | High | Status contract tests |
| 4 | Add shared runtime polling layer | Medium | High | UI polling tests |
| 5 | Extract write lock service | Low | High | Concurrency/conflict tests |
| 6 | Normalize save-only findings persistence | Medium | High | Resume/final-write tests |
| 7 | Introduce runtime operation model | Medium | High | Reconnect/blocking tests |
| 8 | Start `ImgDataService` modular extraction | Medium | High | Existing + focused tests |
| 9 | Add findings storage abstraction | Medium | High | Persistence tests |
| 10 | Add findings pagination | High for large libraries | Medium to High | Findings UI/API tests |
| 11 | Move complex lifecycle logic into Python helper | Low to Medium | High | Startup/helper tests |
| 12 | Improve optional dependency status | Low | High | Mocked optional package tests |
| 13 | Improve Photos lookup caching | Medium to High | Medium | Cache invalidation tests |
| 14 | Split metadata parsers by schema | Low | Medium to High | Parser fixtures |
| 15 | Profile large scans and only then optimize matching/listing | Conditional | Medium | Performance baselines |
| 16 | Evaluate SQLite | High for large libraries | High if behind abstraction | Migration tests |

---

# Documentation Maintenance Rules

When this plan changes:

- Keep it under `docs/`.
- Update the architecture guidelines if the change creates a new general rule.
- Update the status concept if the change affects progress, counters, modes, button states, reconnect, or polling.
- Update `tests/function_matrix.md` if metadata file access, sidecar lookup, native parsing, or ExifTool behavior changes.
- Keep implementation plans specific. Avoid generic modernization goals without a testable project impact.
