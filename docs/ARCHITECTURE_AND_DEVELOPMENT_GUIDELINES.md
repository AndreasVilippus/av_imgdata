# AV ImgData Architecture And Development Guidelines

## Purpose

This document defines the architectural rules, development constraints, and project premises for `av_imgdata`.

It is written to be:
- easy for humans to read
- easy for AI systems to evaluate
- strict enough to avoid recurring structural mistakes

When in doubt, this document takes precedence over ad hoc implementation preferences.
When this document summarizes a dedicated concept document, the concept document has correctness precedence for that topic.

Related development documents:

- `docs/status-concept-integrated.md` defines the detailed status schema and UI action-state matrix. It is the authoritative source for status/progress correctness.
- `tests/function_matrix.md` documents direct file-access and ExifTool-backed metadata paths.
- `dev/insightface_personenerkennung_konzept_codex.md` records the longer-term InsightFace recognition concept. The current implementation is detection-oriented and must not be treated as completed recognition.

## Core Principles

### MUST

- Keep changes narrow and task-focused.
- Reuse existing project patterns before introducing new abstractions.
- Prefer explicit logic over guessed fallback behavior.
- Preserve predictable behavior over convenience hacks.
- Keep frontend structure and backend structure simple and inspectable.
- Make code paths easy to trace during debugging.
- Keep the package distributable under the MIT license.
- Keep code and UI behavior close to DSM and Synology Photos conventions.
- Keep the package installable on DSM without manual post-installation steps.

### MUST NOT

- Add speculative fallbacks for unverified problems.
- Add defensive branches without a concrete failure mode.
- Mix unrelated refactoring into a targeted fix.
- Hide structural problems behind retries, resets, or silent recovery.
- Add CSS or component structure that is broader than the actual UI need.
- Introduce dependencies, assets, or bundled components that prevent MIT-compatible distribution.
- Require manual DSM shell steps, manual file copying, or manual patching after package installation.

## Distribution And Packaging Constraints

- Every bundled dependency, asset, model, and library MUST be compatible with MIT distribution of this package, or MUST remain external and user-supplied.
- If a dependency cannot be redistributed cleanly, the package MUST NOT silently bundle it.
- Optional external tools or models should follow the ExifTool pattern: explicit configuration, explicit status, no hidden download.
- Optional Python packages and model files MUST be explicitly configured, status-reported, and license-aware. Do not add automatic model downloads or implicit package installation paths.
- InsightFace code, wheelhouse packages, and model archives are optional external capabilities. Model files are user-supplied or explicitly uploaded/installed; they MUST NOT be bundled silently.
- The install path for normal package use MUST be fully handled by the DSM package itself.
- If something requires manual operator steps, treat that as a packaging gap, not as a normal product workflow.

## Runtime Configuration And State

- Default configuration belongs in `ConfigService.defaultConfig()` and `var/config.json`; new settings MUST be normalized in `ConfigService.normalizeConfig()`.
- UI config editors MUST preserve the full config shape and avoid dropping unrelated config areas.
- Runtime config is stored below `SYNOPKG_PKGVAR`, usually `/var/packages/AV_ImgData/var`.
- Persisted findings are stored through `FileAnalysisService`, currently as JSON under `analysis_findings`.
- Runtime progress is stored through `FileAnalysisService.writeRuntimeState(...)`, currently under `runtime_state`.
- Check ignore lists are not regular inline config arrays anymore. They are stored as dedicated files below `ignore_lists` and surfaced through config/status APIs.
- Legacy config migration is allowed only when it is deterministic and idempotent.

## DSM Alignment

- Prefer DSM-native behavior, naming, interaction patterns, and visual structure over custom product invention.
- UI should feel close to Synology DSM and Synology Photos unless there is a clear project-specific reason to differ.
- Backend process flow should align with observed Synology behavior where practical, but must remain explicit and debuggable in our own code.
- When choosing between a custom design and a DSM-like design, prefer the DSM-like design unless the custom design solves a concrete problem.

