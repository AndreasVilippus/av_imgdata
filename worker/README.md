# External Worker

This directory contains the future UI-free external worker runtime for AV ImgData.

The worker is intentionally separate from the DSM package runtime:

```text
DSM package
  = controller, DSM authority, job owner, status owner, final write owner

External worker
  = remote execution runtime, DSM Worker API client, local processor runner
```

The worker reuses the same processor contracts and will reuse compatible processor binaries from the same repository, but it is built and packaged as a separate artifact.

## Current status

Implemented:

```text
- worker/ project path
- worker-local CMake project
- av-imgdata-worker executable
- av-imgdata-worker-api-loop executable
- version command
- probe command with structured config extraction
- config-relative path resolution
- local face processor path resolution
- local face processor binary existence check
- local face processor version/probe checks
- capability list emitted only when version and probe succeed
- once command with native face processor execution
- run readiness loop
- C++ Worker API HTTP loop using curl as transport
- local/DSM-compatible worker API HTTP router for integration tests
- linux-x86_64 build target
- windows-x86_64 MinGW cross-build target
- docker-linux-x86_64 staging target, currently deferred for validation
- example config
- sample local job
- Linux systemd packaging placeholder
- Windows packaging notes
- Dockerfile and entrypoint
```

Still pending:

```text
- DSM package routing/wiring for the worker API HTTP endpoints
- file download/upload for non-shared-filesystem workers
- persistent warm native processor mode with model reuse
- automatic model distribution into worker bundles
```

## Commands

```text
av-imgdata-worker version
av-imgdata-worker probe --config <worker-config.json>
av-imgdata-worker once --config <worker-config.json> --job <job.json>
av-imgdata-worker run --config <worker-config.json>
av-imgdata-worker-api-loop --config <worker-config.json> --api-url <worker-api-url>
```

## Local build targets

```text
linux-x86_64
windows-x86_64
docker-linux-x86_64
```

Build from repository root:

```bash
bash tools/build-worker.sh --target linux-x86_64
bash tools/build-worker.sh --target windows-x86_64
bash tools/build-worker.sh --target docker-linux-x86_64
```

Optional clean builds:

```bash
bash tools/build-worker.sh --target linux-x86_64 --clean
bash tools/build-worker.sh --target windows-x86_64 --clean
bash tools/build-worker.sh --target docker-linux-x86_64 --clean
```

Docker validation is currently deferred. Optional Docker image build after Docker staging:

```bash
bash tools/build-worker.sh --target docker-linux-x86_64 --docker-build
```

## Native face processor bundles

Build the Linux native face processor before building the Linux worker when native face jobs should run from the worker bundle:

```bash
bash tools/build-native-face-processor-linux.sh --clean
bash tools/build-worker.sh --target linux-x86_64 --clean
```

The Linux native build automatically downloads missing upstream native dependencies into `worker/native_deps/linux-x86_64/`:

```text
worker/native_deps/linux-x86_64/onnxruntime/
  include/onnxruntime_c_api.h
  lib/libonnxruntime.so*

worker/native_deps/linux-x86_64/jpeg/
  include/jpeglib.h
  lib/libjpeg.so*
```

Downloaded dependency files are ignored by Git. The dependency fetcher records the pinned source URLs and versions in:

```text
worker/native_deps/linux-x86_64/native-deps-manifest.json
```

The fetcher also queries GitHub release metadata and prints update hints when newer releases are available. To force a dependency refresh:

```bash
bash tools/build-native-face-processor-linux.sh --clean --force-deps
```

To disable network fetching and update checks:

```bash
bash tools/build-native-face-processor-linux.sh --clean --no-fetch-deps --no-update-check
```

Pinned versions can be overridden for validation runs:

```bash
ONNXRUNTIME_VERSION=1.20.1 \
LIBJPEG_TURBO_VERSION=3.2.0 \
bash tools/build-native-face-processor-linux.sh --clean --force-deps
```

The Linux face processor is built and bundled with matching libjpeg/libjpeg-turbo headers and runtime from the same `JPEG_ROOT`. The build fails on detected JPEG header/runtime ABI mismatches.

Environment overrides for fully local dependency roots:

```bash
ONNXRUNTIME_ROOT=/path/to/onnxruntime \
JPEG_ROOT=/path/to/libjpeg-turbo \
bash tools/build-native-face-processor-linux.sh --clean --no-fetch-deps
```

For Windows native face processor builds, use:

```bash
bash tools/build-native-face-processor-windows.sh --clean
bash tools/build-worker.sh --target windows-x86_64 --clean
```

## Worker API HTTP router integration test

The framework-free local router exposes the same endpoint adapter that DSM routing should call later:

```text
POST /worker-api/register
POST /worker-api/heartbeat
POST /worker-api/claim
POST /worker-api/result
POST /worker-api/fail
GET  /worker-api/status
```

