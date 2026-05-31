# Optimization And Modernization Plan

## Purpose

This document is the single consolidated optimization and modernization plan for `av_imgdata`.

It replaces the older optimization planning documents:

- `docs/optimization-modernization-plan.md`
- `docs/optimization-modernization-reassessment.md`

It is based on the current source state on `main` and on the status rules defined in:

- `docs/architecture-and-development-guidelines.md`
- `docs/status-concept-integrated.md`

## Current Source Baseline

The current implementation already contains several items that were still open or only partially implemented in earlier optimization documents.

Implemented or materially started:

- `src/services/status_payload_builder.py` exists and builds schema version 1 status payloads.
- Checks and FaceMatch status payload builders are implemented inside `StatusPayloadBuilder`.
- Counter relevance filtering and `show_when_zero` handling are implemented in the status builder.
- `src/services/runtime_operation_service.py` exists and contains operation IDs, revisions, timestamps, stale stopping detection, and blocked-operation payload construction.
- `src/services/write_lock_service.py` exists and provides non-blocking keyed write locks with structured conflict error creation through `ImgDataService`.
- `ui/src/services/runtime-polling.js` exists and implements named runtime polling with `skipIfPending`, pending state, run IDs, and `finally` cleanup.
- `src/parser/metadata_parser.py` delegates schema-specific parsing to ACD, Microsoft, and MWG parser modules.
- `FileAnalysisService` remains JSON-backed and provides current persisted findings/runtime-state primitives.

Remaining structural issue:

- `src/imgdata.py` still owns too much workflow and runtime orchestration: progress dictionaries, thread references, stop requests, candidate caches, runtime context, Photos access, metadata reads, findings handling, and mutation flow coordination.
- `ui/src/App.vue` still contains DSM API client behavior, backend error formatting, DSM credential context handling, endpoint timeout mapping, and general root-component coordination.

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

# Priority 1: Stabilize Runtime And Extract Broad Orchestration

## 1.1 Finish runtime identity consistency across all long-running operations

Status: Partial.

### Current state

`RuntimeOperationService` exists and centralizes useful primitives:

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

Required fields should be present and semantically consistent where an operation is long-running:

- `operation`
- `action` or check type
- `mode`
- `operation_id`
- `revision`
- `phase`
- `running`
- `stop_requested`
- updated timestamp
- structured error context where relevant

### Verification

- Older progress responses cannot overwrite newer ones.
- Reconnect applies only matching operation, mode, and action.
- Cross-operation blocking reports the running operation identity.
- Stale stopping timeout behaves consistently.
- `stop_requested` is scoped to the operation, mode, and action that produced it.

Speed impact: Medium.

Stability impact: High.

## 1.2 Extract runtime/workflow orchestration out of `src/imgdata.py`

Status: Open.

### Problem

`ImgDataService` still coordinates too many responsibilities. The status/runtime primitives are now partly extracted, but the broad service still owns most workflow state and mutation coordination.

### Target extraction order

Extract one seam at a time. Do not perform broad rename-only refactors.

Suggested service boundaries:

```text
src/services/checks_workflow_service.py
src/services/face_match_workflow_service.py
src/services/cleanup_workflow_service.py
src/services/file_analysis_workflow_service.py
src/services/runtime_state_service.py
```

The exact names may follow existing project conventions.

### Required preservation rules

- No API response shape changes.
- Existing focused tests pass unchanged or are deliberately updated with matching behavior evidence.
- Status payloads remain schema version 1 compatible.
- No workflow duplication moves into API routes.
- No guessed fallback behavior is added without observed failure mode.

### Verification

- Checks scan, stored findings review, and auto-apply behavior stay unchanged.
- FaceMatch scan, stored findings review, and transfer/create/assign behavior stay unchanged.
- Cleanup and file analysis progress behavior stay unchanged.
- Route handlers remain thin after extraction.

Speed impact: Low to Medium.

Stability impact: High.

## 1.3 Finish save-only findings persistence and resume correctness

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

### Verification

- Stopped scan keeps already written findings.
- Failed scan keeps already written findings.
- Resume appends without replacing existing persisted entries.
- Empty stored list reports zero even if historical progress contains a higher count.
- Stored review item remains visible until backend replaces, resolves, skips, ignores, or clears it.

Speed impact: Medium.

Stability impact: High.

## 1.4 Complete write-lock coverage and tests

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
- translated message key or stable message key

### Verification

- Same-target writes conflict.
- Unrelated writes do not block each other.
- Conflict responses include phase and object identity.
- UI receives retryability information.
- Retrying writes requires either idempotency or a known safe condition.

Speed impact: Low.

