# Optional Worker Concept

## Purpose

This document describes the optional worker architecture for `av_imgdata` after the first external Worker API path has been validated.

Version `0.10.0` is the development line for turning the validated Worker API
path into a maintained external-worker implementation.

The DSM package remains the authority for:

```text
- package configuration through ConfigService
- authentication and worker token management
- DSM and Synology Photos integration
- job ownership and queue state
- worker registration and heartbeat state
- result validation before final commit
- status ownership
- progress ordering
- conflict handling
- final writes
- persistence
```

Expensive processing may run through:

```text
- package-shipped local native C++ face processor
- package-shipped optional native libvips image processor
- local persistent C++ face processor subprocess mode
- optional external worker runtime executing compatible processor binaries/modules
```

The external worker is an optional offload path. It does not replace the package-internal processor path. The package-internal native processor remains part of the DSM package and remains available as local execution path, fallback path, and baseline production path for DSM-local processing.

## Current Architecture

```text
DSM package
  = controller, config owner, job owner, token owner, status owner, final write owner

Local native C++ face processor
  = package-shipped av-imgdata-face-processor
  = built through Synology Toolkit for the DSM package platform
  = executes ProcessorContract jobs locally on the NAS/package host
  = supports single-image, batch, ranking, profile math and persistent stdin/stdout mode

Optional local native image processor
  = package-shipped av-imgdata-image-processor when AV_IMGDATA_WITH_VIPS=1
  = executes libvips-based image operations and batch operations

Optional external worker runtime
  = separate runtime outside the DSM backend process
  = current targets: Windows and Linux
  = optional execution target for compute offload
  = registers/heartbeats/claims jobs through Worker API
  = executes compatible local processor binaries/modules
  = reports structured result/fail payloads back to DSM
```

The architecture is not “NAS or external”. It is:

```text
DSM package
├── internal package processor path remains available
└── optional external worker mode for selected offloaded tasks
    ├── Windows worker
    ├── Linux worker
    └── later Docker/cloud/GPU workers
```

## Current Implemented State

Implemented and validated:

```text
- optional FastAPI Worker API mounted at /worker-api
- Worker API enable/disable through package config worker_api.ENABLED
- Worker API config read through ConfigService from ${SYNOPKG_PKGVAR}/config.json
- Worker API state stored in ${SYNOPKG_PKGVAR}/worker-api-state.json
- worker token creation through tools/worker-api-store.py
- heartbeat, claim, result and fail flow
- DSM start script exports AV_IMGDATA_WORKER_API_STATE_PATH
- DSM backend remains bound to 127.0.0.1 by default
- backend bind can be overridden with AV_IMGDATA_BACKEND_HOST and AV_IMGDATA_BACKEND_PORT
- external access is expected through DSM Reverse Proxy/nginx, not by default external bind
- package build can build external worker bundles
- Windows worker API loop has been validated through DSM Reverse Proxy
- Windows worker successfully claimed and completed a face_native_embed job
```

Validated external flow:

```text
DSM package FastAPI
→ /worker-api
→ DSM Reverse Proxy
→ Windows worker API loop
→ heartbeat
→ claim
→ local processor execution
→ result upload
```

The current successful Windows worker command shape is:

```powershell
.\bin\av-imgdata-worker-api-loop.exe `
  --config .\config\worker-config.example.json `
  --api-url http://savy:8088/worker-api `
  --path-base-dir Q:\Projekte\Synology\toolkit\source\av_imgdata `
  --max-iterations 1
```

For real photo processing, `--path-base-dir` must point to a worker-local view of the NAS photo share, for example `P:\photo`, `\\savy\photo`, or `/mnt/savy/photo`.

## Build And Artifact Policy

The DSM package build remains based on Synology Toolkit and the package scripts.

External worker bundles are generated artifacts. They are built from the same repository but are not source files.

```text
build/                local build artifacts, not tracked
/dist/                generated worker bundles, not tracked
.models/              local model files, not tracked
worker/native_deps/   local third-party binary dependencies, not tracked
```

