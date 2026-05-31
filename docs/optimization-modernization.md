# Optimization And Modernization Plan

## Purpose

This document is the single consolidated optimization and modernization plan for `av_imgdata`.

It replaces the older optimization planning documents:

- `docs/optimization-modernization-plan.md`
- `docs/optimization-modernization-reassessment.md`

It is based on the current source state on `main` and on the status rules defined in:

- `docs/architecture-and-development-guidelines.md`
- `docs/status-concept-integrated.md`

## Validation Snapshot

Validated against current source on `main`.

Confirmed implemented or materially started:

- `src/services/status_payload_builder.py` exists and builds schema version 1 status payloads.
- Checks and FaceMatch status payload builders are implemented inside `StatusPayloadBuilder`.
- Counter relevance filtering and `show_when_zero` handling are implemented in the status builder.
- `src/services/runtime_operation_service.py` exists and contains operation IDs, revisions, timestamps, stale stopping detection, and blocked-operation payload construction.
- `src/services/write_lock_service.py` exists and provides non-blocking keyed write locks with structured conflict error creation through `ImgDataService`.
- `ui/src/services/runtime-polling.js` exists and implements named runtime polling with `skipIfPending`, pending state, run IDs, and `finally` cleanup.
- `src/parser/metadata_parser.py` delegates schema-specific parsing to ACD, Microsoft, and MWG parser modules.
- `FileAnalysisService` remains JSON-backed and provides current persisted findings/runtime-state primitives.

Confirmed remaining structural issues:

- `src/imgdata.py` still owns too much workflow and runtime orchestration: progress dictionaries, thread references, stop requests, candidate caches, runtime context, Photos access, metadata reads, findings handling, and mutation flow coordination.
- `ui/src/App.vue` still contains DSM API client behavior, backend error formatting, DSM credential context handling, endpoint timeout mapping, and root-component coordination.
- Runtime identity is implemented as primitives, but the plan must still prove consistent use across file analysis, checks, face match, and cleanup.
- Findings persistence exists as JSON primitives, but no storage boundary exists that can support cheap status reads, page reads, or future SQLite evaluation.

## Planning Rules

- Do not guess. Verify current implementation, tests, logs, HAR data, DSM behavior, or source state before changing logic.
- Keep every work package behavior-preserving unless the behavior change is explicitly documented and tested.
- Do not add broad fallback or retry behavior without an observed failure mode.
- Do not add more status/runtime logic directly to `src/imgdata.py`.
- Do not make API routes workflow owners.
- Do not optimize Photos cache, matching, image listing, or storage format before the necessary tests and measurement boundaries exist.
- Do not introduce hidden dependency downloads or license-sensitive assets.

## Evaluation Scale

| Rating | Meaning |
|---|---|
| High | broad or clearly measurable benefit |
| Medium | benefit in specific flows or larger libraries |
| Low | minor or indirect benefit |
| Conditional | only useful after profiling, logs, HAR data, or reproduced evidence |

## Status Categories

| Status | Meaning |
|---|---|
| Done | Implemented in current source; keep tests and do not reopen without evidence. |
| Partial | Implemented partly; remaining scope is still relevant. |
| Open | Not implemented or not sufficiently represented in the source. |
| Deferred | Intentionally not next; depends on evidence or prerequisite work. |

---

# Critical Path

The next work should follow this sequence. Later items should not start before the gating item above them is protected by tests.

```text
A. Runtime/status contract tests
B. Runtime identity consistency across long-running operations
C. Save-only findings correctness
D. Write-lock coverage
E. Extract workflow orchestration from ImgDataService, one seam at a time
F. UI root-component service extraction
G. Findings storage abstraction
H. Findings pagination and only then storage-format evaluation
```

Rationale:

- Runtime/status behavior is already important user-visible behavior. It must be protected before large extraction.
- Findings correctness affects interrupted scans, reconnect, and stored review state. It is more urgent than performance work.
- `ImgDataService` extraction is necessary, but doing it before contract tests raises regression risk.
- Storage and pagination work should wait until status and findings semantics are stable.