## Backend Architecture

### General

- Business logic belongs in `src/`.
- API request parsing belongs in `src/api/`.
- API handler glue belongs in dedicated handlers such as `src/handler/`.
- Small focused utility logic belongs in `src/services/`.
- Data containers belong in `src/models/`.

### Flow Rules

- HTTP/API entrypoints should stay thin.
- Request normalization and validation should happen near the API layer.
- Handler classes should encapsulate remote-system access such as Synology Photos APIs.
- Matching, analysis, and process orchestration should stay in explicit service or main workflow logic, not inside low-level request wrappers.
- Repeated domain workflows MUST be centralized in `ImgDataService` or a focused service helper, not copied between API routes, cleanup flows, checks flows, and face-match flows.
- Synology Photos person creation MUST go through the shared person creation and person-id resolution path (`createMatchedFaceAsPerson` / `_resolveCreatedPersonId`) instead of reimplementing response parsing or name lookup fallbacks.
- API routes MAY assemble route-specific response payloads, but MUST NOT duplicate multi-step write workflows such as "add Photos face, assign/create person, update findings, save mapping" when that behavior is shared by another route.
- API mutation routes that change findings, mappings, ignore lists, or progress MUST return enough updated state for the UI to continue without reconstructing backend state from stale local data.
- Session handling, authentication bootstrap, and Photos API retries belong in `SessionManager`; route handlers and services should consume structured session errors instead of duplicating login/resume logic.

### Error Handling

- Prefer one clear failure path over layered fallback behavior.
- Add retries only when the failure mode is known and the retry is intentional.
- If a process stops unexpectedly, inspect the process flow first. Do not patch symptoms with guessed resume logic.

## Long-Running Process Stability

These rules apply to all longer-running flows, including file analysis, checks, face matching, cleanup, metadata writes, and Synology Photos write operations.

### Process Identity

- Every long-running process SHOULD have an explicit operation identity such as `operation_id`.
- Progress updates SHOULD include a monotonic `revision` or equivalent ordering value.
- Frontend code MUST NOT let older progress responses overwrite newer progress for the same process.
- If multiple processes of the same type can exist, the active process MUST be distinguishable by user, action, and operation identity.
- The current long-running operation set is `file_analysis`, `checks`, `face_match`, and `cleanup`.
- Start paths for all long-running operations MUST check cross-operation blocking before spawning a worker.
- A stale stopping state may stop blocking new operations only through an explicit timeout/staleness rule, not through guessed thread absence.

### Progress Ownership

- Backend progress is the source of truth.
- Frontend code MAY render an initial empty/default state, but MUST NOT invent process progress that can overwrite backend state.
- Starting, resuming, skipping, or advancing a process MUST preserve the last reliable backend progress until a newer backend progress response arrives.
- Avoid explicit zero-value progress writes unless they represent a real backend state transition.
- View changes MUST NOT be required to recover lost progress or status messages.

### Progress Semantics

- Progress fields MUST have stable meanings across a process.
- Do not reuse one counter for both current item state and cumulative process totals.
- Cumulative counters MUST be monotonic unless there is an explicit reset with a new operation identity.
- Current-item counters and pending counters MUST be named separately from cumulative counters.
- User-visible totals MUST describe what they count, for example scanned files, discovered findings, ignored findings, resolved findings, failed findings, or written metadata entries.

### Status Messages

- Status messages SHOULD come from backend process phases or backend events.
- Frontend code MUST NOT broadly suppress backend messages while a process is running.
- If message smoothing is needed, make it explicit and phase-based, not based on guessed transient behavior.
- The last meaningful status SHOULD remain visible while a process action request is in flight.

### Result Handling

- A displayed result MUST remain stable until the backend explicitly replaces, resolves, skips, or clears it.
- A `next`, `skip`, or `resume` action MUST NOT clear the visible result before the backend acknowledges the state change.
- Result identity SHOULD be explicit enough to avoid returning to the same unresolved item accidentally.
- Resume cursors MUST be treated as backend-owned process state, not as a frontend reconstruction.

