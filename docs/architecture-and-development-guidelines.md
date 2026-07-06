# Architecture And Development Guidelines

## Purpose

This document defines the architectural rules, development constraints, and project premises for `av_imgdata`.

It is intentionally compact to stay adapter-safe. The source guideline document was reviewed and folded into this repository plan. Future changes should keep this file concise and move large implementation plans into separate focused documents under `docs/`.

## Core Rules

### Must

- Keep changes narrow and task-focused.
- Inspect existing code before changing structure.
- Reuse existing project patterns before introducing new abstractions.
- Prefer explicit logic over guessed fallback behavior.
- Preserve predictable behavior over convenience hacks.
- Keep frontend and backend structure simple and inspectable.
- Keep code paths easy to trace during debugging.
- Keep the package distributable under the MIT license.
- Keep behavior close to DSM and Synology Photos conventions.
- Keep the package installable on DSM without manual post-installation steps.
- Keep native package components self-contained in the SPK when they are enabled by default.

### Must Not

- Add speculative fallbacks for unverified problems.
- Add defensive branches without a concrete failure mode.
- Mix unrelated refactoring into targeted fixes.
- Hide structural problems behind retries, resets, or silent recovery.
- Add broad CSS, broad component structure, or decorative UI without concrete need.
- Introduce dependencies, assets, models, or bundled components that prevent compliant SPK distribution under the project license and the bundled components' own licenses.
- Require manual DSM shell steps, manual file copying, or manual patching after package installation.

## Distribution And Optional Dependencies

- Bundled dependencies, assets, models, and libraries must be compatible with distributing this MIT-licensed project as an SPK while preserving their own license obligations, or remain external and user-supplied.
- Optional external tools and models must be explicit, configurable, status-visible, and license-aware.
- InsightFace model archives remain user-supplied.
- ONNXRuntime, OpenCV, libvips, libheif, libde265, and required shared runtime libraries may be packaged only when their license notices, source references, and redistribution obligations are preserved in the SPK.
- GPL codec implementations such as x265 must stay out of the package unless the package license and distribution model are deliberately changed.
- InsightFace models must not be silently bundled or auto-downloaded.
- Optional package tests must pass without installing optional packages or downloading models.

## Runtime Configuration And State

- Defaults belong in `ConfigService.defaultConfig()` and `var/config.json`.
- New settings must be normalized in `ConfigService.normalizeConfig()`.
- UI config editors must preserve the full config shape.
- Runtime config and state live below `SYNOPKG_PKGVAR`.
- Operational findings, suppressions, mappings, and runtime state should go through `src/av_imgdata/db` repositories, `RuntimeStateService`, `FileAnalysisService`, or a successor storage abstraction.
- Legacy JSON files are migration or compatibility inputs unless the current storage abstraction still owns that file.
- Remaining runtime JSON writes should remain change-aware and atomic.
- Legacy config migration is allowed only when deterministic and idempotent.

## Backend Architecture

- Business logic belongs in `src/`.
- API request parsing belongs in `src/api/`.
- Remote-system access belongs in handlers such as `src/handler/`.
- Focused utility and domain logic belongs in `src/services/`.
- Data containers belong in `src/models/`.
- HTTP/API entrypoints should stay thin.
- Request normalization and validation should happen near the API layer.
- Shared multi-step workflows must not be duplicated between API routes, cleanup flows, checks flows, and face-match flows.
- Synology Photos person creation must go through the shared person creation and person-id resolution path.
- Session handling, authentication bootstrap, and Photos API retries belong in `SessionManager`.

## Native Processor Architecture

- Native source code belongs under `processors/native/`.
- Native build and package integration belongs in `tools/`, `SynoBuildConf/build`, `SynoBuildConf/install`, and matching static contract tests.
- Runtime access to native binaries must go through service adapters in `src/services/`; UI and workflow code should not execute native binaries directly.
- The native face processor and the optional libvips image processor are separate components with separate status, config, and failure reasons.
- `FACE_PROCESSOR` readiness covers the InsightFace-compatible embedding runtime and model/license state.
- `IMAGE_PROCESSOR_VIPS` readiness covers the libvips image backend binary, linked libraries, supported formats, and fallback behavior.
- libvips may be preferred only when `IMAGE_PROCESSOR_VIPS.ENABLED`, `PREFERRED`, status availability, and probed format support agree.
- Fallback from libvips to the default decoder path must be controlled by `ALLOW_FALLBACK_TO_DEFAULT` and visible in logs/status when it matters.
- Native processor command output must keep a stable JSON contract with `contract_version`, `success`, operation identity, and structured errors.
- Native status checks should be cached or warmed in the background when direct probing would block the UI.

## Long-Running Process Rules

