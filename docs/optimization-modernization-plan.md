# Optimization And Modernization Plan

## Purpose

This document lists optional optimizations and modernizations for `av_imgdata`, sorted by priority and evaluated by expected speed and stability impact.

It follows:

- `docs/architecture-and-development-guidelines.md`
- `docs/status-concept-integrated.md`

The plan is intentionally implementation-oriented. It does not recommend a broad programming-language rewrite. Python, Vue 2, shell lifecycle hooks, Synology Toolkit packaging, ExifTool, and optional InsightFace/OpenCV integration should remain in place unless a focused change proves a better option through tests and measurements.

## Rating Scale

| Rating | Meaning |
|---|---|
| High | broad or clearly measurable benefit |
| Medium | benefit in specific flows or larger libraries |
| Low | minor or indirect benefit |
| Conditional | only useful after profiling, logs, HAR data, or reproduced evidence |

---

# Priority 1: Stabilize Status, Progress, And Long-Running Operations

## 1.1 Centralize status payload builders

### Problem

Checks, face matching, cleanup, and file analysis need consistent status semantics. The UI must not infer relevant counters from legacy raw fields once schema status data exists.

### Optimization

Create backend builders for schema version 1 status payloads:

- status payload
- progress object
- counter object
- blocked-operation response
- structured operation errors

### Required behavior

- `status.schema_version == 1`
- `status.operation`, `status.action`, `status.mode`, and `status.phase` are explicit.
- `status.progress` describes exactly one progress display.
- `status.counters` contains only relevant counters.
- Irrelevant zero counters are omitted.
- Zero counters are shown only with `show_when_zero: true`.

### Speed impact

Low.

### Stability impact

High.

### Verification

Add status contract tests for Checks and FaceMatch:

- save-only scan sends only `findings`
- findings review sends action counters only
- auto-transfer sends `transferred`, optional `skipped`, optional `errors`
- blocked operation returns `mode: "none"` and `phase: "blocked"`
- finished progress does not show an active progress bar merely because `current == total`

## 1.2 Introduce explicit runtime operation identity

### Problem

Runtime state, thread state, stop requests, persisted progress, and UI polling need a shared identity model.

### Optimization

Introduce a focused backend model or helper for long-running operations containing:

- `operation`
- `action` or `check_type`
- `mode`
- `operation_id`
- `revision`
- `phase`
- `running`
- `stop_requested`
- timestamps
- structured error context

### Speed impact

Medium.

### Stability impact

High.

### Verification

Tests for:

- reconnect after DSM window close/reopen
- stale `stopping` timeout
- cross-operation blocking
- scan state not overwriting active findings review
- `stop_requested` scoped to matching operation/mode/action

## 1.3 Implement shared runtime polling behavior in the UI

### Problem

Repeated status polling can create overlapping requests and stale state writes.

### Optimization

Extract shared polling logic with:

- stable `poll_key`
- opt-in `skipIfPending`
- local `pending` state
- `run_id`
- pending reset in `finally`
- skipped ticks not increasing request ID or revision

Runtime polling applies only to progress endpoints:

- `checks_progress`
- `face_match_progress`
- `file_analysis_progress`
- `cleanup_progress`

Normal status, config, ExifTool, pip package, and findings status requests must not use this guard.

### Speed impact

Medium.

### Stability impact

High.

### Verification

UI/static tests for:

- overlap guard is opt-in
- ordinary status/config calls bypass the guard
- polling errors do not mark backend operation failed
- reconnect can restart polling
- pending resets in `finally`

## 1.4 Normalize save-only findings persistence

### Problem

Save-only scans must not keep findings only in worker memory. Historical completed progress must not be treated as current findings state.

### Optimization

Normalize Checks and FaceMatch behavior:

- debounce findings writes during scans
- force-write on `stopped`, `failed`, and `finished`
- resume using persisted findings
- build skip lists from resume cursor and persisted entries
- report current stored findings count from stored findings, not old progress

### Speed impact

Medium.

### Stability impact

High.

### Verification

Regression tests for:

- resume appends without duplicating existing findings
- empty stored list reports `0`
- historical `findings_count` does not override current list status
- final worker write does not replace persisted data with stale partial state

## 1.5 Extract write locking

### Problem

Metadata and Synology Photos writes can collide on the same image, sidecar, face, or item.

### Optimization

Move lock handling into a focused service, for example:

```text
src/services/write_lock_service.py
```

Lock keys should cover:

- metadata path
- sidecar path
- Photos face
- Photos item
- relevant person operations if needed

Conflicts should return structured errors with code, phase, retryability, and affected object identity.

### Speed impact

Low.

### Stability impact

High.

### Verification

Tests for same-target write conflicts and unrelated writes running independently.

---

# Priority 2: Modularize Backend Workflow Code