### Unified Status Schema

- Long-running operation payloads SHOULD include `status.schema_version == 1`.
- Backend status builders are the source of truth for `status.operation`, `status.action`, `status.mode`, `status.phase`, `status.progress`, and `status.counters`.
- UI code MUST use `status.progress` and `status.counters` when `status.schema_version == 1` and those fields are present.
- UI code may use legacy progress fields only when schema status fields are absent.
- UI code MUST NOT infer relevant counters from legacy raw fields such as `findings_count`, `resolved_count`, `ignored_count`, `skipped_count`, or `transferred_count` once schema counters are present.
- Backend code MUST send only relevant counters. Irrelevant zero counters are omitted.
- Zero counters may be shown only when the backend sets `show_when_zero: true`.
- Cross-operation start blocking MUST return `blocked_by_running_operation: true` and a schema status with `mode: "none"` and `phase: "blocked"`.
- A checks-only scan block may keep `blocked_by_running_scan: true` for compatibility, but new generic logic should use cross-operation blocking.
- Status messages should use `message_key` and `message_params`; UI text must be translated.

### Operation Modes

- `scan` means backend-owned search, check, cleanup, or analysis work.
- `findings` means an existing stored findings list is being reviewed or applied.
- `snapshot` means a refresh without active processing.
- `idle` means no active operation state.
- `none` means no progress display is intended, for example cross-operation blocked responses.
- `mode` is part of process identity. A `scan` state and a `findings` state MUST NOT overwrite each other without an explicit transition.
- Any uncertainty about mode, phase, counters, progress kind, reconnect behavior, stale stopping, or button labels MUST be resolved against `docs/status-concept-integrated.md`.

### Reconnect Rules

- Persisted `running: true` progress remains authoritative after DSM window close/reopen.
- Reconnect code MUST read progress without immediately applying it when a local findings review is active.
- Checks views MUST discover running check scans across check types and adopt only matching scan state.
- A local findings review MUST remain visible until the backend replaces, resolves, skips, ignores, or clears the current item.
- `stop_requested` applies only to the operation, action/check type, and mode that produced it.

### Error Structure

- Long-running processes SHOULD return structured errors.
- Structured errors SHOULD include `code`, `message_key`, `operation_id`, `phase`, `retryable`, and the relevant object identity such as path, person, image, face, or entry token.
- Errors from Synology APIs SHOULD preserve the remote API name, remote error code, and relevant request context when safe.
- Do not collapse write failures into generic 500 responses when the failing object and process phase are known.
- UI error text MUST use project translation rules and MUST NOT expose raw debug dumps as the primary user message.

### Write Safety

- File writes and Synology Photos writes MUST be treated as sensitive operations.
- Concurrent writes to the same image, sidecar, face, or Photos object SHOULD be guarded by an explicit process-level lock or equivalent sequencing.
- Before writing after a long-running read phase, code SHOULD detect whether the target object changed when practical.
- If a target changed during processing, fail with a clear conflict state instead of silently writing stale data.
- Atomic write patterns SHOULD be preferred for local metadata or sidecar changes where the platform allows them.
- Runtime JSON state and findings writes SHOULD use change-aware atomic writes through `FileAnalysisService` instead of ad hoc file writes.

### Retry And Recovery

- Retries MUST be limited to observed and understood failure modes.
- Retrying writes requires an idempotency argument or a verified safe retry condition.
- Unknown failures SHOULD pause or fail with enough context to investigate, not silently resume.
- Recovery logic MUST distinguish between process lost, authentication required, remote service busy, write conflict, and invalid input.
- Do not add guessed recovery for high-load behavior without logs, HAR data, or a reproducible failure mode.

### Persistence And Diagnostics

- Important long-running process state SHOULD survive UI navigation and app reload where practical.
- If progress is kept in memory, process loss MUST be detectable and reported explicitly.
- Runtime state files or operation logs SHOULD store enough recent context to answer which item failed and why.
- Diagnostic events SHOULD be tied to operation identity.
- Logs and API responses MUST avoid exposing secrets, tokens, or credentials.