The long-running operation set is:

- `file_analysis`
- `checks`
- `face_match`
- `cleanup`

Rules:

- Every long-running process should have `operation_id` or equivalent identity.
- Progress updates should include a monotonic `revision` or equivalent ordering value.
- Older progress responses must not overwrite newer progress.
- Backend progress is the source of truth.
- Frontend may render initial empty/default state, but must not invent process progress that can overwrite backend state.
- `operation`, `mode`, `action`, and `operation_id` are state identity.
- `scan` and `findings` must not overwrite each other without explicit transition.
- Cross-operation start blocking must be explicit.
- A stale stopping state may stop blocking only through an explicit timeout/staleness rule.

## Unified Status Schema

Long-running operation payloads should include `status.schema_version == 1`.

Backend status builders are the source of truth for:

- `status.operation`
- `status.action`
- `status.mode`
- `status.phase`
- `status.progress`
- `status.counters`

UI rules:

- Use `status.progress` and `status.counters` when schema version 1 is present.
- Do not infer relevant counters from legacy raw fields once schema counters are present.
- Do not show counters not sent by the backend.
- Show backend status text inside the progress element when progress is visible.
- Do not duplicate the same message in a separate status line.

Details are defined in `docs/status-concept-integrated.md`.

## Write Safety

- File writes and Synology Photos writes are sensitive operations.
- Concurrent writes to the same image, sidecar, face, or Photos object should be guarded by explicit locks or sequencing.
- Before writing after a long-running read phase, detect changed target objects where practical.
- If a target changed, fail with a clear conflict state instead of silently writing stale data.
- Retrying writes requires an idempotency argument or verified safe retry condition.

## Frontend Architecture

- Vue view files in `ui/src/views/` should be primarily view/template definitions.
- Large script logic must not accumulate in view components.
- Reusable stateful logic should live in mixins or dedicated modules.
- Keep navigation state centralized.
- Avoid mutating props directly.
- Keep counters and derived progress values explicit.
- Use operation-id and revision guards when applying polled progress.
- New UI strings must be added in English and German together.

## Metadata And Face Geometry

- Supported metadata face schemas are `ACD`, `MICROSOFT`, `MWG_REGIONS`, and `IPTC_EXT_REGIONS`.
- Metadata schema enablement belongs under `metadata.SCHEMAS`.
- Face coordinate comparison and signatures must use the shared coordinate precision helpers.
- Do not add another coordinate rounding or string-formatting rule.
- Display face normalization must preserve source format, orientation handling, and source identity.
- Unnamed ACD faces remain opt-in only.
- MWG AppliedToDimensions, orientation, and dimension mismatch context must be preserved.

## File, Sidecar, And ExifTool Rules

- Native file access and ExifTool-backed access are both valid, but responsibilities must stay visible in `tests/function_matrix.md`.
- Sidecar lookup variants are configuration-driven.
- Do not hard-code lookup order in call sites.
- Embedded XMP full scan is optional and bounded.
- ExifTool persistent mode is optional and timeout-bounded.
- ExifTool installation and update checks must remain explicit and status-visible.
- libvips-backed image decode and normalization is optional, status-visible, and controlled by `IMAGE_PROCESSOR_VIPS`.
- If parser/file access behavior changes, update `tests/function_matrix.md`.

## Synology API Rules

- Treat Synology Photos behavior as observed behavior, not assumed behavior.
- Verify API behavior with HAR, browser traces, direct API inspection, or reproducible logs before changing product logic.
- Do not rely on undocumented or ineffective parameters.
- Preserve remote API names and safe error context in structured errors.

## Testing And Verification

- Run the narrowest useful verification first.
- Prefer focused tests for focused changes.
- Escalate to broader build or lint only when useful for the touched area.
- Existing unrelated failures must not be confused with new changes.
- Status/progress changes require status contract tests.
- UI reconnect, progress identity, and button-state changes require focused UI or integration tests where available.
- Native build, packaging, licensing, and binary-contract changes require static package/build contract tests.
- Native processor runtime behavior requires focused service tests before relying on SPK-level validation.

## Decision Checklist

Before implementing a change, verify:

1. Is there an established local pattern?
2. Can the change stay within the current module boundary?
3. Is the fallback based on an observed failure mode?
4. Is the UI value semantically correct?
5. Is the CSS change no broader than needed?
6. Can behavior stay out of the view component?
7. Are operation identity, mode, and revision ordering preserved?
8. Does schema status already provide the data the UI should use?
9. Does the change affect findings, runtime state, ignore lists, or config migration?
10. Does the change add or alter an optional dependency, external tool, model, or license-sensitive asset?
11. Does the change add or alter a native processor command, binary, packaged library, or runtime fallback path?