Start the router from the repository root:

```bash
python3 tools/worker-api-http-router.py \
  --host 127.0.0.1 \
  --port 8765 \
  --package-var "$PWD"
```

Create or refresh a local worker token and copy it into the worker bundle:

```bash
TOKEN="$(python3 tools/worker-api-store.py --package-var "$PWD" create-token \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')"
printf '%s\n' "$TOKEN" > dist/av-imgdata-worker-linux-x86_64/worker.token
```

Queue a local test job:

```bash
python3 tools/worker-api-store.py --package-var "$PWD" enqueue \
  --job-id job-http-local-1 \
  --type face_native_embed \
  --payload '{"local_path":"tests/images/test_raw.jpg","min_confidence":0.5,"max_faces":1,"det_size":[640,640]}'
```

Run the C++ HTTP loop against the router:

```bash
dist/av-imgdata-worker-linux-x86_64/bin/av-imgdata-worker-api-loop \
  --config dist/av-imgdata-worker-linux-x86_64/config/worker-config.example.json \
  --api-url http://127.0.0.1:8765/worker-api \
  --max-iterations 1
```

Expected event:

```json
{"mode":"api-loop","claim_status":"claimed","reported":"result"}
```

Check API state:

```bash
curl -s http://127.0.0.1:8765/worker-api/status
```

## Debian build host requirements

Baseline:

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential \
  cmake \
  ninja-build \
  git \
  zip \
  unzip \
  curl \
  dpkg
```

For Windows cross-builds:

```bash
sudo apt-get install -y \
  mingw-w64 \
  g++-mingw-w64-x86-64
```

Docker image build requires Docker only when `--docker-build` is used.

## Output layout

Linux:

```text
dist/av-imgdata-worker-linux_x86_64/    # canonical path is dist/av-imgdata-worker-linux-x86_64/
  bin/av-imgdata-worker
  bin/av-imgdata-worker-api-loop
  bin/av-imgdata-face-processor
  config/worker-config.example.json
  jobs/sample-worker-job.json
  .models/face/README.txt
  logs/
  work/
  lib/libonnxruntime.so*
  lib/libjpeg.so*
  share/processor_contract/schemas/
```

Windows:

```text
dist/av-imgdata-worker-windows-x86_64/
  bin/av-imgdata-worker.exe
  bin/av-imgdata-worker-api-loop.exe
  bin/av-imgdata-face-processor.exe
  config/worker-config.example.json
  jobs/sample-worker-job.json
  .models/face/README.txt
  logs/
  work/
  share/processor_contract/schemas/
```

Docker staging:

```text
dist/av-imgdata-worker-docker-linux-x86_64/
  Dockerfile
  entrypoint.sh
  bin/av-imgdata-worker
  config/worker-config.example.json
  jobs/sample-worker-job.json
  .models/face/README.txt
  share/processor_contract/schemas/
```

## Smoke tests

Linux:

```bash
dist/av-imgdata-worker-linux-x86_64/bin/av-imgdata-worker version
dist/av-imgdata-worker-linux-x86_64/bin/av-imgdata-worker probe \
  --config dist/av-imgdata-worker-linux-x86_64/config/worker-config.example.json
dist/av-imgdata-worker-linux-x86_64/bin/av-imgdata-worker once \
  --config dist/av-imgdata-worker-linux-x86_64/config/worker-config.example.json \
  --job dist/av-imgdata-worker-linux-x86_64/jobs/sample-worker-job.json
dist/av-imgdata-worker-linux-x86_64/bin/av-imgdata-worker-api-loop --help
```

Windows, after copying the bundle to Windows 11:

```powershell
.\bin\av-imgdata-worker.exe version
.\bin\av-imgdata-worker.exe probe --config .\config\worker-config.example.json
.\bin\av-imgdata-worker.exe once --config .\config\worker-config.example.json --job .\jobs\sample-worker-job.json
.\bin\av-imgdata-worker-api-loop.exe --help
```

Docker:

```bash
docker build -t av-imgdata-worker:phase-e dist/av-imgdata-worker-docker-linux-x86_64
docker run --rm av-imgdata-worker:phase-e version
```

## Probe behavior

`probe` reads `worker-config.example.json`, extracts the configured face processor, resolves relative paths against the config file directory, and attempts:

```text
<face_processor> version
<face_processor> probe --model-root <model_root> --model-name <model_name>
```

If the face processor binary is not present in the worker bundle yet, `probe` still returns a valid worker JSON payload with:

```json
{
  "face_processor_binary_exists": false,
  "capabilities": []
}
```

Capabilities are advertised only when both `version` and `probe` succeed.

## Directory policy

Worker-specific build files belong below this directory. This includes worker-only CMake toolchains.

Shared processor code belongs below `processors/native/`.

DSM package build logic remains below `SynoBuildConf/` and package build scripts in `tools/`.