---

# Priority 0: Contract Safety Before Further Extraction

## 0.1 Strengthen backend status contract tests

Status: Open / highest immediate gate.

### Why this is first

The status builder and runtime service already exist. The next steps will move behavior across service boundaries. Without contract tests, extraction can silently change API shape, counter relevance, or reconnect behavior.

### Required tests

Add or strengthen backend tests for:

- `StatusPayloadBuilder.payload`
- `StatusPayloadBuilder.checks_payload`
- `StatusPayloadBuilder.face_match_payload`
- `RuntimeOperationService.stamp_progress`
- `RuntimeOperationService.blocked_by_running_operation_payload`
- stale stopping detection
- schema version 1
- operation, action, mode, and phase fields
- progress kind and numeric coercion
- relevant counters only
- irrelevant zero counters omitted
- `show_when_zero` retained only where intended

### Acceptance criteria

- Checks save-only scan status contains `findings` and only valid auto-resolve counters.
- Checks findings review status contains only action counters: `resolved`, `ignored`, `skipped`, `errors` when relevant.
- FaceMatch save-only scan status contains `findings` and does not show transfer counters.
- FaceMatch apply/transfer status contains `transferred`, optional `skipped`, optional `errors`, and no fake findings counter.
- Blocked operation payload returns `blocked_by_running_operation: true`, `mode: "none"`, `phase: "blocked"`, and the running operation identity.
- Finished progress does not become active only because `current == total`.

Speed impact: Indirect.

Stability impact: High.

## 0.2 Strengthen UI/static status contract tests

Status: Open / highest immediate gate.

### Required tests

Add or strengthen UI/static tests for:

- schema counters are preferred over legacy raw fields
- no legacy counter reconstruction when `status.schema_version == 1`
- no duplicate status line under visible progress
- scan progress does not overwrite active findings mode
- reconnect does not overwrite active findings review
- `stop_requested` is scoped to matching operation, mode, and action
- `runtime-polling.js` skips overlapping runtime progress polls only when `skipIfPending` is enabled
- normal status, config, ExifTool, pip package, and findings status requests do not use the runtime polling guard

### Acceptance criteria

- UI renders exactly the counters sent by schema status when schema version 1 is present.
- Active stored review state remains visible until a backend mutation response replaces, resolves, skips, ignores, or clears it.
- Skipped runtime polling ticks do not increment request ID, revision, or stale detection state.
- Polling communication errors do not mark a backend operation failed.

Speed impact: Indirect.

Stability impact: High.

---

# Priority 1: Runtime Correctness And State Ownership

## 1.1 Complete runtime identity consistency across all long-running operations

Status: Partial.

### Current state

`RuntimeOperationService` centralizes useful primitives:

- `operation_id`
- `revision`
- `last_updated_at`
- stale stopping detection
- blocked-operation response construction

### Remaining work

Apply the same runtime identity model consistently across:

- file analysis
- checks
- face match
- cleanup

Required fields for persisted or polled long-running progress:

- `operation`
- `action` or check type
- `mode`
- `operation_id`
- `revision`
- `phase`
- `running`
- `stop_requested`
- `last_updated_at`
- structured error context where relevant

### Implementation guidance

- Introduce helper methods instead of duplicating progress stamping logic in workflow code.
- Keep existing payload names and legacy fields while adding missing normalized identity fields.
- Do not change UI-visible strings unless tests are updated deliberately.
- Normalize stale stopping behavior through `RuntimeOperationService`; do not add per-flow ad hoc timeout rules.

### Acceptance criteria

- Every long-running operation writes or exposes operation identity consistently.
- Older progress responses cannot overwrite newer ones.
- Reconnect applies only matching operation, mode, and action.
- Cross-operation blocking reports the running operation identity.
- Stale stopping timeout behaves consistently across supported operations.
- `stop_requested` is scoped to the operation, mode, and action that produced it.

Speed impact: Medium.

Stability impact: High.

## 1.2 Finish save-only findings persistence and resume correctness

Status: Partial.

### Current state