## Frontend Architecture

### View Structure

- Vue view files in `ui/src/views/` should be primarily template/view definitions.
- Large script logic MUST NOT live inside view components.
- Reusable stateful UI logic should live in mixins or dedicated modules.
- If a view needs app state and actions, pass a `vm` object or use the established project pattern instead of rebuilding local orchestration.
- DSM app navigation is componentized; do not duplicate sidebar/navigation state inside feature views.
- External library configuration belongs in the external libraries view/mixin, not in general status or check views.

### Mandatory Separation

- Separate view/template concerns from behavioral logic.
- Separate icon components from navigation structure.
- Separate page styling from shared styling when possible.
- Do not reintroduce heavy `<script>` sections into views after logic has been extracted.

### State Rules

- Avoid mutating props directly.
- Keep displayed counters and derived progress values explicit.
- Do not mix cumulative values and current-run values unless the distinction is intentional and visible in code.
- Use operation-id and revision guards when applying polled progress.
- Anonymous progress responses MUST NOT overwrite a known active operation once an `operation_id` is known.
- For checks and face matching, saved findings counts come from the stored findings status/list, not from old completed progress.

## CSS Guidelines

### MUST

- Keep CSS as small and local as practical.
- Prefer shared utility classes or narrow shared classes over repeated one-off spacing rules.
- Keep selectors simple.
- Use existing class naming patterns.

### SHOULD

- Put cross-view layout rules in shared stylesheet files.
- Keep feature-specific styles in feature-specific CSS files when they are not reused elsewhere.

### MUST NOT

- Add broad selectors that affect unrelated views.
- Add decorative or oversized styling without a concrete product need.
- Solve structural problems with deep selector stacking.

## UI/UX Implementation Rules

- Favor stable status messages over noisy transient detail messages.
- Avoid duplicate information in the UI.
- Counters shown to the user must correspond to a clear semantic meaning.
- If a detail message is not reliable because backend phases are too fast or too coarse, simplify the message instead of pretending it is precise.
- Primary action labels are UI action states, not raw backend phases. Follow `docs/status-concept-integrated.md` for Start/Stop/Restart/Resume rules.
- Show backend status text inside the progress element when a progress element is visible. Do not also render the same message in a separate status line.
- Check `changed_since_days` is a scan-only filter. It MUST NOT affect stored findings review mode.
- Check ignore actions add deterministic entry tokens to the configured ignore list and update findings/progress state through backend mutation responses.

## Language Rules

- The default project language is English.
- UI text MUST always have a German translation.
- New UI strings should be added in English and German together.
- Missing German UI translations are treated as incomplete work, not as an optional follow-up.

## Synology / External API Integration

- Treat Synology Photos behavior as observed behavior, not assumed behavior.
- Verify request and response behavior with HAR, browser network traces, or direct API inspection before changing logic.
- If an API parameter appears supported in docs or binaries but has no observable effect, do not build product logic around it.
- Prefer explicit request construction in central handlers.

## Metadata And Face Geometry

- Supported metadata face schemas are currently `ACD`, `MICROSOFT`, and `MWG_REGIONS`.
- Metadata schema enablement belongs under `metadata.SCHEMAS`.
- Face coordinate comparison and signatures MUST use the shared coordinate precision helpers in `src/services/face_coordinate_precision.py`.
- Do not introduce a second coordinate rounding or string-formatting rule for face signatures.
- Display face normalization MUST preserve source format, orientation handling, and source identity.
- Unnamed ACD faces remain opt-in for flows that explicitly need them; default metadata parsing should not expose them broadly.
- MWG AppliedToDimensions, orientation, and dimension mismatch handling are already part of the metadata analysis surface. New logic must preserve the existing mismatch context and warnings.
- `stArea:unit` and other schema details must be validated from observed metadata samples before product behavior depends on them.