`.gitignore` already excludes these directories. Generated `dist/` content may be removed locally and regenerated through the build scripts.

Current external worker targets:

```text
linux-x86_64
windows-x86_64
docker-linux-x86_64
```

The package includes generated worker archives under the installed package target so that administrators can download them for external hosts. Linux and Docker worker targets are packaged as `.tar.gz`; Windows worker targets are packaged as `.zip`. The package must not install the unpacked worker bundle directories; those remain generated build inputs under `dist/`, not package contents.

## Worker API Endpoint Model

Current implemented API path:

```text
GET  /worker-api/status
POST /worker-api/register
POST /worker-api/heartbeat
POST /worker-api/claim
POST /worker-api/result
POST /worker-api/fail
```

Current endpoint model is intentionally simple:

```text
- token auth through Authorization: Bearer <token>
- package-local JSON state
- one job state store
- worker reports result/fail after local execution
```

Future API extensions for file transfer should stay under `/worker-api` and use the same worker token auth model.

## Execution Target Selection

The DSM package selects where a task runs. The worker does not decide final ownership or final writes.

Target model:

```text
JobDispatcher
  -> LocalNativeProcessorAdapter
  -> ExternalWorkerProcessorAdapter
```

Default order should remain conservative:

```text
1. local_native when available and configured as standard path
2. external_worker when enabled, compatible and selected/preferred
3. fail with actionable status if no compatible target exists
```

When external offload is preferred:

```text
1. external_worker if enabled, compatible and a suitable worker/input path exists
2. local_native fallback if configured
3. fail with actionable status if neither path is possible
```

This preserves the internal package path and makes external processing optional.

## Image Input Strategies For External Workers

External workers need access to the input image. There are two supported conceptual modes:

```text
1. shared_path
2. download
```

Both modes use the same Worker API for job control, heartbeat, claim and result reporting. They differ only in how the worker obtains the image bytes.

### shared_path Mode

`shared_path` is the fast LAN-oriented mode.

The DSM package converts a NAS source path into a relative path under a configured NAS root. The worker resolves that relative path against its own local `--path-base-dir`.

Example NAS path:

```text
/volume1/photo/Urlaub/IMG_001.jpg
```

Example job payload:

```json
{
  "input_mode": "shared_path",
  "path_profile": "photos",
  "source_path": "/volume1/photo/Urlaub/IMG_001.jpg",
  "local_path": "Urlaub/IMG_001.jpg",
  "min_confidence": 0.5,
  "max_faces": 1,
  "det_size": [640, 640]
}
```

Windows worker examples:

```powershell
--path-base-dir P:\photo
```

or:

```powershell
--path-base-dir \\savy\photo
```

Linux worker example:

```bash
--path-base-dir /mnt/savy/photo
```

Resolved worker-local input path:

```text
P:\photo\Urlaub\IMG_001.jpg
/mnt/savy/photo/Urlaub/IMG_001.jpg
```

Advantages:

```text
- fastest normal LAN option
- avoids routing large files through the DSM backend process
- uses SMB/NFS/local sync mechanisms designed for file access
- avoids temporary HTTP download copies
- best for mass processing and large libraries
```

Disadvantages:

```text
- worker needs access to the NAS share or synced data
- administrator must configure SMB/NFS/VPN/local mount permissions
- path mapping must be correct
- not suitable for isolated cloud workers without storage access
```

`shared_path` should be the default for Windows/Linux workers in the same LAN.

### download Mode

`download` is the fallback/remote mode for workers that do not have direct file-system access to the NAS share.

The worker claims a job and then downloads the input file from the DSM package through the Worker API. The worker stores the file in its local workspace, executes the processor against the temporary local copy, and then reports the result.

Example job payload:

```json
{
  "input_mode": "download",
  "path_profile": "photos",
  "source_path": "/volume1/photo/Urlaub/IMG_001.jpg",
  "input_ref": {
    "type": "worker_api_file",
    "job_id": "job-123",
    "filename": "IMG_001.jpg",
    "size_hint": 7340032
  },
  "min_confidence": 0.5,
  "max_faces": 1,
  "det_size": [640, 640]
}
```