JSON-backed persisted findings and runtime-state primitives exist in `FileAnalysisService`. Status and stored review behavior have improved.

### Remaining work

Ensure Checks and FaceMatch consistently:

- debounce findings writes during scans
- force-write findings on `stopped`, `failed`, and `finished`
- resume using persisted findings
- build skip lists from resume cursor and persisted entries
- report current stored findings count from stored findings, not old completed progress
- keep the visible review item stable until backend mutation response

### Implementation guidance

- Treat persisted findings as authoritative for current stored list state.
- Treat completed progress counts as historical once findings have changed.
- Keep scan mode and findings mode separate.
- Avoid replacing persisted findings with worker-local partial state on final write.
- Use entry tokens or equivalent stable identity to avoid duplicate append on resume.

### Acceptance criteria

- Stopped scan keeps already written findings.
- Failed scan keeps already written findings.
- Finished scan force-writes final findings once.
- Resume appends without replacing existing persisted entries.
- Resume does not duplicate entries already stored before interruption.
- Empty stored list reports zero even if historical progress contains a higher count.
- Stored review item remains visible until backend replaces, resolves, skips, ignores, or clears it.

Speed impact: Medium.

Stability impact: High.

## 1.3 Complete write-lock coverage and tests

Status: Partial.

### Current state

`WriteLockService` exists and keyed non-blocking write locks are integrated through `ImgDataService`.

### Remaining work

Verify and, if needed, extend lock coverage for:

- metadata path
- sidecar path
- Photos face
- Photos item
- person-related operations where required

Conflict responses should include:

- code
- phase
- retryable flag
- affected object identity
- stable message key

### Implementation guidance

- Keep lock keys deterministic and narrow enough that unrelated writes do not block each other.
- Lock the smallest safe target, but include all targets changed by a mutation.
- Do not introduce blocking waits in request handlers unless explicitly justified.
- Prefer immediate structured conflict responses for concurrent writes.

### Acceptance criteria

- Same metadata target writes conflict.
- Same Photos face writes conflict.
- Same Photos item writes conflict.
- Unrelated writes do not block each other.
- Conflict responses include phase and object identity.
- UI receives retryability information.
- Retrying writes requires either idempotency or a known safe condition.

Speed impact: Low.

Stability impact: High.

---

# Priority 2: Controlled Backend Decomposition

## 2.1 Extract runtime state handling from `ImgDataService`

Status: Open.

### Problem

`ImgDataService` still stores progress dictionaries, thread references, stop requests, active context, candidate caches, and operation start locks directly.

### Target

Create a focused runtime state boundary before moving full workflows.

Possible module:

```text
src/services/runtime_state_service.py
```

### Responsibilities

- hold per-operation progress state
- stamp progress through `RuntimeOperationService`
- read/write persisted runtime state where needed
- manage stop request state
- expose current running operation for cross-operation blocking
- normalize stale stopping decisions

### Acceptance criteria

- Existing API responses are unchanged.
- Cross-operation blocking behavior is unchanged or better covered by tests.
- Checks, FaceMatch, cleanup, and file analysis progress reads still work.
- No workflow logic moves into routes.

Speed impact: Low.

Stability impact: High.

## 2.2 Extract Checks workflow seam

Status: Open.

### Target

Move Checks-specific orchestration out of `ImgDataService` after runtime state is protected.

Possible module:

```text
src/services/checks_workflow_service.py
```

### Responsibilities

- checks scan start/stop orchestration
- candidate listing for checks
- save-only findings writes
- stored findings review mutations
- auto-apply/rebuild flow
- checks progress/status construction through existing builders

### Acceptance criteria

- Checks scan behavior is unchanged.
- Checks stored findings review behavior is unchanged.
- Checks auto-apply resume cursor semantics are unchanged.
- Finding counts and processed-entry token filtering are unchanged.
- Existing focused Checks tests pass.
- No duplicated Checks workflow appears in API routes.

Speed impact: Low to Medium.

Stability impact: High.

## 2.3 Extract FaceMatch workflow seam

Status: Open.

### Target

