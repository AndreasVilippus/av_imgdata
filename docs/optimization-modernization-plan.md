# Optimization And Modernization Plan

## Purpose

This document lists optional optimizations and modernizations for `av_imgdata`, sorted by current priority and evaluated by expected speed and stability impact.

It follows:

- `docs/architecture-and-development-guidelines.md`
- `docs/status-concept-integrated.md`

The plan reflects the current status implementation on `main`. The status concept is now partially implemented, so the highest-value work has shifted from defining status semantics to extracting the implemented status/runtime primitives out of `ImgDataService` and finishing consistency across all long-running operations.

## Rating Scale

| Rating | Meaning |
|---|---|
| High | broad or clearly measurable benefit |
| Medium | benefit in specific flows or larger libraries |
| Low | minor or indirect benefit |
| Conditional | only useful after profiling, logs, HAR data, or reproduced evidence |

## Current Implementation Baseline

The repository already contains relevant status work:

- schema version 1 status payload builders exist in `ImgDataService`
- Checks and FaceMatch status payloads exist
- relevant counter filtering exists
- Checks progress writes `operation_id` and `revision`
- cross-operation blocking exists
- runtime polling has an opt-in `skipIfPending` guard
- saved findings and stored review behavior have been improved

Remaining issue: much of this logic still lives inside `src/imgdata.py` and `ui/src/App.vue`. Further work should avoid adding more status/runtime behavior to those broad files.

---

# Priority 1: Extract And Stabilize Status/Runtime Foundations

## 1.1 Extract status payload builders from `ImgDataService`

### Problem

Status semantics are now implemented, but the implementation is still embedded in `ImgDataService`. This increases the size and responsibility of `src/imgdata.py`.

### Optimization

Extract status construction into focused services, for example:

```text
src/services/status_payload_builder.py
src/services/checks_status_builder.py
src/services/face_match_status_builder.py
```

Exact names may follow existing project conventions.

### Required behavior

Preserve current response shapes exactly:

- `status.schema_version == 1`
- `status.operation`
- `status.action`
- `status.mode`
- `status.phase`
- `status.progress`
- `status.counters`
- relevant counters only
- no irrelevant zero counters
- `show_when_zero: true` behavior
- blocked response with `mode: "none"` and `phase: "blocked"`

### Speed impact

Low.

### Stability impact

High.

### Verification

- Existing status payload tests pass unchanged.
- No API response shape changes.
- Checks save-only scan still sends only `findings`.
- Checks findings review still sends only action counters.
- FaceMatch save-only scan still sends only `findings`.
- FaceMatch auto-transfer still sends `transferred`, optional `skipped`, optional `errors`.
- Finished progress still does not display as active only because `current == total`.

## 1.2 Complete runtime operation identity for all long-running operations

### Problem

Runtime identity is partly present. Checks already writes `operation_id` and `revision`, but the model should be consistent across all long-running operations.

### Optimization

Apply a shared runtime operation model to:

- file analysis
- checks
- face match
- cleanup

Required fields:

- `operation`
- `action` or `check_type`
- `mode`
- `operation_id`
- `revision`
- `phase`
- `running`
- `stop_requested`
- updated timestamp
- structured error context where relevant

### Speed impact

Medium.

### Stability impact

High.

### Verification

- Older progress responses cannot overwrite newer ones.
- Reconnect applies only matching operation/mode/action.
- Cross-operation blocking reports the running operation identity.
- Stale stopping timeout behaves consistently.
- `stop_requested` is scoped to the operation/mode/action that produced it.

## 1.3 Extract write locking into a dedicated service

### Problem

Metadata and Synology Photos writes can collide on the same image, sidecar, face, item, or person operation. Locking should not remain mixed into broad orchestration.

### Optimization

Create a focused write-lock service, for example:

```text
src/services/write_lock_service.py
```

Lock keys should cover:

- metadata path
- sidecar path
- Photos face
- Photos item
- relevant person operations if needed

Conflicts should return structured errors with:

- code
- phase
- retryable flag
- affected object identity
- translated message key

### Speed impact

Low.

### Stability impact

High.

### Verification