Stability impact: High.

---

# Priority 2: Preserve Status Contracts And Continue UI Decomposition

## 2.1 Keep status payload builder behavior stable

Status: Done for central builder; Partial for contract coverage.

### Current state

`StatusPayloadBuilder` is extracted and implements:

- schema version 1 payloads
- phase derivation
- progress object construction
- counter object construction
- Checks status payloads
- FaceMatch status payloads
- relevant counter filtering
- `show_when_zero` behavior

### Remaining work

Only split Checks and FaceMatch status builders into separate modules if it reduces complexity without changing behavior. The current single builder is acceptable if tests protect it.

### Verification

- Existing status payload tests pass unchanged.
- No API response shape changes.
- Checks save-only scan sends only `findings` plus valid auto-resolve counters.
- Checks findings review sends only action counters.
- FaceMatch save-only scan sends only `findings`.
- FaceMatch auto-transfer sends `transferred`, optional `skipped`, optional `errors`.
- Finished progress does not display as active only because `current == total`.

Speed impact: Low.

Stability impact: High.

## 2.2 Strengthen backend and UI status contract tests

Status: Open / not yet sufficiently proven.

### Required backend tests

Add or strengthen tests for:

- generic status builder
- Checks status payloads
- FaceMatch status payloads
- blocked-operation payload
- schema version
- operation, mode, action, and phase
- progress kind
- relevant counters only
- irrelevant zero counters omitted
- stale stopping behavior

### Required UI/static tests

Add or strengthen tests for:

- schema counters are preferred
- no legacy counter reconstruction when `status.schema_version == 1`
- no duplicate status line under visible progress
- reconnect does not overwrite active findings review
- scan progress does not overwrite findings mode
- `stop_requested` is scoped to matching operation, mode, and action
- runtime polling guard behavior

Speed impact: Indirect.

Stability impact: High.

## 2.3 Keep API routes thin after service extraction

Status: Partial.

### Problem

Route helpers that attach status are acceptable as a bridge, but route handlers should not become workflow owners.

### Optimization

After status/runtime and workflow services exist, route handlers should delegate:

- status attachment
- runtime mutation responses
- finding mutation responses
- mapping updates
- ignore-list updates
- Photos assignment workflows
- metadata writes

Mutation responses must return enough updated state for the UI.

### Verification

- Mutation routes return current status, current item, or list state where relevant.
- Routes do not duplicate multi-step write workflows.
- Shared workflows remain in service code.

Speed impact: Low.

Stability impact: High.

## 2.4 Decompose `ui/src/App.vue` further

Status: Partial.

### Current state

Runtime polling has been extracted to `ui/src/services/runtime-polling.js`.

### Remaining work

Move remaining root-component behavior into focused modules:

```text
ui/src/services/dsm-api-client.js
ui/src/services/backend-error-formatter.js
```

Preserve DSM app registration and existing mixin/view structure.

### Candidate responsibilities

`dsm-api-client.js`:

- DSM credential context
- SynoToken and cookie handling
- request payload construction
- endpoint timeout mapping
- API response normalization

`backend-error-formatter.js`:

- backend error detail rendering
- retryable/phase/path/person/face/item formatting
- translation-key fallback handling

### Verification

- Token, cookie, and resume context handling remain unchanged.
- Endpoint-specific timeouts remain unchanged.
- Backend error messages remain translated and complete.
- Normal status/config requests do not use runtime polling guard.

Speed impact: Low to Medium.

Stability impact: High.

---

# Priority 3: Findings Storage And Metadata Modularity

## 3.1 Add a findings storage abstraction

Status: Open / only JSON primitives exist.

### Problem

`FileAnalysisService` currently provides JSON-backed primitives, but there is no separate storage boundary for future pagination or alternate storage.

### Optimization

Introduce a storage boundary before changing storage format:

- read findings status
- read current entry
- read page of entries
- append entries
- update, remove, ignore, or resolve one entry
- force flush
- read and write runtime state

JSON remains the first backend.

### Verification

- Atomic JSON writes remain used.
- Status reads do not materialize full findings lists where avoidable.
- Mutation responses return current status and current item.
- Invalid state files fail safely.

Speed impact: Medium.

Stability impact: High.

## 3.2 Add findings pagination after storage abstraction

Status: Open.

### Optimization

Support backend APIs for:

- total open entries
- current item
- page size
- cursor or index
- mutation response with next current item

### Verification

- First page load works.
- Next item after resolve or ignore works.
- Empty list returns explicit zero status.
- Visible current item remains stable during action in flight.

Speed impact: High for large libraries.

Stability impact: Medium to High.