Proposed endpoint:

```text
GET /worker-api/jobs/{job_id}/input
Authorization: Bearer <token>
```

Optional later endpoint for multiple assets/batches:

```text
GET /worker-api/jobs/{job_id}/input/{asset_id}
```

Worker-local flow:

```text
1. heartbeat
2. claim job
3. see input_mode=download
4. GET /worker-api/jobs/{job_id}/input
5. store bytes under work/input-cache/<job_id>/input-file
6. build ProcessorContract input with worker-local image_path
7. execute av-imgdata-face-processor
8. POST /worker-api/result or /worker-api/fail
9. cleanup according to local retention policy
```

Advantages:

```text
- works without SMB/UNC/NFS access
- useful for cloud workers or isolated external machines
- avoids per-worker path mapping
- uses the same HTTPS/token-authenticated Worker API
- simpler initial setup for remote workers
```

Disadvantages:

```text
- slower for many images than shared_path
- DSM package backend becomes a file-transfer path
- Reverse Proxy and FastAPI must stream potentially large files
- local temporary copies are required on the worker
- timeout, size limit, retry and cleanup policy are required
```

`download` should be optional, not the only mode. It solves the “no path access” case, but it is not the preferred high-throughput LAN mode.

## shared_path Versus download Performance

For single images in a LAN, the difference may be acceptable. A 3–15 MB image can usually be downloaded through HTTP quickly enough for occasional jobs.

For large batches and library scans, `shared_path` should be materially better:

```text
shared_path:
  Worker reads through SMB/NFS/local file system.
  DSM backend stays mostly out of the data plane.

download:
  DSM backend streams every image through FastAPI/nginx.
  Worker writes a temporary copy before processing.
  Backend, reverse proxy and worker disk I/O become part of every job.
```

Decision:

```text
- shared_path = default for LAN Windows/Linux workers
- download = optional fallback for workers without share access
```

Do not remove the shared path mode unless measurements later show that the HTTP download path is fast enough under realistic batch load and does not overload the DSM package backend.

## Path Profile Concept For shared_path

The DSM package should not store Windows-specific or Linux-specific absolute worker paths in the package config as the global truth. Different workers may mount the same NAS root differently.

The DSM package should store NAS-side path profiles:

```json
{
  "external_workers": {
    "ENABLED": true,
    "PREFERRED": false,
    "DEFAULT_INPUT_MODE": "shared_path",
    "ALLOW_DOWNLOAD_INPUT": true,
    "PATH_PROFILES": {
      "photos": {
        "ENABLED": true,
        "NAS_ROOT": "/volume1/photo",
        "DEFAULT_INPUT_MODE": "shared_path",
        "ALLOW_DOWNLOAD_INPUT": true
      }
    }
  }
}
```

For `shared_path`, the package converts:

```text
/volume1/photo/Album/Bild.jpg
```

into:

```text
Album/Bild.jpg
```

Rules:

```text
- source path must be absolute on the NAS
- source path must resolve below the selected NAS_ROOT
- payload path separator is always /
- generated local_path must be relative
- ../ path escapes are forbidden
- symlink/realpath escapes must be rejected where possible
- source_path may be kept for diagnostics, but workers should process local_path/input_ref only
```

## Worker Capabilities For Input Modes

Workers must advertise what input modes they can handle.

Shared path worker:

```json
{
  "worker_id": "windows-pc-1",
  "capabilities": [
    "face_native_embed",
    "input_shared_path"
  ]
}
```

Download worker:

```json
{
  "worker_id": "cloud-worker-1",
  "capabilities": [
    "face_native_embed",
    "input_download"
  ]
}
```

A worker may support both:

```json
{
  "worker_id": "linux-box-1",
  "capabilities": [
    "face_native_embed",
    "input_shared_path",
    "input_download"
  ]
}
```

Claim logic should prevent incompatible assignments:

```text
input_mode=shared_path -> worker must have input_shared_path
input_mode=download    -> worker must have input_download
```