- Same-target writes conflict.
- Unrelated writes do not block each other.
- Conflict responses include phase and object identity.
- Retrying writes requires an idempotency argument or known safe condition.

## 1.4 Finish save-only findings persistence and resume correctness

### Problem

Stored findings and historical progress handling have improved, but save-only correctness remains critical for interrupted scans and UI reconnect.

### Optimization

Ensure Checks and FaceMatch consistently:

- debounce findings writes during scans
- force-write findings on `stopped`, `failed`, and `finished`
- resume using persisted findings
- build skip lists from resume cursor and persisted entries
- report current stored findings count from stored findings, not old completed progress
- keep the visible review item stable until backend mutation response

### Speed impact

Medium.

### Stability impact

High.

### Verification

- Stopped scan keeps written findings.
- Failed scan keeps written findings.
- Resume appends without replacing existing persisted entries.
- Empty stored list reports zero even if historical progress contains a higher count.
- Stored review item remains visible until backend replaces, resolves, skips, ignores, or clears it.

## 1.5 Extract status/runtime subset from `src/imgdata.py`

### Problem

The original plan listed broad `ImgDataService` decomposition as Priority 2. After the status implementation, the status/runtime subset has become the immediate architectural bottleneck.

### Optimization

Do not add more status/runtime logic directly to `src/imgdata.py`. Extract the implemented primitives first:

- status payload builders
- phase derivation
- operation ID and revision handling
- cross-operation blocked response builder
- stale stopping detection
- write conflict handling

### Speed impact

Low to Medium.

### Stability impact

High.

### Verification

- Behavior-preserving extraction only.
- No route/API response shape changes.
- Existing focused tests pass unchanged.
- No new fallback behavior without observed failure mode.

---

# Priority 2: Continue Backend And UI Decomposition

## 2.1 Extract runtime polling from `App.vue`

### Problem

`App.vue` contains useful runtime polling behavior, including `skipIfPending`, but this keeps infrastructure logic in the root component.

### Optimization

Move polling behavior into a focused module, for example:

```text
ui/src/services/runtime-polling.js
```

Preserve:

- stable `poll_key`
- opt-in `skipIfPending`
- local pending state
- run ID protection
- pending reset in `finally`
- skipped ticks not changing request ID or revision
- normal status/config requests bypassing the runtime polling guard

### Speed impact

Low to Medium.

### Stability impact

High.

### Verification

- Runtime progress polling uses the guard.
- Normal status/config/finding status calls do not use the guard.
- Polling errors do not mark backend operations as failed.
- Reconnect can restart polling.

## 2.2 Strengthen status and UI contract tests

### Problem

Status behavior is implemented across backend and UI. Tests should protect that behavior before further refactoring.

### Optimization

Add or strengthen tests for:

- generic status builder
- Checks status builder
- FaceMatch status builder
- blocked operation payload
- schema counter rendering
- no legacy counter reconstruction when schema version 1 exists
- no duplicate status line under visible progress
- runtime polling guard behavior
- reconnect not overwriting active findings review

### Speed impact

Indirect.

### Stability impact

High.

## 2.3 Keep API routes thin after service extraction

### Problem

Route helpers that attach status are acceptable as a bridge, but route handlers should not become workflow owners.

### Optimization

After status/runtime services exist, route handlers should delegate:

- status attachment
- runtime mutation responses
- finding mutation responses
- mapping updates
- ignore-list updates
- Photos assignment workflows

### Speed impact

Low.

### Stability impact

High.

### Verification

- Mutation routes return enough updated state for the UI.
- Routes do not duplicate multi-step write workflows.
- Shared workflows remain in service code.

## 2.4 Refactor Checks and FaceMatch workflow orchestration out of `imgdata.py`

### Problem

`ImgDataService` still coordinates workflow logic, progress, caches, Photos access, metadata parsing, file access, and findings handling.

### Optimization

Extract focused workflow services after the status/runtime extraction:

```text
src/services/checks_workflow_service.py
src/services/face_match_workflow_service.py
```

Avoid broad rename-only refactors. Extract one workflow seam at a time.

### Speed impact

Medium, mostly indirect.

### Stability impact

High.

### Verification

- Behavior-preserving extraction.
- Existing Checks and FaceMatch tests pass.
- Status payloads remain unchanged.
- No duplicated write workflows in API routes.