## 3.3 Keep metadata parser split stable

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

### Verification

Fixture tests should cover ACD, Microsoft, MWG, orientation, dimensions, unnamed ACD, denied ACD names, and source identity.

Speed impact: Low.

Stability impact: Medium to High.

---

# Priority 4: Packaging, Dependencies, And Runtime Diagnostics

## 4.1 Move complex lifecycle shell logic into Python helpers

Status: Open.

### Problem

DSM lifecycle shell scripts must remain, but pip, wheelhouse, manifest, and optional package logic are easier to test in Python.

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

### Verification

- Missing venv is reported clearly.
- Missing core packages are reported clearly.
- Disabled optional packages do not block startup.
- Invalid wheelhouse manifest is reported clearly.
- OpenCV conflicts are reported without hidden package changes.
- Startup remains possible without optional packages.

Speed impact: Low to Medium.

Stability impact: High.

## 4.2 Improve optional dependency status

Status: Open / not fully proven.

### Optimization

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

### Verification

Use mock-based tests only. No optional package or model download is required.

Speed impact: Low.

Stability impact: High.

---

# Priority 5: Conditional Performance Work

## 5.1 Improve Photos lookup caching only with explicit invalidation

Status: Partial / needs invalidation proof.

### Current state

Photos lookup cache objects exist and are used in scan context and service code.

### Remaining work

Cache only safe read-heavy data and invalidate after writes:

- folder ID by path
- items by folder
- persons by normalized name

Invalidation after:

- person creation
- face assignment
- item mutation
- explicit refresh

### Verification

- Cache hit on repeated safe reads.
- Invalidation after write.
- No stale cache before sensitive write verification.

Speed impact: Medium to High for large libraries.

Stability impact: Medium.

## 5.2 Face matching optimization after profiling only

Status: Deferred.

Only optimize if profiling shows IoU matching dominates runtime.

Possible improvements:

- group by image/source
- coordinate-range prefilter
- avoid incompatible source comparisons
- preserve deterministic sorting

Speed impact: Conditional, potentially Medium to High.

Stability impact: Medium if tests preserve exact results.

## 5.3 Image path listing optimization after profiling only

Status: Deferred.

Only optimize if large library scan startup is slow.

Possible improvements:

- preparing status before listing
- deterministic candidate cache with config fingerprint
- explicit refresh
- streaming candidates where practical

Speed impact: Conditional, potentially High.

Stability impact: Medium.

## 5.4 Evaluate SQLite only behind findings storage abstraction

Status: Deferred.

SQLite can improve large-list storage, but direct migration remains risky.

Evaluate only after:

- findings storage abstraction exists
- status/finding APIs use the abstraction
- tests define expected behavior
- large-list performance evidence justifies the change

Speed impact: High for large libraries.

Stability impact: High if behind abstraction; lower if done directly.

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

# Consolidated Suggested Implementation Order

| Order | Work package | Status | Priority | Speed impact | Stability impact |
|---:|---|---|---:|---|---|
| 1 | Complete runtime identity across all long-running operations | Partial | 1 | Medium | High |
| 2 | Extract runtime/workflow orchestration out of `src/imgdata.py` | Open | 1 | Low to Medium | High |
| 3 | Finish save-only findings persistence and resume correctness | Partial | 1 | Medium | High |
| 4 | Complete write-lock coverage and tests | Partial | 1 | Low | High |
| 5 | Strengthen backend and UI status contract tests | Open | 2 | Indirect | High |
| 6 | Keep API routes thin after service extraction | Partial | 2 | Low | High |
| 7 | Decompose remaining `App.vue` service logic | Partial | 2 | Low to Medium | High |
| 8 | Add findings storage abstraction | Open | 3 | Medium | High |
| 9 | Add findings pagination | Open | 3 | High for large libraries | Medium to High |
| 10 | Keep metadata parser split stable with tests | Done | 3 | Low | Medium to High |
| 11 | Move lifecycle complexity into Python helper | Open | 4 | Low to Medium | High |
| 12 | Improve optional dependency status | Open | 4 | Low | High |
| 13 | Improve Photos lookup caching with invalidation proof | Partial | 5 | Medium to High | Medium |
| 14 | Profile before optimizing matching/listing | Deferred | 5 | Conditional | Medium |
| 15 | Evaluate SQLite behind abstraction | Deferred | 5 | High for large libraries | High |

## Current Decision

Do not add more status/runtime logic directly to `src/imgdata.py`.

First complete and verify the runtime identity model across all long-running operations, then extract workflow orchestration from `ImgDataService` one seam at a time. Continue functional improvements only on top of those service boundaries and protected status contracts.