Move FaceMatch-specific orchestration out of `ImgDataService` after runtime state and mutation contracts are protected.

Possible module:

```text
src/services/face_match_workflow_service.py
```

### Responsibilities

- face match scan start/stop orchestration
- candidate listing for face match
- save-only findings writes
- stored findings review mutations
- transfer/create/assign/apply coordination
- result action locking coordination
- face match progress/status construction through existing builders

### Acceptance criteria

- FaceMatch scan behavior is unchanged.
- FaceMatch stored findings review behavior is unchanged.
- Interactive result actions do not double-trigger.
- Generic finished messages do not hide usable results.
- Existing focused FaceMatch tests pass.
- No duplicated FaceMatch workflow appears in API routes.

Speed impact: Low to Medium.

Stability impact: High.

## 2.4 Keep API routes thin after service extraction

Status: Partial.

### Target

Route handlers should remain adapters. They may parse request input and attach standard response wrappers, but they should not own workflow behavior.

### Delegate after service extraction

- status attachment
- runtime mutation responses
- finding mutation responses
- mapping updates
- ignore-list updates
- Photos assignment workflows
- metadata writes

### Acceptance criteria

- Mutation routes return current status, current item, or list state where relevant.
- Routes do not duplicate multi-step write workflows.
- Shared workflows remain in services.
- Route tests assert response shape, not internal service implementation.

Speed impact: Low.

Stability impact: High.

---

# Priority 3: UI Decomposition Without Behavior Changes

## 3.1 Keep runtime polling service stable

Status: Done for extraction; keep contract tests.

### Current state

`ui/src/services/runtime-polling.js` exists and implements the core polling guard.

### Acceptance criteria

- Runtime progress polling uses the guard only when requested.
- Normal status/config/finding status calls bypass the guard.
- Pending state resets in `finally`.
- Reconnect can restart polling.
- Communication errors do not mark backend operations failed.

Speed impact: Low.

Stability impact: High.

## 3.2 Extract DSM API client behavior from `App.vue`

Status: Open.

### Target module

```text
ui/src/services/dsm-api-client.js
```

### Responsibilities

- DSM credential resume context
- SynoToken extraction
- cookie collection
- request payload construction
- endpoint timeout mapping
- response data normalization

### Acceptance criteria

- Token, cookie, and resume context handling remain unchanged.
- Endpoint-specific timeouts remain unchanged.
- All existing callers continue to receive the same response data shape.
- DSM app registration remains untouched.

Speed impact: Low to Medium.

Stability impact: High.

## 3.3 Extract backend error formatting from `App.vue`

Status: Open.

### Target module

```text
ui/src/services/backend-error-formatter.js
```

### Responsibilities

- backend error detail rendering
- retryable flag rendering
- phase/path/person/face/item formatting
- translation-key fallback handling

### Acceptance criteria

- Existing translated error messages remain complete.
- Conflict errors still show code, phase, affected object identity, and retryability.
- Existing UI flows continue to display backend errors without additional local reconstruction.

Speed impact: Low.

Stability impact: Medium to High.

---

# Priority 4: Findings Storage Boundary

## 4.1 Add a findings storage abstraction

Status: Open / only JSON primitives exist.

### Problem

`FileAnalysisService` currently provides JSON-backed primitives, but there is no separate storage boundary for cheap status reads, page reads, or future alternate storage.

### Target module

Possible module:

```text
src/services/findings_storage_service.py
```

JSON remains the first backend.

### Required operations

- read findings status
- read current entry
- read page of entries
- append entries
- update one entry
- remove one entry
- ignore one entry
- resolve one entry
- force flush
- read runtime state
- write runtime state

### Acceptance criteria

- Atomic JSON writes remain used.
- Existing JSON files remain readable.
- Status reads do not materialize full findings lists where avoidable.
- Mutation responses return current status and current item.
- Invalid state files fail safely.
- No SQLite dependency is introduced in this step.

Speed impact: Medium.

Stability impact: High.

## 4.2 Add findings pagination after storage abstraction

Status: Open.

### Required API semantics