## 2.1 Split broad orchestration from `ImgDataService`

### Problem

The main service coordinates workflows, progress, threads, caches, write locks, metadata parsing, Photos access, file access, and findings handling.

### Optimization

Extract focused services only when behavior remains covered by tests:

- checks workflow service
- face-match workflow service
- cleanup workflow service
- file-analysis workflow service
- runtime operation service
- write lock service

Avoid broad rename-only refactors.

### Speed impact

Medium, mostly indirect.

### Stability impact

High.

### Verification

Each extraction must preserve route/API behavior and status contract behavior.

## 2.2 Keep API routes thin

### Problem

Routes should not duplicate multi-step business workflows.

### Optimization

Route handlers should delegate mutations for:

- findings
- mappings
- ignore lists
- runtime progress
- Photos assignments
- metadata writes

Mutation responses must return enough updated state for the UI.

### Speed impact

Low.

### Stability impact

High.

### Verification

Route tests should assert returned updated progress/status/current item/list state.

## 2.3 Split metadata parsers by schema

### Problem

ACDSee, Microsoft, and MWG region parsing share a facade but have distinct semantics.

### Optimization

Keep `metadata_parser.py` as facade and split schema-specific logic into focused parser modules.

Important preservation rules:

- source format
- source identity
- orientation handling
- MWG AppliedToDimensions
- dimension mismatch warnings
- unnamed ACD opt-in behavior
- coordinate precision helpers

### Speed impact

Low.

### Stability impact

Medium to High.

### Verification

Fixture tests for ACD, Microsoft, MWG, orientation, dimensions, unnamed ACD, and denied ACD names.

---

# Priority 3: Improve Findings And Runtime Storage

## 3.1 Add storage abstraction before SQLite

### Problem

JSON findings are simple, but large lists can make status reads and mutations expensive.

### Optimization

Introduce a storage boundary before changing storage format:

- read findings status
- read current entry
- read page of entries
- append entries
- update/remove/ignore/resolve one entry
- force flush
- read/write runtime state

JSON remains the first backend.

### Speed impact

Medium.

### Stability impact

High.

### Verification

Tests must prove atomic JSON writes remain used and status reads do not need to materialize full findings lists where avoidable.

## 3.2 Add findings pagination

### Problem

Large findings lists can slow UI loading and increase memory pressure.

### Optimization

Support backend APIs for:

- total open entries
- current item
- page size
- cursor or index
- mutation response with next current item

### Speed impact

High for large libraries.

### Stability impact

Medium to High.

### Verification

Tests for first page, next item, resolve, ignore, empty list, and stable visible current item during action in flight.

## 3.3 Evaluate SQLite only behind abstraction

### Problem

SQLite can improve large-list storage but direct migration is risky.

### Optimization

Evaluate SQLite only after the storage abstraction and tests are stable.

Candidate tables:

- operations
- findings
- ignore entries

Migration must be deterministic, idempotent, and not require manual DSM steps.

### Speed impact

High for large libraries.

### Stability impact

High if behind abstraction; lower if done directly.

### Verification

Migration tests for existing JSON, repeated migration, failed migration, and startup without manual repair.

---

# Priority 4: Modernize DSM Startup And Optional Dependency Handling

## 4.1 Move complex shell logic into Python helpers

### Problem

The DSM lifecycle script must remain, but complex pip, wheelhouse, manifest, and optional package logic is easier to test in Python.

### Optimization

Keep shell as DSM wrapper. Move complex logic into a helper such as:

```text
src/package_runtime.py
```

or:

```text
scripts/runtime_helper.py
```

Responsibilities:

- validate core packages
- validate optional package config
- prepare wheelhouse
- install from manifest
- validate InsightFace/OpenCV status
- write status JSON
- return clear exit codes

### Speed impact

Low to Medium.

### Stability impact

High.

### Verification

Tests for missing venv, missing core packages, disabled optional packages, invalid wheelhouse manifest, OpenCV conflicts, and startup without optional packages.

## 4.2 Improve optional dependency status

### Problem

Optional capability state must be explicit and license-aware.

### Optimization

Report:

- enabled/disabled
- install-on-start state
- module import result
- active model name
- model root
- model store status
- available models
- wheelhouse state
- OpenCV conflict state
- relevant license notice location if available

### Speed impact

Low.

### Stability impact

High.

### Verification

Mock-based tests only. No optional package or model download required.

---

# Priority 5: Harden Synology Photos And Session Integration

## 5.1 Preserve observed API behavior only

### Problem

Synology Photos behavior must be treated as observed behavior, not assumed behavior.

### Optimization

For behavior changes, record evidence through HAR, browser trace, direct API inspection, logs, or test fixtures.

Centralize request construction in handlers.

### Speed impact

Low.

### Stability impact

High.

### Verification

Tests for request parameters, error mapping, remote API names, and retry behavior.