This avoids assigning a shared-path job to a cloud worker that cannot read the NAS share.

## Security Requirements For download Mode

Download mode makes the DSM package a controlled file server for worker jobs. It must not become a generic file-read API.

Server-side checks:

```text
- valid worker token required
- job must exist
- job must be claimed by the requesting worker, or claim ownership must be otherwise verified
- source_path must be derived from package job state, not from arbitrary request query parameters
- source_path must match an enabled PATH_PROFILE
- source_path must resolve below the profile NAS_ROOT
- path traversal and symlink escape must be rejected where possible
- optional max file size policy should be enforced
- content should be streamed, not loaded fully into memory
```

Recommended response:

```text
200 OK
Content-Type: application/octet-stream
Content-Length: <size if known>
Content-Disposition: attachment; filename="IMG_001.jpg"
```

Error model:

```text
401 unauthorized
403 worker_not_assigned_to_job
404 job_or_input_not_found
409 job_input_mode_not_download
413 input_file_too_large
500 input_stream_failed
```

## Worker Workspace And Cache

For `download`, the worker should store input files under a worker-local workspace:

```text
work/input-cache/<job_id>/<filename>
```

First implementation may delete inputs after each job. Later, workers may keep a bounded cache using a key such as:

```text
source_id + size + mtime + optional sha256
```

Cache is optional. It should not be required for correctness.

## Job Payload Standard

For single-image face jobs, external worker payloads should contain common processing options plus input metadata.

Shared path example:

```json
{
  "job_id": "job-photo-1",
  "type": "face_native_embed",
  "payload": {
    "input_mode": "shared_path",
    "path_profile": "photos",
    "source_path": "/volume1/photo/Album/Bild.jpg",
    "local_path": "Album/Bild.jpg",
    "min_confidence": 0.5,
    "max_faces": 1,
    "det_size": [640, 640]
  }
}
```

Download example:

```json
{
  "job_id": "job-photo-2",
  "type": "face_native_embed",
  "payload": {
    "input_mode": "download",
    "path_profile": "photos",
    "source_path": "/volume1/photo/Album/Bild.jpg",
    "input_ref": {
      "type": "worker_api_file",
      "job_id": "job-photo-2",
      "filename": "Bild.jpg"
    },
    "min_confidence": 0.5,
    "max_faces": 1,
    "det_size": [640, 640]
  }
}
```

The worker transforms either form into ProcessorContract input with a worker-local `input.image_path`.

## Implementation Roadmap From Current State

### Phase H1: shared_path path mapping

```text
- add external_workers config defaults through ConfigService
- add PATH_PROFILES config model
- add service for NAS source path -> relative worker local_path
- add tests for relative path creation and escape rejection
- add worker-api-store.py helper for enqueue-path test jobs
- keep workers resolving relative local_path against --path-base-dir
```

### Phase H2: input capability matching

```text
- add input_shared_path and input_download capability names
- make jobs declare required input capability
- make claim logic skip jobs incompatible with worker capabilities
- add tests for claim filtering
```

### Phase H3: download input mode

```text
- add GET /worker-api/jobs/{job_id}/input
- stream source_path from NAS after PATH_PROFILE validation
- require token and claimed-worker ownership
- add worker-side file download into work/input-cache
- run processor against downloaded local file
- report result/fail as today
```

### Phase H4: UI and documentation

```text
- expose external worker enablement separately from internal package processor config
- show Shared Path as recommended LAN mode
- show Download as fallback mode for workers without NAS share access
- document Windows path-base-dir examples
- document Linux mount examples
- document Reverse Proxy setup for Worker API
```

## Final Decision

```text
- The internal package processor remains part of the package.
- External workers are optional offload targets.
- Current focus is Windows and Linux external workers.
- shared_path is the preferred high-throughput LAN mode.
- download is the planned fallback for workers without direct NAS path access.
- Both modes must use the same Worker API control plane.
- DSM remains the authority for configuration, queue ownership, validation and final writes.
- Workers only execute processor jobs and report structured results.
```