- total open entries
- current item
- page size
- cursor or index
- mutation response with next current item

### Acceptance criteria

- First page load works.
- Next item after resolve works.
- Next item after ignore works.
- Empty list returns explicit zero status.
- Visible current item remains stable during action in flight.
- Historical progress count does not override current findings count.

Speed impact: High for large libraries.

Stability impact: Medium to High.

## 4.3 Evaluate SQLite only behind findings storage abstraction

Status: Deferred.

SQLite can improve large-list storage, but direct migration remains risky.

Evaluate only after:

- findings storage abstraction exists
- status/finding APIs use the abstraction
- tests define expected behavior
- large-list performance evidence justifies the change

Candidate tables may include:

```sql
operations(operation_id, operation, action, mode, phase, revision, started_at, updated_at, payload_json)
findings(id, finding_type, action, entry_token, status, payload_json, created_at, updated_at)
ignore_entries(ignore_type, entry_token, payload_json, created_at)
```

### Acceptance criteria for any SQLite step

- Existing JSON remains source-safe during migration.
- Migration is deterministic and idempotent.
- Failed migration does not delete JSON source data.
- Package start remains functional without manual DSM repair.

Speed impact: High for large libraries.

Stability impact: High if behind abstraction; lower if done directly.

---

# Priority 5: Existing Parser Split And Metadata Safety

## 5.1 Keep metadata parser split stable

Status: Done for parser split; keep regression coverage.

### Current state

`MetadataParser` delegates schema-specific parsing to dedicated parser modules.

### Required preservation rules

- source format
- source identity
- orientation handling
- MWG `AppliedToDimensions`
- dimension mismatch warnings
- unnamed ACD opt-in behavior
- denied ACD names
- coordinate precision helpers

### Acceptance criteria

Fixture tests cover:

- ACD named faces
- unnamed ACD opt-in behavior
- denied ACD names
- Microsoft regions
- MWG regions
- MWG `AppliedToDimensions`
- orientation handling
- dimension mismatch context
- source format and source identity preservation

Speed impact: Low.

Stability impact: Medium to High.

---

# Priority 6: Packaging, Dependencies, And Runtime Diagnostics

## 6.1 Move complex lifecycle shell logic into Python helpers

Status: Open.

### Problem

DSM lifecycle shell scripts must remain, but pip, wheelhouse, manifest, and optional package logic are easier to test in Python.

### Target

Keep shell as DSM wrapper. Move complex behavior into a helper such as:

```text
src/package_runtime.py
```

or:

```text
scripts/runtime_helper.py
```

### Responsibilities

- validate core packages
- validate optional package config
- prepare wheelhouse
- install from manifest
- validate InsightFace/OpenCV status
- write status JSON
- return clear exit codes

### Acceptance criteria

- Missing venv is reported clearly.
- Missing core packages are reported clearly.
- Disabled optional packages do not block startup.
- Invalid wheelhouse manifest is reported clearly.
- OpenCV conflicts are reported without hidden package changes.
- Startup remains possible without optional packages.
- Shell wrapper remains DSM-compatible.

Speed impact: Low to Medium.

Stability impact: High.

## 6.2 Improve optional dependency status

Status: Open / not fully proven.

### Required status fields

Report optional capability state explicitly:

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

### Acceptance criteria

- Mock-based tests cover all status branches.
- No optional package or model download is required for tests.
- Disabled optional dependencies do not produce error status.
- License notice location is visible when applicable.

Speed impact: Low.

Stability impact: High.

---

# Priority 7: Conditional Performance Work

## 7.1 Improve Photos lookup caching only with explicit invalidation

Status: Partial / needs invalidation proof.

### Current state

Photos lookup cache objects exist and are used in scan context and service code.

### Required invalidation points

Cache only safe read-heavy data and invalidate after writes:

- folder ID by path
- items by folder
- persons by normalized name

Invalidation after:

- person creation
- face assignment
- item mutation
- explicit refresh

### Acceptance criteria