---

# Priority 3: Improve Findings Storage And Metadata Modularity

## 3.1 Add findings storage abstraction

### Problem

Status correctness now depends strongly on persisted findings state. JSON files are simple, but large lists can make status reads and mutations expensive.

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

- Atomic JSON writes remain used.
- Status reads do not materialize full findings lists where avoidable.
- Mutation responses return current status/current item.
- Invalid state files fail safely.

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

- First page load works.
- Next item after resolve/ignore works.
- Empty list returns explicit zero status.
- Visible current item remains stable during action in flight.

## 3.3 Split metadata parsers by schema

### Problem

ACDSee, Microsoft, and MWG region parsing share a facade but have distinct semantics.

### Optimization

Keep `metadata_parser.py` as facade and split schema-specific logic into focused parser modules.

Preserve:

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

# Priority 4: Packaging, Dependencies, And Runtime Diagnostics

## 4.1 Move complex lifecycle shell logic into Python helpers

### Problem

The DSM lifecycle script must remain, but pip, wheelhouse, manifest, and optional package logic is easier to test in Python.

### Optimization

Keep shell as DSM wrapper. Move complex behavior into a helper such as:

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

# Priority 5: Conditional Performance Work

## 5.1 Photos lookup caching with explicit invalidation

### Problem

Synology Photos lookups can be expensive, but stale cache can corrupt writes.

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

- Cache hit on repeated safe reads.
- Invalidation after write.
- No stale cache before sensitive write verification.

## 5.2 Face matching optimization after profiling only

Only optimize if profiling shows IoU matching dominates runtime.

Possible improvements:

- group by image/source
- coordinate-range prefilter
- avoid incompatible source comparisons
- preserve deterministic sorting

Speed impact: Conditional, potentially Medium to High.

Stability impact: Medium if tests preserve exact results.

## 5.3 Image path listing optimization after profiling only

Only optimize if large library scan startup is slow.

Possible improvements:

- preparing status before listing
- deterministic candidate cache with config fingerprint
- explicit refresh
- streaming candidates where practical

Speed impact: Conditional, potentially High.

Stability impact: Medium.

## 5.4 SQLite evaluation behind storage abstraction only

SQLite can improve large-list storage, but direct migration remains risky.

Evaluate only after the findings storage abstraction and tests are stable.

Speed impact: High for large libraries.

Stability impact: High if behind abstraction.

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

# Revised Suggested Implementation Order

| Order | Work package | Priority | Speed impact | Stability impact |
|---:|---|---:|---|---|
| 1 | Extract status payload builders from `ImgDataService` | 1 | Low | High |
| 2 | Complete runtime operation identity for all long-running operations | 1 | Medium | High |
| 3 | Extract write lock service | 1 | Low | High |
| 4 | Finish save-only findings persistence and resume correctness | 1 | Medium | High |
| 5 | Extract status/runtime subset from `src/imgdata.py` | 1 | Low to Medium | High |
| 6 | Extract runtime polling from `App.vue` | 2 | Low to Medium | High |
| 7 | Strengthen status and UI contract tests | 2 | Indirect | High |
| 8 | Keep API routes thin after service extraction | 2 | Low | High |
| 9 | Refactor Checks and FaceMatch workflow orchestration out of `imgdata.py` | 2 | Medium | High |
| 10 | Add findings storage abstraction | 3 | Medium | High |
| 11 | Add findings pagination | 3 | High for large libraries | Medium to High |
| 12 | Split metadata parsers by schema | 3 | Low | Medium to High |
| 13 | Move lifecycle complexity into Python helper | 4 | Low to Medium | High |
| 14 | Improve optional dependency status | 4 | Low | High |
| 15 | Improve Photos lookup caching | 5 | Medium to High | Medium |
| 16 | Profile before optimizing matching/listing | 5 | Conditional | Medium |
| 17 | Evaluate SQLite behind abstraction | 5 | High for large libraries | High |

## Current Decision

Do not add more status/runtime logic directly to `src/imgdata.py`.

First extract the implemented status and runtime primitives into focused services. Then continue functional improvements on top of those service boundaries.