## File, Sidecar, And ExifTool Rules

- Native file access and ExifTool-backed access are both valid, but their responsibilities must stay visible in `tests/function_matrix.md`.
- Sidecar lookup variants are configuration-driven; do not hard-code a new lookup order in call sites.
- Sidecar read behavior is controlled by `SIDECAR_READ_MODE` and related normalized flags. New code should use the normalized config, not legacy booleans alone.
- Embedded XMP full scan is optional and bounded by `EMBEDDED_XMP_FULL_SCAN_MAX_BYTES`.
- ExifTool persistent mode is optional and timeout-bounded by config.
- ExifTool can be installed into the package target path from the UI, but the package must also support a manually configured external path.
- ExifTool update checks and online lookups must remain explicit and status-visible.
- If a parser starts calling ExifTool directly or file/context loading behavior diverges, update `tests/function_matrix.md`.

## Optional Face Detection / InsightFace

- OpenCV Haar detection and InsightFace detection are optional capabilities, not required package startup dependencies.
- InsightFace package status must report module import results, conflicts, wheelhouse settings, active model name, and model-store status.
- InsightFace models are read from the configured model root/model store or explicit uploads. Do not auto-download model files.
- InsightFace use in the current implementation is detection-oriented. Do not describe it as full person recognition unless recognition code and tests exist.
- Tests for optional face detection should use mocks unless explicitly running a manual DSM smoke test.

## Development Premises

### Process

- Inspect existing code before changing structure.
- Work with existing repository state; do not revert unrelated user changes.
- Validate behavioral changes with focused checks whenever possible.
- When behavior is unclear, inspect implementation, tests, runtime state, logs, HAR, or direct API responses before changing code.

### Testing / Verification

- Run the narrowest useful verification first.
- Prefer focused verification for narrow changes.
- Escalate to broader build or lint only when useful for the touched area.
- Existing unrelated lint failures must not be confused with the new change.
- For status/progress changes, update or run the status contract tests before relying on manual UI inspection.
- For UI reconnect, progress identity, or button-state changes, prefer focused integration tests under `tests/integration/status`, `tests/integration/ui`, `tests/integration/checks`, or `tests/integration/face_matching`.
- For optional dependency behavior, tests MUST pass without installing optional packages or downloading models.

## Decision Rules For New Changes

Before implementing a change, check:

1. Is there already an established local pattern?
2. Can the change stay within the current module boundary?
3. Is the proposed fallback based on an observed failure mode?
4. Is the UI value being shown semantically correct?
5. Is the CSS change narrower than or equal to the actual layout need?
6. Can the logic be kept out of the view component?
7. Does the change preserve operation identity, mode, and revision ordering?
8. Does the backend already provide a schema status payload that the UI should use?
9. Does the change affect stored findings, runtime state, ignore lists, or config migration?
10. Does the change add or alter an optional dependency, external tool, model, or license-sensitive asset?

If any answer is "no", stop and redesign the change more narrowly.

## Examples Of Project-Specific Rules

- `Views should not accumulate large script sections again after extraction to mixins.`
- `Do not add guessed process recovery for face matching without concrete evidence from HAR or API traces.`
- `Do not rely on undocumented Synology sort parameters if live testing shows no effect.`
- `Do not inflate CSS for minor spacing problems; standardize with a shared class where appropriate.`
- `Do not replace a stable total counter with a current-run counter unless that semantic change is intentional.`
- `Do not let a scan progress overwrite an active stored-findings review.`
- `Do not infer UI counters from raw progress fields when schema status counters exist.`
- `Do not add an InsightFace model download path without explicit user action and license visibility.`
- `Do not add a new face-coordinate precision rule outside the shared coordinate precision helper.`

## Preferred Documentation Style For Future Additions

When extending this document:

- Use short rule statements.
- Prefer `MUST`, `SHOULD`, `MUST NOT`.
- Record concrete project decisions, not generic software slogans.
- Add premises only if they are repeatedly relevant to this repository.