- Cache hit on repeated safe reads.
- Invalidation after person creation.
- Invalidation after face assignment.
- Invalidation after item mutation.
- No stale cache before sensitive write verification.

Speed impact: Medium to High for large libraries.

Stability impact: Medium.

## 7.2 Face matching optimization after profiling only

Status: Deferred.

Only optimize if profiling shows IoU matching dominates runtime.

Possible improvements:

- group by image/source
- coordinate-range prefilter
- avoid incompatible source comparisons
- preserve deterministic sorting

Acceptance criteria before implementation:

- profiling data shows matching dominates runtime
- fixture tests preserve exact matching results and order
- no incompatible source comparisons are introduced

Speed impact: Conditional, potentially Medium to High.

Stability impact: Medium if tests preserve exact results.

## 7.3 Image path listing optimization after profiling only

Status: Deferred.

Only optimize if large library scan startup is slow.

Possible improvements:

- preparing status before listing
- deterministic candidate cache with config fingerprint
- explicit refresh
- streaming candidates where practical

Acceptance criteria before implementation:

- profiling or logs show listing dominates startup time
- candidate ordering remains deterministic
- cache invalidation has an explicit refresh path
- status is written before expensive listing starts

Speed impact: Conditional, potentially High.

Stability impact: Medium.

---

# Explicit Non-Goals

Do not prioritize:

- full backend rewrite to Go, Rust, Java, or Node
- rewriting face detection in Rust or Go
- Vue 3 migration without DSM proof
- hidden dependency or model downloads
- broad guessed fallback or retry logic
- storage migration before storage abstraction exists
- performance work without profiling, logs, HAR data, or reproduced evidence

---

# Detailed Implementation Order

| Order | Work package | Status | Priority | Must precede | Speed impact | Stability impact |
|---:|---|---|---:|---|---|---|
| 1 | Backend status contract tests | Open | 0 | runtime extraction | Indirect | High |
| 2 | UI/static status contract tests | Open | 0 | UI/root extraction | Indirect | High |
| 3 | Complete runtime identity across all long-running operations | Partial | 1 | workflow extraction | Medium | High |
| 4 | Finish save-only findings persistence and resume correctness | Partial | 1 | findings abstraction | Medium | High |
| 5 | Complete write-lock coverage and tests | Partial | 1 | workflow extraction | Low | High |
| 6 | Extract runtime state handling from `ImgDataService` | Open | 2 | Checks/FaceMatch extraction | Low | High |
| 7 | Extract Checks workflow seam | Open | 2 | route cleanup | Low to Medium | High |
| 8 | Extract FaceMatch workflow seam | Open | 2 | route cleanup | Low to Medium | High |
| 9 | Keep API routes thin after service extraction | Partial | 2 | broader backend cleanup | Low | High |
| 10 | Extract DSM API client from `App.vue` | Open | 3 | UI cleanup | Low to Medium | High |
| 11 | Extract backend error formatter from `App.vue` | Open | 3 | UI cleanup | Low | Medium to High |
| 12 | Add findings storage abstraction | Open | 4 | pagination/SQLite | Medium | High |
| 13 | Add findings pagination | Open | 4 | SQLite evaluation | High for large libraries | Medium to High |
| 14 | Keep metadata parser split stable with tests | Done | 5 | parser changes | Low | Medium to High |
| 15 | Move lifecycle complexity into Python helper | Open | 6 | optional dependency cleanup | Low to Medium | High |
| 16 | Improve optional dependency status | Open | 6 | optional model work | Low | High |
| 17 | Improve Photos lookup caching with invalidation proof | Partial | 7 | broader cache/perf work | Medium to High | Medium |
| 18 | Profile before optimizing matching/listing | Deferred | 7 | matching/listing optimization | Conditional | Medium |
| 19 | Evaluate SQLite behind abstraction | Deferred | 7 | storage migration | High for large libraries | High |

## Current Decision

The next implementation step is not another broad refactor. The next step is contract coverage.

After contract coverage, complete runtime identity consistency, save-only findings correctness, and write-lock coverage. Only then extract workflow orchestration from `ImgDataService` one seam at a time.