## 5.2 Improve Photos lookup caching with invalidation

### Problem

Photos lookups can be expensive, but stale cache can corrupt writes.

### Optimization

Cache only safe read-heavy data and invalidate after writes:

- folder ID by path
- items by folder
- persons by normalized name

Invalidation after:

- person creation
- face assignment
- item mutation
- explicit refresh

### Speed impact

Medium to High for large libraries.

### Stability impact

Medium.

### Verification

Tests for cache hit, invalidation, and no stale cache before sensitive write verification.

---

# Priority 6: Frontend Modernization Without Framework Rewrite

## 6.1 Extract DSM API client from `App.vue`

### Problem

Root UI code contains DSM credential context, API calls, timeout mapping, error formatting, polling helpers, and display helpers.

### Optimization

Create focused modules:

- `ui/src/services/dsm-api-client.js`
- `ui/src/services/backend-error-formatter.js`
- `ui/src/services/runtime-polling.js`

Keep DSM app registration intact.

### Speed impact

Low.

### Stability impact

High.

### Verification

Tests or focused checks for token/cookie/context handling, endpoint timeouts, and error formatting.

## 6.2 Keep Vue 2 unless DSM compatibility is proven

### Problem

A Vue 3 or build-tool migration could break DSM integration.

### Recommendation

Do not prioritize framework migration. First modularize current Vue 2 code.

### Speed impact

Conditional.

### Stability impact

Conditional to negative unless proven.

---

# Priority 7: Performance Work Only After Profiling

## 7.1 Face matching optimization

Only optimize if profiling shows IoU matching dominates runtime.

Possible improvements:

- group by image/source
- coordinate-range prefilter
- avoid incompatible source comparisons
- preserve deterministic sorting

Speed impact: Conditional, potentially Medium to High.

Stability impact: Medium if tests preserve exact results.

## 7.2 Image path listing optimization

Only optimize if large library scan startup is slow.

Possible improvements:

- preparing status before listing
- deterministic candidate cache with config fingerprint
- explicit refresh
- streaming candidates where practical

Speed impact: Conditional, potentially High.

Stability impact: Medium.

## 7.3 Separate face-detection worker

Only consider if optional detection blocks the API process or causes model lifecycle instability.

Keep optional dependencies explicit. Do not add hidden model downloads or silent package installs.

Speed impact: Conditional.

Stability impact: Conditional.

---

# Priority 8: Test And Diagnostic Improvements

## 8.1 Status payload contract tests

Add or extend backend tests for schema version, operation, mode, action, progress kind, relevant counters, blocked operation payload, and stale stopping behavior.

Speed impact: Indirect.

Stability impact: High.

## 8.2 UI status contract tests

Add or extend UI/static tests for schema counters, no legacy reconstruction, no duplicate status line, reconnect rules, scan/findings separation, and scoped `stop_requested`.

Speed impact: Indirect.

Stability impact: High.

## 8.3 Large-library synthetic performance tests

Measure:

- scan setup time
- per-file processing time
- findings append/write time
- status endpoint time
- memory use where practical
- Photos API call count when mocked

Speed impact: Indirect.

Stability impact: Medium.

## 8.4 Structured operation logging

Add operation-aware diagnostics without secrets:

- operation
- action
- mode
- operation_id
- revision
- phase
- safe object identity
- error code
- retryable flag

Speed impact: Low.

Stability impact: Medium to High.

---

# Explicit Non-Goals

Do not prioritize:

- full backend rewrite to Go, Rust, Java, or Node
- rewriting face detection in Rust or Go
- Vue 3 migration without DSM proof
- hidden dependency or model downloads
- broad guessed fallback or retry logic
- storage migration before storage abstraction exists

---

# Suggested Implementation Order

| Order | Work package | Speed impact | Stability impact |
|---:|---|---|---|
| 1 | Add status payload contract tests | Indirect | High |
| 2 | Add UI status contract tests | Indirect | High |
| 3 | Centralize status builders | Low | High |
| 4 | Add shared runtime polling layer | Medium | High |
| 5 | Extract write lock service | Low | High |
| 6 | Normalize save-only findings persistence | Medium | High |
| 7 | Introduce runtime operation identity | Medium | High |
| 8 | Modularize `ImgDataService` by workflow | Medium | High |
| 9 | Add findings storage abstraction | Medium | High |
| 10 | Add findings pagination | High | Medium to High |
| 11 | Move lifecycle complexity into Python helper | Low to Medium | High |
| 12 | Improve optional dependency status | Low | High |
| 13 | Improve Photos lookup caching | Medium to High | Medium |
| 14 | Split metadata parsers by schema | Low | Medium to High |
| 15 | Profile large scans before optimizing matching/listing | Conditional | Medium |
| 16 | Evaluate SQLite behind abstraction | High | High |
